"""Named-entity classifier for natural-language queries (UC-02).

Runs locally, before Gemini, and finds what the user actually wrote:

    PLACE        Faisalabad, Mangla Dam                  spaCy NER (GPE / LOC / FAC)
    DATE         from June to August 2024, 2023          spaCy NER + patterns for relative dates
    DATASET      Sentinel-2 -> sentinel2_sr              aliases from the dataset catalogue
    PROCESS      NDVI, water bodies -> WaterBodyDetection
    ANALYSIS     vegetation -> Vegetation
    BAND         B4, VV
    CLOUD_COVER  under 20% clouds -> 20
    RESOLUTION   at 30 m -> 30
    COMPOSITE    median, average -> mean

The entities are given to Gemini as hints, used to check its answer, and,
when Gemini is unavailable, used on their own to fill what they can.

spaCy (``en_core_web_sm``) is optional: without it, places and dates come from
simpler patterns and everything else still works.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from calendar import monthrange
from datetime import date

from backend.config import ANALYSIS_KEYWORDS, DATASET_ALIASES, DATASETS, PROCESS_ALIASES
from backend.dto import EntityDTO

log = logging.getLogger(__name__)

SPACY_MODEL = "en_core_web_sm"
PLACE_LABELS = ("GPE", "LOC", "FAC")
RETRY_PLACE_LABELS = ("ORG", "NORP", "PERSON")


class IEntityExtractor(ABC):
    @abstractmethod
    def extract(self, text: str) -> list[EntityDTO]:
        """Entities in ``text``, ordered by position."""


# ----------------------------------------------------------------------------- patterns
def _phrase_pattern(phrase: str) -> str:
    """'sentinel-2' -> sentinel[\\s-]?2 so spacing and hyphens don't matter."""
    parts = re.split(r"[\s\-]+", phrase.strip())
    return r"[\s\-]?".join(re.escape(p) for p in parts)


def _alias_regex(aliases: dict[str, tuple[str, ...]]) -> list[tuple[re.Pattern, str]]:
    """Longest phrases first, so 'sentinel-2 l1c' wins over 'sentinel-2'."""
    pairs = [(phrase, value) for value, phrases in aliases.items() for phrase in phrases]
    pairs.sort(key=lambda pair: len(pair[0]), reverse=True)
    return [(re.compile(rf"(?<![\w-]){_phrase_pattern(p)}(?![\w-])", re.IGNORECASE), v) for p, v in pairs]


_DATASET_PATTERNS = _alias_regex(DATASET_ALIASES)
_PROCESS_PATTERNS = _alias_regex(PROCESS_ALIASES)
_ANALYSIS_PATTERNS = _alias_regex(ANALYSIS_KEYWORDS)

# Band names that are also process names (MOD13Q1 has "NDVI" / "EVI" bands) count as processes.
# Only code-like band names (B4, SR_B5, VV); Dynamic World's "water" / "crops" are ordinary words.
_ALL_BANDS = sorted(
    {
        band for info in DATASETS.values() for band in info.bands
        if band not in PROCESS_ALIASES and (any(c.isdigit() for c in band) or band.isupper())
    },
    key=len, reverse=True,
)
_BAND_PATTERN = re.compile(r"(?<![\w-])(" + "|".join(re.escape(b) for b in _ALL_BANDS if len(b) <= 6) + r")(?![\w-])")

_PERCENT = r"(\d{1,3})\s*(?:%|percent|per cent)"
_LIMIT = r"(?:under|below|less than|lower than|<=?|max(?:imum)?(?: of)?|at most|up to|no more than)"
_CLOUD_PATTERNS = [
    re.compile(rf"(?:{_LIMIT}\s*)?{_PERCENT}\s*(?:of\s+)?cloud(?:s|y|iness|\s*cover(?:age)?)?\b", re.I),
    re.compile(rf"\bcloud(?:s|\s*cover(?:age)?)?\s*(?:of\s*)?(?:{_LIMIT}\s*)?{_PERCENT}", re.I),
]
_CLOUD_FREE = re.compile(r"\b(?:cloud[\s-]?free|cloudless|no clouds|clear[\s-]sky)\b", re.I)
CLOUD_FREE_PERCENT = 10

_UNIT = r"(km|kilometres?|kilometers?|m|metres?|meters?)"
_RESOLUTION_PATTERNS = [
    re.compile(rf"\b(?:at|resolution(?: of)?|scale(?: of)?|pixel size(?: of)?)\s*(\d+(?:\.\d+)?)\s*{_UNIT}\b", re.I),
    re.compile(rf"\b(\d+(?:\.\d+)?)\s*{_UNIT}\s*(?:resolution|pixels?|pixel size|scale|grid)\b", re.I),
]
_COMPOSITE_PATTERN = re.compile(
    r"\b(median|mean|average|mosaic|mode)\b(?:\s+composite)?|\b(max|min)(?:imum)?\s+composite\b", re.I
)

