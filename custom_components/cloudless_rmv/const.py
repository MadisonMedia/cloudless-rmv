"""Constants for Cloudless RMV."""

from __future__ import annotations

DOMAIN = "cloudless_rmv"

API_BASE = "https://www.rmv.de/hapi"
OPEN_DATA_URL = "https://www.rmv.de/s/de/rmv-open-data"

ATTRIBUTION = "Daten: Rhein-Main-Verkehrsverbund (RMV), opendata.rmv.de"

# Config entry data
CONF_API_KEY = "api_key"
CONF_STOP = "stop"
CONF_DIRECTION = "direction"
CONF_WATCH = "watch"
CONF_CONNECTIONS = "connections"

# Options
CONF_WALK_MIN = "walk_min"
CONF_MAX_ROWS = "max_rows"
CONF_DURATION = "duration"
CONF_TRANSFER_BUFFER = "transfer_buffer"

DEFAULT_WALK_MIN = 5
DEFAULT_MAX_ROWS = 6
DEFAULT_DURATION = 90
DEFAULT_TRANSFER_BUFFER = 3

# Limits from the RMV terms of use (Nutzungsbedingungen, section 5b):
# at most 600 requests per hour and 5000 per day per API key.
HOURLY_LIMIT = 600
DAILY_LIMIT = 5000
# Stay clearly below the hard limits.
BUDGET_SAFETY = 0.85

# Debounce for manual/automatic refresh requests (seconds).
REFRESH_COOLDOWN = 15

CARD_URL = f"/{DOMAIN}/cloudless-rmv-card.js"
LOGO_URL = f"/{DOMAIN}/rmv-logo.png"
CARD_VERSION = "0.1.0"

PLATFORMS = ["sensor", "binary_sensor"]
