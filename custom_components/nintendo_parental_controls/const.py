"""Constants for the Nintendo Switch parental controls integration."""

DOMAIN = "nintendo_parental_controls"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_SESSION_TOKEN = "session_token"

BEDTIME_ALARM_MIN = "16:00"
BEDTIME_ALARM_MAX = "23:00"
BEDTIME_ALARM_DISABLE = "00:00"

BEDTIME_END_TIME_MIN = "05:00"
BEDTIME_END_TIME_MAX = "09:00"

# Nintendo accepts at most 60 minutes of extra playing time per request,
# or unlimited playing time for the rest of the day (-1).
BONUS_TIME_MIN = 5
BONUS_TIME_MAX = 60
BONUS_TIME_UNLIMITED = -1

CONF_PLAYING_HOLDOVER = "playing_holdover"
DEFAULT_PLAYING_HOLDOVER = 10
ATTR_LAST_INCREASE = "last_increase"

APP_SETUP_URL = (
    "https://www.nintendo.com/my/support/switch/parentalcontrols/app/setup.html"
)