_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august",
           "september", "october", "november", "december")
_MONTH = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_YEAR = r"(?:19[89]\d|20\d{2})"
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                 "nine": 9, "ten": 10, "a": 1, "few": 3}
_DATE_PATTERNS = [
    re.compile(rf"\b(?:from|between)?\s*{_MONTH}(?:\s+{_YEAR})?\s*(?:to|until|till|and|-|–)\s*{_MONTH}\s+{_YEAR}\b", re.I),
    re.compile(rf"\b(?:from|between)\s+{_YEAR}\s*(?:to|until|till|and|-|–)\s*{_YEAR}\b", re.I),
    re.compile(rf"\b{_YEAR}\s*(?:-|–|to)\s*{_YEAR}\b", re.I),
    re.compile(rf"\b{_MONTH}\s+{_YEAR}\b", re.I),
    re.compile(r"\b(?:the\s+)?(?:last|past|previous|this|next)\s+(?:\d+\s+|(?:one|two|three|four|five|six|seven|eight|nine|ten|few)\s+)?"
               r"(?:years?|months?|weeks?|days?|summers?|winters?|springs?|autumns?|monsoons?|seasons?|decades?)\b", re.I),
    re.compile(rf"\b(?:in|during|for|since)\s+{_YEAR}\b", re.I),
    re.compile(rf"\b{_YEAR}\b"),
]

# Words after which a place name usually follows; used to recover lower-case places.
_PLACE_CUES = re.compile(r"\b(?:in|for|of|around|near|over|at|across|within|from|and)\s+", re.I)
_NOT_PLACE = re.compile(
    rf"^(?:the|a|an|my|this|that|last|past|next|every|each|all|some|{_MONTH}|{_YEAR}|\d+)$", re.I
)


