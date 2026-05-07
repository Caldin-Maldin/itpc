"""Кнопки для ITPC интеграции."""
from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
import logging

from .const import DOMAIN, CONF_LOGIN, CONF_PASSWORD
from . import get_data

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Настройка кнопок."""
    entities = [ITPCRefreshButton(hass, entry)]
    async_add_entities(entities)

class ITPCRefreshButton(ButtonEntity):
    """Кнопка обновления данных."""

    def __init__(self, hass, entry):
        self.hass = hass
        self._entry = entry
        self._attr_name = "Обновить данные Личного кабинета"
        self._attr_unique_id = f"{entry.entry_id}_refresh_button"
        self._attr_icon = "mdi:refresh"

    @property
    def device_info(self):
        """Информация об устройстве."""
        user_data = self.hass.data[DOMAIN][self._entry.entry_id]['data'].get('user_data', {})
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": f"Личный кабинет {user_data.get('accounts', 'Неизвестно')}",
            "manufacturer": "ТРИЦ",
            "model": "Личный кабинет",
        }

    async def async_press(self) -> None:
        """Действие при нажатии кнопки."""
        _LOGGER.info("Обновление данных ТРИЦ по запросу пользователя")
        
        config = self.hass.data[DOMAIN][self._entry.entry_id]['config']
        login = config.get(CONF_LOGIN)
        password = config.get(CONF_PASSWORD)
        
        if not login or not password:
            _LOGGER.error("Нет учетных данных для обновления")
            return
        
        # Получаем свежие данные
        try:
            new_data = await self.hass.async_add_executor_job(
                get_data,
                login,
                password
            )
            
            if new_data.get('auth_success'):
                # Обновляем данные в хранилище
                self.hass.data[DOMAIN][self._entry.entry_id]['data'] = new_data
                
                # Обновляем все сенсоры
                for entity in self.hass.data[DOMAIN][self._entry.entry_id].get('entities', []):
                    if hasattr(entity, 'async_update'):
                        await entity.async_update()
                
                _LOGGER.info("Данные ТРИЦ успешно обновлены")
            else:
                _LOGGER.error(f"Ошибка обновления данных: {new_data.get('error', 'Неизвестная ошибка')}")
        except Exception as e:
            _LOGGER.error(f"Исключение при обновлении: {e}")