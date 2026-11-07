"""Shared test set-up."""

import os

# The tests run in the light theme, whatever theme is saved on this computer.
os.environ.setdefault("GEE_ASSIST_THEME", "light")
