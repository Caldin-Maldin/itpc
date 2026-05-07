"""Константы для интеграции ITPC."""
from homeassistant.const import Platform

DOMAIN = "itpc"
PLATFORMS = [Platform.SENSOR, Platform.BUTTON]  # Добавили BUTTON

CONF_LOGIN = "login"
CONF_PASSWORD = "password"

DEFAULT_SCAN_INTERVAL = 3600

# Атрибуты
ATTR_ACCOUNTS = "accounts"
ATTR_ADDRESS = "address"
ATTR_MAIN = "main"
ATTR_PENALTIES = "penalties"
ATTR_COUNTERS = "counters"
ATTR_OID = "oid"
ATTR_SERIAL = "serial"
ATTR_PREVIOUS = "previous"
ATTR_MODEL = "model"
ATTR_NEXT_VERIFICATION = "next_verification"

# Сервисы
SERVICE_SEND_VALUES = "send_values"

