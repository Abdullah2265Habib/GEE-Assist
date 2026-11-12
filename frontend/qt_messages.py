"""Hide Qt warnings that are known to be harmless; every other message is shown as before.

Qt Multimedia's FFmpeg backend prints "QObject::disconnect: wildcard call disconnects
from destroyed signal of QFFmpeg::..." while the intro video's player shuts down.
They come from inside Qt (the player is stopped properly), and Qt's logging rules
cannot single them out, so they are filtered here by their text.
"""

from __future__ import annotations

import sys

from PyQt6.QtCore import qInstallMessageHandler

HARMLESS_PREFIXES = (
    "QObject::disconnect: wildcard call disconnects from destroyed signal of QFFmpeg::",
)

_previous = None
_installed = None  # kept so Python does not collect the handler Qt calls


def is_harmless(message: str) -> bool:
    return message.startswith(HARMLESS_PREFIXES)


def install_message_filter() -> None:
    """Drop the harmless messages; hand the rest to the previous handler (or stderr)."""
    global _previous, _installed

    def handler(kind, context, message: str) -> None:
        if is_harmless(message):
            return
        if _previous is not None:
            _previous(kind, context, message)
        else:
            sys.stderr.write(message + "\n")

    _installed = handler
    _previous = qInstallMessageHandler(handler)
