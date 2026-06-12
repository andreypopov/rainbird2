"""Constants for the Rain Bird IQ4 integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "rainbird_iq4"

DATA_CLIENT = "client"
DATA_COORDINATOR = "coordinator"
DATA_FRONTEND_REGISTERED = "frontend_registered"

CONF_DEFAULT_DURATION = "default_duration"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_NAME = "Rain Bird IQ4"
DEFAULT_DURATION_MINUTES = 6
DEFAULT_SCAN_INTERVAL_MINUTES = 5
MIN_SCAN_INTERVAL_MINUTES = 1

DEFAULT_UPDATE_INTERVAL = timedelta(minutes=DEFAULT_SCAN_INTERVAL_MINUTES)

SERVICE_START_STATION = "start_station"
SERVICE_STOP_STATION = "stop_station"
SERVICE_STOP_ALL = "stop_all"
SERVICE_SET_RAIN_DELAY = "set_rain_delay"

ATTR_CONTROLLER_ID = "controller_id"
ATTR_DURATION = "duration"
ATTR_IS_GROUP_START = "is_group_start"
ATTR_STATION_ID = "station_id"
ATTR_DAYS = "days"

MANUFACTURER = "Rain Bird"
FRONTEND_URL_PATH = "/rainbird_iq4_static"
CARD_FILENAME = "rainbird-iq4-card.js"
