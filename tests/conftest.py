"""Test isolation: never read a developer's local `.env` during the suite."""

from __future__ import annotations

import os

# `app.config` loads `<repo>/.env` at import time for local runs. A developer's
# file must not change test behaviour, so disable that loader before any test
# module imports the app.
os.environ.setdefault("TIJORI_DISABLE_DOTENV", "1")