# ----------------------------------------------------------------------------- extractor
class QueryEntityExtractor(IEntityExtractor):
    def __init__(self, use_spacy: bool = True, today: date | None = None):
        self._use_spacy = use_spacy
        self._nlp = None
        self._spacy_failed = False
        self._today = today

    # ------------------------------------------------------------------ API
    def extract(self, text: str) -> list[EntityDTO]:
        text = text or ""
        domain = self._domain_entities(text)
        taken = [(e.start, e.end) for e in domain if e.label in ("DATASET", "PROCESS", "BAND")]

        places, dates = self._spacy_places_and_dates(text, taken)
        places = _merge_spans(places, [e for e in self._cue_places(text) if not _overlaps(e, taken)])
        dates = _merge_spans(dates, self._pattern_dates(text))

        general = [e for e in places + dates if not _overlaps(e, taken)]
        entities = domain + general
        entities.sort(key=lambda e: (e.start, e.label))
        return entities

    # ------------------------------------------------------------ domain terms
    def _domain_entities(self, text: str) -> list[EntityDTO]:
        found: list[EntityDTO] = []
        found += _match_aliases(text, _DATASET_PATTERNS, "DATASET")
        found += _match_aliases(text, _PROCESS_PATTERNS, "PROCESS")
        processes = [e for e in found if e.label == "PROCESS"]
        # "water" inside "water bodies" adds nothing once the process is known
        found += [e for e in _match_aliases(text, _ANALYSIS_PATTERNS, "ANALYSIS") if not _overlaps_any(e.start, e.end, processes)]

        for m in _BAND_PATTERN.finditer(text):
            found.append(EntityDTO("BAND", m.group(0), m.group(1), m.start(), m.end()))

        cloud = None
        for pattern in _CLOUD_PATTERNS:
            cloud = cloud or pattern.search(text)
        if cloud and 0 <= int(cloud.group(1)) <= 100:
            found.append(EntityDTO("CLOUD_COVER", cloud.group(0).strip(), str(int(cloud.group(1))), cloud.start(), cloud.end()))
        elif (free := _CLOUD_FREE.search(text)):
            found.append(EntityDTO("CLOUD_COVER", free.group(0), str(CLOUD_FREE_PERCENT), free.start(), free.end()))

        for pattern in _RESOLUTION_PATTERNS:
            if (m := pattern.search(text)):
                metres = float(m.group(1)) * (1000 if m.group(2).lower().startswith("k") else 1)
                if metres >= 1:
                    found.append(EntityDTO("RESOLUTION", m.group(0).strip(), str(round(metres)), m.start(), m.end()))
                break

        if (m := _COMPOSITE_PATTERN.search(text)):
            word = (m.group(1) or m.group(2)).lower()
            value = {"average": "mean"}.get(word, word)
            found.append(EntityDTO("COMPOSITE", m.group(0), value, m.start(), m.end()))
        return found

    # --------------------------------------------------------- places and dates
    def _spacy_places_and_dates(self, text: str, taken) -> tuple[list[EntityDTO], list[EntityDTO]]:
        nlp = self._load_spacy()
        if nlp is None:
            return [], []
        places, dates = self._run_spacy(nlp, text)
        places = [e for e in places if not _overlaps(e, taken) and not _is_domain_phrase(e.text)]
        if not places:
            # spaCy needs capitals; retry with likely place words capitalised (same offsets).
            # Only words after a place cue were capitalised, so names spaCy files under
            # ORG / NORP / PERSON there ("Sahiwal and Okara") are taken as places too.
            places, _ = self._run_spacy(nlp, _capitalise_after_cues(text), extra_labels=RETRY_PLACE_LABELS)
            places = [
                EntityDTO("PLACE", text[p.start:p.end], p.value, p.start, p.end)
                for e in places for p in _split_places(e)
                if not _overlaps(p, taken) and not _is_domain_phrase(p.text)
            ]
        return places, dates

    def _run_spacy(self, nlp, text: str, extra_labels=()) -> tuple[list[EntityDTO], list[EntityDTO]]:
        places, dates = [], []
        for ent in nlp(text).ents:
            if ent.label_ in PLACE_LABELS or ent.label_ in extra_labels:
                places.append(EntityDTO("PLACE", ent.text, ent.text.strip(), ent.start_char, ent.end_char))
            elif ent.label_ == "DATE":
                dates.append(EntityDTO("DATE", ent.text, _date_value(ent.text, self._today_or_now()),
                                       ent.start_char, ent.end_char))
        return places, dates

    def _pattern_dates(self, text: str) -> list[EntityDTO]:
        spans: list[EntityDTO] = []
        for pattern in _DATE_PATTERNS:
            for m in pattern.finditer(text):
                entity = EntityDTO("DATE", m.group(0).strip(), _date_value(m.group(0), self._today_or_now()),
                                   m.start() + (len(m.group(0)) - len(m.group(0).lstrip())), m.end())
                if not _overlaps(entity, [(s.start, s.end) for s in spans]):
                    spans.append(entity)
        return spans

    def _cue_places(self, text: str) -> list[EntityDTO]:
        """Without spaCy: capitalised words after 'in / for / around ...'."""
        places = []
        for cue in _PLACE_CUES.finditer(text):
            words = re.match(r"((?:[A-Z][\w'-]*)(?:\s+[A-Z][\w'-]*){0,2})", text[cue.end():])
            if words and not _NOT_PLACE.match(words.group(1).split()[0]) and not _is_domain_phrase(words.group(1)):
                start = cue.end()
                places.append(EntityDTO("PLACE", words.group(1), words.group(1), start, start + len(words.group(1))))
        return places

    def _load_spacy(self):
        if not self._use_spacy or self._spacy_failed:
            return None
        if self._nlp is None:
            try:
                import spacy

                self._nlp = spacy.load(SPACY_MODEL, disable=["lemmatizer"])
            except Exception as exc:  # not installed / model missing: patterns still work
                log.warning("spaCy model %s unavailable (%s); using pattern-based entities only.", SPACY_MODEL, exc)
                self._spacy_failed = True
                return None
        return self._nlp

    def _today_or_now(self) -> date:
        return self._today or date.today()


# ----------------------------------------------------------------------------- helpers
def _match_aliases(text: str, patterns: list[tuple[re.Pattern, str]], label: str) -> list[EntityDTO]:
    found: list[EntityDTO] = []
    for pattern, value in patterns:
        for m in pattern.finditer(text):
            if not _overlaps_any(m.start(), m.end(), found):
                found.append(EntityDTO(label, m.group(0), value, m.start(), m.end()))
    return found


def _split_places(entity: EntityDTO) -> list[EntityDTO]:
    """'Sahiwal and Okara' -> 'Sahiwal', 'Okara' (offsets kept)."""
    parts = []
    for m in re.finditer(r"\b(?!and\b)[A-Za-z][\w'-]*(?:\s+(?!and\b)[A-Za-z][\w'-]*)*", entity.text, re.I):
        piece = m.group(0)
        offset = entity.start + m.start()
        parts.append(EntityDTO("PLACE", piece, piece[:1].upper() + piece[1:], offset, offset + len(piece)))
    return parts or [entity]


def _overlaps_any(start: int, end: int, entities: list[EntityDTO]) -> bool:
    return any(start < e.end and e.start < end for e in entities)


def _overlaps(entity: EntityDTO, spans: list[tuple[int, int]]) -> bool:
    return any(entity.start < end and start < entity.end for start, end in spans)


