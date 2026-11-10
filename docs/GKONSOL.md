# gkonsol — the GEE-Assist command line

gkonsol is a terminal built into GEE-Assist. Everything you can do with the mouse in the
signed-in window can also be done by typing a command: checking your account and session,
verifying the Google Earth Engine sign-in, filling and submitting the parameter form,
downloading datasets with a live progress bar and live speed, and more.

> **gkonsol commands work only inside GEE-Assist.**
> They are not Windows commands: typing `gee verify` or `download start` in Windows Terminal,
> PowerShell or cmd does nothing useful. The reverse is also true: Windows and PowerShell
> commands (`dir`, `cd`, `python`, `pip`, `earthengine` …) do not work inside gkonsol, which
> says so when you try one.

---

## Contents

1. [Opening, resizing and closing the terminal](#1-opening-resizing-and-closing-the-terminal)
2. [Typing commands](#2-typing-commands)
3. [A first session](#3-a-first-session)
4. [Command reference](#4-command-reference)
   - [General](#41-general) · [Account](#42-account) · [Earth Engine](#43-earth-engine) ·
     [Parameters](#44-parameters) · [Downloads](#45-downloads) · [App](#46-app)
5. [The live download views](#5-the-live-download-views)
6. [Every name and alias](#6-every-name-and-alias)
7. [Files gkonsol uses](#7-files-gkonsol-uses)
8. [Messages and what to do](#8-messages-and-what-to-do)
9. [For developers](#9-for-developers)

---

## 1. Opening, resizing and closing the terminal

The terminal sits **below the page, to the right of the side bar**, like the terminal panel
in VS Code. It is hidden until you open it.

| To … | Do this |
|---|---|
| Open or hide the terminal | Click **Terminal** in the side bar (the `>_` icon), or **View → Terminal**, or press **Ctrl+`** |
| Make it taller or shorter | Drag the line between the page and the terminal |
| Give it the whole window | Click **⌃** (Maximise) in the terminal's header, drag the line to the top, or type `panel max` |
| Give the page its room back | Click **⌄** (Restore), drag the line down, or type `panel restore` |
| Set an exact height | `panel height 400` |
| Clear the output | Click the bin in the header, press **Ctrl+L**, or type `clear` |
| Hide it | Click **×** in the header, press **Ctrl+`**, or type `exit` |

- The side bar's Terminal button is highlighted while the terminal is open, and
  **View → Terminal** is ticked.
- Hiding the terminal keeps its output, its history and a running command.
- The height you leave it at is remembered the next time GEE-Assist starts.
- The terminal uses the app's theme (light, dark blue-green or dark grey).

## 2. Typing commands

### The prompt

```
ayesha@gkonsol ~/downloads $
```

The prompt shows who is signed in and which page the window shows: `~` is the dashboard,
`~/query` the Query Input page, `~/downloads` the Downloads page and `~/account` the
account page. It changes when you change page, with the mouse or with `open`.

Type a command after the prompt and press **Enter**. The command and what it prints stay
in the terminal above the next prompt; until the output fills the terminal, the prompt
follows the last line, and after that it stays at the bottom while the output scrolls.

### Words, quotes and options

The rules are the same for every command.

| Rule | Example |
|---|---|
| Words are separated by spaces | `download start 2` |
| Quotes (`"…"` or `'…'`) keep spaces inside one word | `form set output "D:\GEE data"` |
| A backslash is an ordinary character, so Windows paths need no escaping | `form aoi file C:\areas\lahore.geojson` |
| `--name value`, `--name=value` and `-n value` give an option a value | `users list --page 2`, `users list -p 2` |
| `--flag` or `-f` switches a flag on; flags can be combined | `download start -d`, `-dy` |
| A negative number is a value, not an option | `form aoi bbox -74.05 40.68 -73.90 40.82` |
| After `--`, every word is a value | `echo -- --not-an-option` |
| `ask` and `echo` take the rest of the line exactly as typed | `ask what's the NDVI of Lahore in 2024?` |

In this document, `UPPERCASE` words are values you type, `[brackets]` mark what is
optional and `a|b` means one of them.

### Keys

| Key | What it does |
|---|---|
| **Enter** | Runs the line (or answers the question being asked) |
| **↑ / ↓** | Goes through the commands typed before; ↓ past the newest brings back what you were typing |
| **Tab** | Completes the word at the cursor: commands, subcommands, options, and values gkonsol knows (dataset keys, bands of the chosen dataset, download ids, page names, themes …). When several things match, it completes as far as they agree; pressing Tab again lists them |
| **Ctrl+C** | Copies the selected text. With nothing selected, **stops the running command**, or drops the line you are typing |
| **Ctrl+L** | Clears the terminal |
| **Esc** | Empties the line |
| **Ctrl+`** | Hides (or shows) the terminal |

You can also select text in the output with the mouse and copy it with **Ctrl+C** or the
right-click menu. Clicking the output without selecting puts the cursor back on the
prompt line.

### History

Commands are kept between sessions (the last 500). Besides ↑ and ↓:

| Type | Runs |
|---|---|
| `!!` | The last command again |
| `!12` | Command number 12 of `history` |
| `!-2` | The command before the last |
| `!gee` | The last command that started with `gee` |
| `!! --detach` | The last command with `--detach` added |

gkonsol prints the command a reference stood for before running it.

### Commands that take time

Some commands wait for a server (`gee verify`, `session verify`), and some keep running
until you stop them (`download watch`, `download speed`). While a command runs, the prompt
shows a spinner and what it is waiting for, for example
`⠙ Checking Earth Engine…  (Ctrl+C to stop)`. Press **Ctrl+C** to stop it. Stopping
`download watch` stops the *watching*, not the download.

### Questions

Commands that cannot be undone ask first, in place of the prompt:

```
Sign out of GEE-Assist? [y/N]
```

Type `y` (or `yes`) and Enter to go ahead. Anything else, or just Enter, keeps the default
(the capital letter: `N` here). Tab offers the answers. Add `-y` to the command to skip
the question: `signout -y`.

### When something is wrong

Mistakes are explained in red, with the usage of the command and where its help is:

```
ayesha@gkonsol ~ $ form set cloud 150
✗ The cloud cover must be from 0 to 100.
  → Usage: form set FIELD VALUE...   ·   help form set
```

Mistyped command names get suggestions:

```
ayesha@gkonsol ~ $ downlod
✗ 'downlod' is not a gkonsol command.
  → Did you mean 'download' or 'downloads'?
  → Type 'help' to see every command.
```

## 3. A first session

Check that everything is set up, describe what you need, download it, and watch it arrive:

```
doctor                                        # server, session, Gemini, download folder, Earth Engine
gee login                                     # only if gee verify / doctor said you are not signed in
form set dataset landsat-8                    # or: ask NDVI of Lahore in summer 2024 from Landsat 8
form set dates 2024-06-01 2024-08-31
form aoi bbox 74.20 31.40 74.45 31.60
form set analysis Vegetation NDVI
form validate
form submit                                   # kept as request #1
download start                                # starts it and shows the live progress bar
```

Everything typed in the terminal shows in the parameter form on the Query Input page
as well, and the new download appears on the Downloads page.

---

## 4. Command reference

The commands are grouped as `help` lists them. Each command has its own help page in the
terminal too: `help <command>`, e.g. `help download start`.

### 4.1 General

#### `help`

```
help [COMMAND [SUBCOMMAND]]
```

Without a command, lists every command by group. With one, shows its usage, description,
options, subcommands and examples. Commands for administrators are listed only for
administrators. Alias: `?`.

```
help                    every command
help download           the download command and its subcommands
help form set           the fields 'form set' can set
```

#### `clear`

```
clear
```

Removes everything printed so far (a progress bar that is being redrawn stays).
Same as **Ctrl+L** or the bin button. Alias: `cls`.

#### `history`

```
history [COUNT] [--clear]
```

Lists the last `COUNT` commands (20 if not given), numbered from the start of the
history so that `!<number>` runs one again. `--clear` forgets all of them.

```
ayesha@gkonsol ~ $ history 3
12  form submit
13  download start
14  history 3
Run one again with !<number> (e.g. !14), or the last one with !!.
```

#### `echo`

```
echo TEXT
```

Prints `TEXT` exactly as typed (quotes included).

#### `version`

```
version
```

Shows the versions of gkonsol, Python, PyQt/Qt, the Earth Engine API and the Gemini API,
and the operating system. Alias: `about`.

#### `exit`

```
exit
```

Hides the terminal. Its output, history and running command are kept; open it again
from the side bar or with **Ctrl+`**. Alias: `close`. (To quit GEE-Assist, use `quit`.)

### 4.2 Account

#### `whoami`

```
whoami
```

Prints who is signed in and their role.

```
ayesha@gkonsol ~ $ whoami
ayesha  Ayesha Khan  ·  User
```

#### `user`, `user info`

```
user [info] [-r | --refresh]
```

Shows your account: name, username, email (and whether it is verified), phone, role,
whether the account is active, sign-in method, member since, last sign-in and user id.
They are shown as they were when you signed in; `--refresh` loads them from the
authentication server first. `user` alone is `user info`. Alias: `account`.

#### `session`, `session show`

```
session [show]
```

Shows your sign-in session: who is signed in, the authentication server, whether
"Keep me signed in" saved the session on this computer and until when, and when the
access token is renewed.

```
ayesha@gkonsol ~ $ session
  Signed in as    ayesha (Ayesha Khan)
  Server          http://localhost:8000
  Kept signed in  Yes, until 17 Nov 2026, 19:20 (in 6 d 23 h)
  Access token    renews in 28 min
  Refresh token   held
'session verify' asks the server whether the session is still valid.
```

#### `session verify`

```
session verify
```

Sends your access token to the authentication server (renewing it first if needed) and
reports whether the server accepts it, with the time it took. If the session has expired,
it says so and suggests signing in again. Alias: `session check`.

#### `signout`

```
signout [-y | --yes]
```

Signs out of GEE-Assist after asking (`-y` skips the question). The sign-in screen opens
and a session saved with "Keep me signed in" is forgotten. Alias: `logout`.

#### `users` (administrators)

`users` and its subcommands are for administrators only; for other users they are not
listed and refused. `USER` is a username (any letter case) or a user id. `users` alone is
`users list`.

##### `users list`

```
users list [-p N | --page N] [--size N]
```

Lists user accounts, 20 per page (`--size` from 1 to 100): username, name, email, role,
whether the account is active, and the last sign-in. Alias: `users ls`.

```
users list            the first page
users list -p 2       the second page
```

##### `users show`

```
users show USER
```

Shows one user's details, like `user info`.

##### `users role`

```
users role USER admin|user [-y]
```

Makes a user an administrator (`admin`) or an ordinary user (`user`), after asking. The
server refuses to let administrators change their own role.

##### `users enable`

```
users enable USER
```

Lets a disabled user sign in again.

##### `users disable`

```
users disable USER [-y]
```

Stops a user from signing in, after asking.

##### `users open`

```
users open
```

Opens the **Manage users** window.

#### `server`, `server status`

```
server [status]
```

Checks that the authentication server (GEE-Assist-Backend, `AUTH_API_URL` in `.env`)
answers, and how long it took. If it does not, it says how to start it. Alias:
`server ping`.

### 4.3 Earth Engine

Downloads come from Google Earth Engine. It needs a Google Cloud project registered for
Earth Engine (`GEE_PROJECT` in `.env`) and a sign-in on this computer.

#### `gee`, `gee status`

```
gee [status]
```

Shows the Cloud project and whether Earth Engine can be used right now (with the time
the check took). If it cannot, `gee verify` shows why.

#### `gee verify` — the Earth Engine sign-in and set-up check

```
gee verify
```

Checks the Earth Engine set-up step by step and says, for each step that does not pass,
how to fix it:

| Step | What is checked |
|---|---|
| Earth Engine library | `earthengine-api` is installed (its version is shown) |
| Cloud project (GEE_PROJECT) | `GEE_PROJECT` is set in `.env` |
| Sign-in on this computer | A saved Earth Engine sign-in exists (`~/.config/earthengine/credentials`), or a service account key in `GOOGLE_APPLICATION_CREDENTIALS` |
| Connection | Earth Engine accepts the sign-in and the project (with the time it took) |
| Test request | Earth Engine computes a small request (with the time it took) |

Each step is marked `✓` (passed), `!` (works, but look at it), `✗` (failed) or `–`
(skipped because an earlier step failed). Aliases: `gee check`, `gee auth`.

```
ayesha@gkonsol ~ $ gee verify
Checking the Earth Engine set-up step by step…
✓ Earth Engine library         earthengine-api 1.7.48
✓ Cloud project (GEE_PROJECT)  my-gee-project
! Sign-in on this computer     No saved Earth Engine sign-in at C:\Users\you\.config\earthengine\credentials; other Google credentials are tried.
  → Sign in to Earth Engine on this computer (earthengine authenticate).
  → Sign in from here: gee login
✗ Connection                   Earth Engine is not signed in on this computer. Run `earthengine authenticate` once, then try again.  (1204 ms)
  → Sign in from here: gee login
– Test request                 Needs a connection.
✗ 1 step failed: fix it, then run 'gee verify' again.
```

When everything passes, the last line is `✓ Earth Engine is ready: datasets can be downloaded.`

#### `gee login`

```
gee login [--no-browser]
```

Signs this computer in to Earth Engine, the same way `earthengine authenticate` does, but
from inside GEE-Assist:

1. your browser opens Google's sign-in page (the address is also printed, to open by
   hand if the browser does not open — or only printed, with `--no-browser`);
2. sign in with the Google account of your Cloud project and allow access;
3. the browser shows "Signed in to Google Earth Engine"; GEE-Assist saves the sign-in in
   `~/.config/earthengine/credentials` and runs the `gee verify` checks.

The terminal waits up to 5 minutes for the browser. **Ctrl+C** cancels. Alias: `gee signin`.

#### `gee project`

```
gee project
```

Shows the Cloud project Earth Engine uses (`GEE_PROJECT` in `.env`), or how to set one
if it is missing. To use another project, change `.env` and restart GEE-Assist.

#### `datasets`, `datasets list`

```
datasets [list] [--category TEXT] [--analysis TYPE]
```

Lists the datasets that can be downloaded: key, name, scale, the dates they cover,
whether they have a cloud filter, and the analyses they support. `--category` keeps those
whose category contains `TEXT` (e.g. `radar`, `optical`, `land`); `--analysis` keeps those
that support `Water`, `Vegetation`, `LST` or `LULC`. Aliases: `ds`, `datasets ls`.

```
datasets list --analysis LST      datasets with land surface temperature
```

#### `datasets show`

```
datasets show DATASET
```

Shows one dataset: key, Earth Engine collection, category, satellite, scale, dates, cloud
filter, default composite, every band (`*` marks the ones chosen by default) and the
processes of each analysis it supports. `DATASET` is a key (`landsat8_l2`), a common name
(`landsat-8`, `s2`, `era5`) or the start of a key, if only one key starts with it.

```
ayesha@gkonsol ~ $ datasets show s2
Sentinel-2 Surface Reflectance (L2A)
  Key           sentinel2_sr
  Collection    COPERNICUS/S2_SR_HARMONIZED
  Category      Optical (multispectral)
  Satellite     Sentinel-2
  Scale         10 m / pixel
  Available     2017-03-28 → present
  Cloud filter  yes (CLOUDY_PIXEL_PERCENTAGE)
  Composite     median by default
  Bands         B1 B2* B3* B4* B5 B6 B7 B8* B8A B9 B11* B12 SCL QA60
    * chosen by default
  Analyses
    Water: NDWI, MNDWI, WaterBodyDetection, WaterAreaEstimation
    Vegetation: NDVI, EVI, SAVI, GNDVI
```

### 4.4 Parameters

The `form` commands fill the **parameter form on the Query Input page**, the same form you
see there: what you set in the terminal appears in the form, and what you enter in the form
shows in `form show`. Values are checked before they are set, so a value the form could
not hold (a band of another dataset, a date the dataset does not cover) is refused with a
message instead of being changed silently.

#### `form`, `form show`

```
form [show] [--json]
```

Shows every field of the form. `--json` prints the parameters as JSON. Alias: `params`.

```
ayesha@gkonsol ~/query $ form show
Parameter form
  Dataset      landsat8_l2  (Landsat 8 Collection 2 Level-2)
  Bands        SR_B4, SR_B5
  Scale        30 m / pixel
  Cloud cover  at most 20 %
  Composite    median
  Area         Rectangle (Polygon, 4 vertices) · lon 74.2000 → 74.4500, lat 31.4000 → 31.6000
  Dates        2024-06-01 → 2024-08-31  (92 days)
  Projection   WGS 84 (EPSG:4326, degrees)
  Save to      D:\Projects\FYP\GEE-Assist\workspace\downloads
  Analysis     Vegetation: NDVI
```

#### `form set`

```
form set FIELD VALUE...
```

Sets one field. The fields:

| Field (also) | Values | Notes |
|---|---|---|
| `dataset` | `KEY` | A key, a common name or the start of a key (see `datasets list`). Choosing a dataset sets its default bands, scale, cloud cover and composite, as the form does; dates outside the dataset are moved inside it |
| `bands` | `BAND...`, `default`, `all` | Bands of the chosen dataset, separated by spaces or commas; any letter case |
| `scale` | `METRES` | Pixel size, 1–100000 (`30` or `30m`) |
| `cloud` (`cloud-cover`, `clouds`) | `PERCENT` | 0–100 (`20` or `20%`); only datasets with a cloud filter |
| `composite` | `median`, `mean`, `mosaic`, `min`, `max`, `mode` | How the images of the date range are combined |
| `dates` | `START END` | `YYYY-MM-DD`; start on or before end, not in the future, within the dataset's dates |
| `start` | `DATE` | Only the start date |
| `end` | `DATE` | Only the end date |
| `crs` (`projection`) | `EPSG:4326` (`wgs84`), `utm` (`auto`), `EPSG:3857` (`mercator`) | The GeoTIFF's projection; `utm` is the UTM zone of the area, in metres |
| `output` (`folder`, `save-to`) | `FOLDER` | A full folder path; it is created when the download starts. Quotes are optional for paths with spaces |
| `analysis` | `none`, or `TYPE [PROCESS...]` | `Water`, `Vegetation`, `LST` or `LULC` (if the dataset supports it) with its processes; `none` = download only |
| `processes` | `PROCESS...` | Processes of the chosen analysis, e.g. `NDVI EVI` |

```
form set dataset landsat8_l2                Landsat 8, with its default bands and scale
form set bands B4 B8                        only the red and near-infrared bands
form set dates 2024-06-01 2024-08-31        summer 2024
form set cloud 10                           leave out scenes more than 10 % cloudy
form set output "D:\GEE data"               save downloads there
form set analysis Vegetation NDVI EVI       compute NDVI and EVI
```

Tab completes the field names and, for each field, its values.

#### `form aoi` — the area of interest

`form aoi` (alias `form area`) alone shows the area. Coordinates are WGS 84 degrees.
After an area is set, gkonsol prints a rough size of the download.

##### `form aoi show`

```
form aoi show
```

Shows the area: its name, shape, number of vertices and extent.

##### `form aoi bbox`

```
form aoi bbox W S E N
```

A rectangle from its west and east longitudes and south and north latitudes. West must be
less than east and south less than north; negative numbers work as they are. Aliases:
`form aoi rect`, `form aoi rectangle`.

```
ayesha@gkonsol ~ $ form aoi bbox 74.20 31.40 74.45 31.60
✓ area = Rectangle (Polygon, 4 vertices) · lon 74.2000 → 74.4500, lat 31.4000 → 31.6000
  ≈ 4.7 MB in 1 chunk of 500 MB  ·  'form estimate' for more
```

##### `form aoi circle`

```
form aoi circle LON LAT RADIUS
```

A circle around a point, as a 64-sided polygon. `RADIUS` is `500` (metres), `500m` or
`2.5km`, at most 500 km.

```
form aoi circle 73.08 31.42 10km            10 km around Faisalabad
```

##### `form aoi file`

```
form aoi file PATH
```

Imports a GeoJSON file (`.geojson` or `.json`, up to 20 MB: a Polygon or MultiPolygon, as
a geometry, a Feature or a FeatureCollection), like **Import GeoJSON…** in the form. The
form switches to "GeoJSON file".

##### `form aoi geojson`

```
form aoi geojson JSON
```

Uses GeoJSON typed (or pasted) on the line: a Polygon or MultiPolygon geometry, or a
Feature holding one.

```
form aoi geojson {"type":"Polygon","coordinates":[[[73,31],[73.1,31],[73.1,31.1],[73,31]]]}
```

##### `form aoi clear`

```
form aoi clear
```

Removes the area.

#### `form validate`

```
form validate
```

Checks the form exactly as **Submit Parameters** does, but keeps nothing. Each problem is
listed with the command that fixes it. Alias: `form check`.

```
ayesha@gkonsol ~ $ form validate
✗ Area: Specify an Area of Interest: import a GeoJSON file, or draw a rectangle, circle or polygon on the map.
  → form aoi bbox <W> <S> <E> <N>  (or circle / file)
```

#### `form estimate`

```
form estimate
```

Estimates the download: its grid in pixels, the number of bands, its size (float32
GeoTIFF), how many chunks it is split into at the current chunk size, and how many Earth
Engine requests it takes. Needs an area and at least one band.

```
ayesha@gkonsol ~ $ form estimate
  Grid          791 × 738 px
  Bands         2
  Size          about 4.7 MB (float32 GeoTIFF)
  Chunks        1 chunk of 500 MB
  GEE requests  1 (GEE allows 48.0 MB per request)
```

#### `form wizard`

```
form wizard
```

Fills the form step by step, asking one question per field and showing its current value
in `[brackets]`:

```
Dataset [sentinel2_sr]:
Bands [B2 B3 B4 B8 B11]:
Scale in metres [10]:
Max cloud cover % [20]:            (only for datasets with a cloud filter)
Composite [median]:
Start date [2026-08-10]:
End date [2026-11-10]:
Area: bbox W S E N | circle LON LAT RADIUS | file PATH [none]:
Projection: EPSG:4326 | utm | EPSG:3857 [EPSG:4326]:
Save to folder [D:\…\workspace\downloads]:
Analysis: none | TYPE PROCESS... [none]:
```

Press **Enter** to keep a value, type a new one (the same values as `form set`), or `q`
to stop (what was entered so far stays in the form). A wrong answer is explained and asked
again. At the end the form is shown and checked; if it is valid, the wizard asks
`Submit these parameters now? [Y/n]`. Alias: `form fill`.

#### `form submit`

```
form submit
```

The same as **Submit Parameters**: checks the form and, if it is valid, keeps it as a
request (it appears under **Kept Requests**) and tells you its number. Problems are listed
as in `form validate`, and shown in the form too.

```
ayesha@gkonsol ~/query $ form submit
✓ Parameters accepted and kept as request #1.
  → download start 1  downloads it
```

#### `form reset`

```
form reset [-y]
```

Puts every field back to its default, after asking.

#### `ask`

```
ask TEXT
```

The same as **Chat with Gemini**: describe the data you need in plain words, and Gemini,
helped by GEE-Assist's own recogniser of places, dates, datasets and analyses, fills the
form. gkonsol shows what it recognised, which parts of the form were filled, any notes,
and Gemini's question if the request was unclear. Quotes are not needed, and apostrophes
are fine. Aliases: `gemini`, `nl`.

```
ask NDVI of Lahore for summer 2024 from Sentinel-2
ask water bodies near Mangla Dam in 2023
```

Check the values afterwards (`form show`), then `form submit`.

### 4.5 Downloads

#### `requests`, `requests list`

```
requests [list]
```

Lists the kept requests (parameter forms submitted with **Submit Parameters** or
`form submit`), numbered from 1 as in the **Kept Requests** list: the dataset and purpose,
dates, area, and whether it can be downloaded. Kept requests last until GEE-Assist closes.
Aliases: `req`, `kept`, `requests ls`.

#### `requests show`

```
requests show [N]
```

Shows the parameters of request `N` (the latest if not given).

#### `requests download`

```
requests download [N] [-d | --detach]
```

Downloads request `N`; the same as `download start N`.

#### Naming a download

The `download` subcommands that act on one download take an optional `DOWNLOAD`:

| `DOWNLOAD` | Means |
|---|---|
| *(nothing)* | The running download; if none runs, the latest unfinished one |
| `2` or `#2` | Number 2 of `download list` |
| `3f9a` | The download whose id starts with `3f9a` (at least 4 characters, as with git) |
| `last` | The latest download |
| `running` | The running download (an error if none runs) |

`download` alone is `download list`. Aliases: `dl`, `downloads`.

#### `download start`

```
download start [REQUEST] [-d | --detach]
```

Downloads kept request number `REQUEST` (the latest that can be downloaded, if not given)
from Earth Engine: it prints the download's id, size, number of chunks and folder, then
**follows its progress live** (see [the live download views](#5-the-live-download-views))
until it completes, pauses or fails. **Ctrl+C** stops following; the download goes on, and
`download watch` follows it again. `--detach` starts it without following.

```
download start                  the latest kept request
download start 2 -d             request #2, in the background
```

#### `download list`

```
download list [-a | --all]
```

Lists the downloads, numbered, with their id, name, status, a small progress bar,
size, current speed and time left. Cancelled downloads are listed only with `--all`.
Alias: `download ls`.

```
#   ID        NAME                            STATUS     PROGRESS           SIZE                  SPEED    ETA
#1  a17c0e9d  Sentinel-2_74.3250_31.5000_20…  completed  ██████████ 100.0%  1.0 GB / 1.0 GB           —      —
#2  8be04d1c  Sentinel-2_73.0500_31.0500_8b…  running    ████▉░░░░░  48.7%  974.0 MB / 2.0 GB  4.2 MB/s  03:41
#3  c41d77e0  Sentinel-2_73.0500_31.0500_c4…  paused     █████░░░░░  50.0%  500.0 MB / 1.0 GB         —      —
```

#### `download show`

```
download show [DOWNLOAD]
```

Shows a download in detail: id, folder, progress, chunks merged, bytes received from Earth
Engine, the merged file so far, start and finish times, speed and time left while it runs,
the result file once complete, any error — and a table of its chunks with their status,
size, bytes downloaded and retries. Alias: `download info`.

#### `download watch`

```
download watch [DOWNLOAD]
```

Follows a download live: progress bar, speed now / average / peak, time left, chunks,
bytes received, disk usage and a speed sparkline, redrawn twice a second until the download
stops running. **Ctrl+C** stops watching (the download goes on). Aliases:
`download progress`, `download follow`.

#### `download speed`

```
download speed [DOWNLOAD]
```

Shows the download speed live as a chart, like Task Manager (see below). Without
`DOWNLOAD`, it shows whatever is downloading and keeps going (at 0 B/s when nothing is)
until **Ctrl+C**; with one, until that download stops running.

#### `download pause`

```
download pause [DOWNLOAD]
```

Pauses a running or queued download. Finished parts are kept.

#### `download resume`

```
download resume [DOWNLOAD] [-d | --detach]
```

Continues a paused download (a failed one is retried) and follows its progress, unless
`--detach`. Alias: `download continue`.

#### `download retry`

```
download retry [DOWNLOAD] [-d | --detach]
```

Fetches the failed chunks of a failed download again and follows its progress, unless
`--detach`.

#### `download cancel`

```
download cancel [DOWNLOAD] [-y]
```

Cancels a download and **deletes its files**, after asking.

#### `download open`

```
download open [DOWNLOAD]
```

Opens the download's folder in File Explorer.

#### `download chunk-size`

```
download chunk-size [MB]
```

Shows the chunk size new downloads are split into, or changes it (1–102400 MB, e.g. `250`
or `250MB`). Downloads already running keep their chunks. The same as **Options →
Download chunk size…**.

### 4.6 App

#### `open`

```
open PAGE
```

Shows a page: `dashboard` (also `home`), `query` (`query-input`, `form`, `parameters`),
`downloads` (`download`) or `account` (`profile`). Alias: `goto`.

#### `sidebar`

```
sidebar [on|off|toggle]
```

Opens (`on`), collapses (`off`) or switches (`toggle`, or nothing) the side bar. `show` /
`hide`, `open` / `close` and `expand` / `collapse` work too. Same as **Ctrl+B**.

#### `fullscreen`

```
fullscreen [on|off|toggle]
```

Switches full screen on or off. Same as **F11**.

#### `theme`

```
theme [NAME] [-y]
```

Without a name, lists the themes and marks the current one. With one — `light`,
`dark-green` or `dark-grey` — asks, then restarts GEE-Assist in that theme (a running
download is paused and can be resumed).

#### `panel`

```
panel
panel max
panel restore
panel height PX
```

Resizes the terminal. `panel` alone shows its height and whether it is maximised.
`panel max` gives it the whole window (aliases `maximize`, `expand`); `panel restore`
gives the page its room back (aliases `compress`, `normal`); `panel height` sets its
height in pixels (110–4000, `400` or `400px`).

#### `config`

```
config
```

Shows the settings GEE-Assist runs with: the authentication server and its timeout, how
long "Keep me signed in" lasts, the Earth Engine project, the Gemini model and whether its
key is set, the download folder, chunk size, retries per chunk and theme, with the names
of the `.env` settings. Changes to `.env` take effect when GEE-Assist starts again.
Alias: `settings`.

#### `doctor`

```
doctor
```

Checks everything gkonsol can check and says how to fix what does not work: the
authentication server, your session, the Gemini key, the download folder (it can be
written to, and how much space is free; a warning below 5 GB), and every
[Earth Engine step](#gee-verify--the-earth-engine-sign-in-and-set-up-check).
Alias: `checkup`.

```
ayesha@gkonsol ~ $ doctor
GEE-Assist check-up
✓ Authentication server  http://localhost:8000 answered.  (23 ms)
✓ Session                Signed in as ayesha.  (41 ms)
✓ Gemini                 GEMINI_API_KEY is set.
✓ Download folder        D:\Projects\FYP\GEE-Assist\workspace\downloads  (182.4 GB free)
Earth Engine
✓ Earth Engine library         earthengine-api 1.7.48
✓ Cloud project (GEE_PROJECT)  my-gee-project
✓ Sign-in on this computer     Saved sign-in: C:\Users\you\.config\earthengine\credentials
✓ Connection                   Connected with project 'my-gee-project'.  (812 ms)
✓ Test request                 Earth Engine answered in 230 ms.  (230 ms)
✓ Everything works.
```

#### `quit`

```
quit [-y]
```

Quits GEE-Assist, after asking. A running download is paused and continues the next time
it is resumed.

---

## 5. The live download views

### Progress (`download start`, `download watch`, `download resume`, `download retry`)

```
⇣ Sentinel-2_74.3250_31.5000_2024-06-01_2024-08-31  RUNNING
  █████████████████████████████▎░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   48.7%  974.0 MB / 2.0 GB
  speed 4.2 MB/s  ·  average 3.9 MB/s  ·  peak 6.1 MB/s  ·  ETA 04:06
  chunks 1 / 4  ·  received 1.0 GB  ·  on disk 990.0 MB
  speed ▁▁▃▄▅▆▇█▇▆▆▆▇▆▅▆▆▇▆▆  last 10 s
```

| Part | Meaning |
|---|---|
| Name and status | The download's folder name; `RUNNING`, `QUEUED` (waiting for the one ahead), `PAUSED`, `FAILED`, `COMPLETED` or `CANCELLED` |
| Bar | Share of the expected size downloaded, to an eighth of a character; amber when paused, red when failed |
| `974.0 MB / 2.0 GB` | Downloaded / expected size |
| `speed` | The speed over the last 2 seconds, as on the Downloads page |
| `average` | The average since the download (re)started |
| `peak` | The highest speed seen while watching |
| `ETA` | Time left, from the progress of the last 20 seconds |
| `chunks` | Chunks merged into the result / chunks in all |
| `received` | Bytes received from Earth Engine, including requests that were retried |
| `on disk` | Size of the download's files right now |
| `merging` | Speed of the merge running at the moment (shown only while one runs) |
| Sparkline | The speed of the last seconds, newest on the right |

It is redrawn in place twice a second. Messages printed meanwhile appear above it. When
the download stops running, the last drawing stays and a line says what happened:
complete (with the result file), paused (and how to resume), failed (with the reason and
how to retry) or cancelled.

### Speed chart (`download speed`)

```
Download speed  Sentinel-2_74.3250_31.5000_2024-06-01_2024-08-31
  6.1 MB/s ┤             ▁█▂                 ▁█▂                 ▁█▂
           │            ▄███▇▃▅▇▁ ▂▆█▄▁     ▄███▇▃▅▇▁ ▂▆█▄▁     ▄███▇▃▅▇▁ ▂▆█▄▁
           │          ▃▇█████████▇█████   ▃▇█████████▇█████   ▃▇█████████▇█████
           │         ▁█████████████████  ▁█████████████████  ▁█████████████████
           │         ██████████████████  ██████████████████  ██████████████████
           │        ▆██████████████████ ▆██████████████████ ▆██████████████████
     0 B/s ┼───────────────────────────────────────────────────────────────────
            34 s ago                                                        now
  now 4.2 MB/s  ·  average 3.9 MB/s  ·  peak 6.1 MB/s    Ctrl+C stops
```

One column per half second, newest on the right; the top of the chart is the peak speed.
The wider the terminal, the further back the chart goes (up to two minutes).

---

## 6. Every name and alias

| Command | Also |
|---|---|
| `help` | `?` |
| `clear` | `cls` |
| `version` | `about` |
| `exit` | `close` |
| `user` | `account` |
| `session verify` | `session check` |
| `signout` | `logout` |
| `users list` | `users ls` |
| `server status` | `server ping` |
| `gee verify` | `gee check`, `gee auth` |
| `gee login` | `gee signin` |
| `datasets` | `ds` |
| `datasets list` | `datasets ls` |
| `form` | `params` |
| `form aoi` | `form area` |
| `form aoi bbox` | `form aoi rect`, `form aoi rectangle` |
| `form validate` | `form check` |
| `form wizard` | `form fill` |
| `ask` | `gemini`, `nl` |
| `requests` | `req`, `kept` |
| `requests list` | `requests ls` |
| `download` | `dl`, `downloads` |
| `download list` | `download ls` |
| `download show` | `download info` |
| `download watch` | `download progress`, `download follow` |
| `download resume` | `download continue` |
| `open` | `goto` |
| `panel max` | `panel maximize`, `panel expand` |
| `panel restore` | `panel compress`, `panel normal` |
| `config` | `settings` |
| `doctor` | `checkup` |

Commands with subcommands run a default when typed alone: `user` → `user info`,
`session` → `session show`, `users` → `users list`, `server` → `server status`,
`gee` → `gee status`, `datasets` → `datasets list`, `form` → `form show`,
`form aoi` → `form aoi show`, `requests` → `requests list`, `download` → `download list`,
`panel` → its size.

## 7. Files gkonsol uses

| File | What is in it |
|---|---|
| `workspace/gkonsol.json` | The command history (last 500) and the terminal's height. Delete it to start afresh. Like the rest of `workspace/`, it is not committed to git |
| `~/.config/earthengine/credentials` | The Earth Engine sign-in saved by `gee login` (or `earthengine authenticate`) |
| `.env` | The settings `config` shows (`AUTH_API_URL`, `GEE_PROJECT`, `GEMINI_API_KEY` …) |
| `workspace/download_settings.json` | Chunk size and retries, changed by `download chunk-size` |

## 8. Messages and what to do

| Message | What to do |
|---|---|
| `'…' is not a gkonsol command.` | Check the spelling (a suggestion is shown if one is close), or type `help`. Windows and PowerShell commands do not work in gkonsol |
| `Unknown option --…` / `Too many arguments` | See the usage line printed under it, or `help <command>` |
| `A command is still running. Press Ctrl+C to stop it.` | Wait for it, or press **Ctrl+C** |
| `'users …' is for administrators only.` | Ask an administrator |
| `Cannot reach the authentication server at …` | Start GEE-Assist-Backend (`uvicorn app.main:app`), or set `AUTH_API_URL` in `.env` |
| `Your session has expired.` | `signout`, then sign in again |
| `GEE_PROJECT is not set in .env.` | Register a Cloud project at https://code.earthengine.google.com/register, set `GEE_PROJECT=your-project-id` in `.env`, restart GEE-Assist |
| `Earth Engine is not signed in on this computer.` | `gee login` |
| `The Earth Engine API is not enabled for project …` | Open the link in the message, enable the API, wait a few minutes, `gee verify` |
| `Google did not sign you in to Earth Engine (access_denied).` | Run `gee login` again and allow access |
| `The browser did not come back within 5 minutes.` | Run `gee login` again |
| `No requests are kept yet.` | Fill the form and `form submit` (or press Submit Parameters) |
| `Type at least 4 characters of the download's id.` | Use more of the id, or its number from `download list` |
| `Download failed: …` | Read the reason; `download retry` fetches the failed chunks again |

---

## 9. For developers

The terminal is in `frontend/gkonsol/`:

| File | What it does |
|---|---|
| `text.py` | Styled text (spans with a style name) and drawings made of characters: progress bar, sparkline, bar chart, tables |
| `parser.py` | Splits a line into words (quotes, Windows paths) and the words into options and arguments |
| `command.py` | `Command` (name, summary, handler, options, examples, aliases, subcommands) and the `Registry` |
| `effects.py` | What a running command can wait for: `Task` (a background call), `Sleep`, `Ask` |
| `runner.py` | Drives a command (a generator) one effect at a time; Ctrl+C raises `Interrupted` in it |
| `output.py` | The `Writer` commands print with, and live (redrawn) regions |
| `history.py` | The history and `workspace/gkonsol.json` |
| `ports.py` | What commands can do in the app (`AppPort`), in the panel (`PanelPort`) and in the form (`FormPort`); `MemoryForm` for tests |
| `help.py` | The help pages, built from the command definitions |
| `shell.py` | Runs typed lines, reports errors, completes words |
| `commands/` | The commands, one module per group, registered in `commands/__init__.py` |
| `view.py`, `prompt_line.py`, `panel.py`, `scheduler.py`, `colors.py` | The Qt widgets: output, input line, panel and the area that puts it under the page |
| `form_port.py` | Connects the form commands to the parameter form |

The backend gives the terminal what it needs through `IBusinessFacade`: `check_form`,
`get_session_info`, `check_gee_setup` and the browser sign-in (`begin_gee_sign_in`,
`complete_gee_sign_in`, `cancel_gee_sign_in`; see `backend/data/clients/gee_sign_in.py`).

### Adding a command

1. Write a handler `def _hello(ctx: Context, args: Args) -> None` that prints with `ctx.out`
   and uses `ctx.facade`, `ctx.app`, `ctx.form` or `ctx.panel`. For anything that takes
   time, make it a generator and `yield task(fn, *args, label="…")`, `yield Sleep(seconds)`
   or `answer = yield Ask("Question? [y/N]")`.
2. Register it in its group's `register()` with a summary, `params`, options, `max_args` and
   examples: `help`, Tab completion and the usage line come from that.
3. Add tests (see `tests/test_gkonsol_*.py`; `tests/gkonsol_fakes.py` has a terminal with a
   fake backend) and a section in this document — `tests/test_gkonsol_docs.py` checks that
   every command is documented here.