def _merge_spans(primary: list[EntityDTO], extra: list[EntityDTO]) -> list[EntityDTO]:
    """Union of both lists; where spans overlap, the longer one is kept."""
    merged = list(primary)
    for entity in extra:
        clashing = [e for e in merged if entity.start < e.end and e.start < entity.end]
        if all((entity.end - entity.start) > (e.end - e.start) for e in clashing):
            merged = [e for e in merged if e not in clashing] + [entity]
    return merged


def _capitalise_after_cues(text: str) -> str:
    """'temperature of lahore' -> 'temperature of Lahore' (length unchanged)."""
    chars = list(text)
    for cue in _PLACE_CUES.finditer(text):
        for word in list(re.finditer(r"[A-Za-z][\w'-]*", text[cue.end():]))[:3]:
            if _NOT_PLACE.match(word.group(0)) or _is_domain_word(word.group(0)):
                break
            position = cue.end() + word.start()
            chars[position] = chars[position].upper()
    return "".join(chars)


_DOMAIN_WORDS = {
    w.lower()
    for phrases in (*DATASET_ALIASES.values(), *PROCESS_ALIASES.values(), *ANALYSIS_KEYWORDS.values())
    for phrase in phrases
    for w in re.split(r"[\s\-]+", phrase)
} | {"using", "with", "and", "or", "to", "from", "between", "during", "since", "data", "imagery", "images",
     "for", "in", "of", "around", "near", "over", "at", "across", "within", "by", "on", "via", "show", "get"}


_SENSOR_WORDS = {"modis", "landsat", "sentinel", "copernicus", "era5", "jrc", "aqua", "terra", "gee",
                 "google", "earth", "engine"}


def _is_domain_word(word: str) -> bool:
    return word.lower() in _DOMAIN_WORDS or word.lower() in _SENSOR_WORDS


def _is_domain_phrase(phrase: str) -> bool:
    """True when every word is a dataset / process / sensor word (e.g. spaCy calling "MODIS" a place)."""
    words = re.findall(r"[A-Za-z0-9]+", phrase)
    return bool(words) and all(_is_domain_word(w) or w.isdigit() for w in words)


def _month_number(name: str) -> int:
    return next(i for i, month in enumerate(_MONTHS, start=1) if month.startswith(name.lower()[:3]))


def _date_value(text: str, today: date) -> str:
    """Explicit ranges as 'YYYY-MM-DD/YYYY-MM-DD'; '' when the phrase needs real interpretation."""
    lowered = text.lower()
    years = [int(y) for y in re.findall(_YEAR, lowered)]
    months = re.findall(rf"\b{_MONTH}\b", lowered)

    if months and years:
        first, last = _month_number(months[0]), _month_number(months[-1])
        end_year = years[-1]
        start_year = years[0] if len(years) > 1 else (end_year if first <= last else end_year - 1)
        start = date(start_year, first, 1)
        end = date(end_year, last, monthrange(end_year, last)[1])
        return f"{start.isoformat()}/{end.isoformat()}"
    if years and not months:
        end = today if re.search(r"\bsince\b", lowered) else date(max(years), 12, 31)
        return f"{date(min(years), 1, 1).isoformat()}/{end.isoformat()}"

    relative = re.search(r"\b(?:last|past|previous)\s+(?:(\d+|\w+)\s+)?(years?|months?)\b", lowered)
    if relative:
        count_text = relative.group(1)
        count = int(count_text) if count_text and count_text.isdigit() else _NUMBER_WORDS.get(count_text or "", 1)
        months_back = count * (12 if relative.group(2).startswith("year") else 1)
        year, month = divmod(today.year * 12 + today.month - 1 - months_back, 12)
        start = date(year, month + 1, min(today.day, monthrange(year, month + 1)[1]))
        return f"{start.isoformat()}/{today.isoformat()}"
    return ""


def format_entity_hints(entities: list[EntityDTO]) -> str:
    """Block appended to the query so Gemini sees what the classifier found."""
    if not entities:
        return ""
    lines = []
    for e in entities:
        value = f" -> {e.value}" if e.value and e.value.lower() != e.text.lower() else ""
        lines.append(f"- {e.label}: \"{e.text}\"{value}")
    return "\n\nEntities recognised in this request (the user's own words):\n" + "\n".join(lines)


def date_range(entities: list[EntityDTO]) -> tuple[date | None, date | None]:
    """Widest explicit range among the DATE entities."""
    starts, ends = [], []
    for e in entities:
        if e.label == "DATE" and "/" in e.value:
            first, last = e.value.split("/")
            starts.append(date.fromisoformat(first))
            ends.append(date.fromisoformat(last))
    return (min(starts), max(ends)) if starts else (None, None)
