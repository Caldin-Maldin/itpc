"""Сенсоры для ITPC интеграции."""
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
import logging

from .const import DOMAIN, CONF_LOGIN, CONF_PASSWORD, ATTR_ACCOUNTS, ATTR_ADDRESS, ATTR_MAIN, ATTR_PENALTIES
from . import get_data

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Настройка сенсоров."""
    data = hass.data[DOMAIN][entry.entry_id]['data']
    
    entities = []
    
    # Сенсор общей задолженности
    if data.get('user_data', {}).get('main') is not None:
        debt_sensor = ITPCDebtSensor(hass, entry, data['user_data'])
        entities.append(debt_sensor)
    
    # Сенсор квитанции
    payment_sensor = ITPCPaymentSensor(hass, entry, data)
    entities.append(payment_sensor)
    
    # Сенсоры для счетчиков
    if data.get('counter_data', {}).get('counters'):
        for counter in data['counter_data']['counters']:
            counter_sensor = ITPCCounterSensor(hass, entry, counter)
            entities.append(counter_sensor)
    
    # Сохраняем сенсоры в hass.data
    if 'entities' not in hass.data[DOMAIN][entry.entry_id]:
        hass.data[DOMAIN][entry.entry_id]['entities'] = []
    hass.data[DOMAIN][entry.entry_id]['entities'].extend(entities)
    
    async_add_entities(entities)
    
    # Принудительное обновление после создания
    for entity in entities:
        await entity.async_update()

def extract_value(current_data):
    """Извлечение числового значения из показания счетчика."""
    if current_data is None:
        return 0
    
    if isinstance(current_data, dict):
        value = current_data.get('value', 0)
        if isinstance(value, str):
            try:
                return float(value.replace(',', '.'))
            except ValueError:
                return 0
        return float(value) if value is not None else 0
    
    if isinstance(current_data, (int, float)):
        return float(current_data)
    
    if isinstance(current_data, str):
        try:
            return float(current_data.replace(',', '.'))
        except ValueError:
            return 0
    
    return 0

class ITPCDebtSensor(SensorEntity):
    """Сенсор общей задолженности."""

    def __init__(self, hass, entry, user_data):
        self.hass = hass
        self._entry = entry
        self._user_data = user_data
        self._attr_name = "Общая задолженность"
        self._attr_unique_id = f"{entry.entry_id}_debt"
        self._attr_should_poll = False
        self._attr_icon = "mdi:currency-rub"
        self._update_attributes()

    def _update_attributes(self):
        main_value = self._user_data.get('main', 0)
        if isinstance(main_value, dict):
            main_value = extract_value(main_value)
        
        self._attr_native_value = float(main_value) if main_value else 0
        self._attr_extra_state_attributes = {
            ATTR_ACCOUNTS: self._user_data.get('accounts'),
            ATTR_ADDRESS: self._user_data.get('address'),
            ATTR_MAIN: self._user_data.get('main'),
            ATTR_PENALTIES: self._user_data.get('penalties')
        }

    @property
    def native_unit_of_measurement(self):
        return "₽"

    @property
    def device_info(self):
        accounts_number = self._user_data.get('accounts', 'Неизвестно')
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": f"Личный кабинет {accounts_number}",
            "manufacturer": "ТРИЦ",
            "model": "Личный кабинет",
        }

    async def async_update(self):
        _LOGGER.debug("Обновление сенсора задолженности")
        config = self.hass.data[DOMAIN][self._entry.entry_id]['config']
        
        try:
            data = await self.hass.async_add_executor_job(
                get_data,
                config[CONF_LOGIN],
                config[CONF_PASSWORD]
            )
            
            if data.get('auth_success') and data.get('user_data'):
                self._user_data = data['user_data']
                self._update_attributes()
                self.async_write_ha_state()
        except Exception as e:
            _LOGGER.error(f"Ошибка обновления задолженности: {e}")

class ITPCPaymentSensor(SensorEntity):
    """Сенсор для квитанции на оплату."""

    def __init__(self, hass, entry, data):
        self.hass = hass
        self._entry = entry
        self._data = data
        self._attr_name = "Квитанция на оплату"
        self._attr_unique_id = f"{entry.entry_id}_payment"
        self._attr_should_poll = False
        self._attr_icon = "mdi:file-document-outline"
        self._update_attributes()

    def _update_attributes(self):
        payment = self._data.get('payment')
        web_link = self._data.get('web_link_payment')
        
        if web_link and payment:
            self._attr_native_value = "Доступна"
        else:
            self._attr_native_value = "Не доступна"
        
        self._attr_extra_state_attributes = {
            'payment_ticket': payment,
            'payment_link': web_link,
            'account': self._data.get('user_data', {}).get('accounts')
        }

    @property
    def device_info(self):
        user_data = self._data.get('user_data', {})
        accounts_number = user_data.get('accounts', 'Неизвестно')
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": f"Личный кабинет {accounts_number}",
            "manufacturer": "ТРИЦ",
            "model": "Личный кабинет",
        }

    async def async_update(self):
        _LOGGER.debug("Обновление сенсора квитанции")
        config = self.hass.data[DOMAIN][self._entry.entry_id]['config']
        
        try:
            data = await self.hass.async_add_executor_job(
                get_data,
                config[CONF_LOGIN],
                config[CONF_PASSWORD]
            )
            
            if data.get('auth_success'):
                self.hass.data[DOMAIN][self._entry.entry_id]['data'] = data
                self._data = data
                self._update_attributes()
                self.async_write_ha_state()
                _LOGGER.debug(f"Квитанция: ticket={data.get('payment')}, link={data.get('web_link_payment')}")
        except Exception as e:
            _LOGGER.error(f"Ошибка обновления квитанции: {e}")

class ITPCCounterSensor(SensorEntity):
    """Сенсор счетчика."""

    def __init__(self, hass, entry, counter):
        self.hass = hass
        self._entry = entry
        self._counter = counter
        self._attr_name = counter.get('name')
        self._attr_unique_id = f"{entry.entry_id}_{counter.get('oid')}"
        self._attr_should_poll = False
        
        name = counter.get('name', '')
        if 'Электричество' in name:
            self._attr_icon = "mdi:lightning-bolt"
        elif 'водоснабжение' in name:
            self._attr_icon = "mdi:water"
        else:
            self._attr_icon = "mdi:counter"
        
        self._update_attributes()

    def _update_attributes(self):
        current_value = self._counter.get('current')
        numeric_value = extract_value(current_value)
        
        self._attr_native_value = numeric_value
        
        self._attr_extra_state_attributes = {
            'oid': self._counter.get('oid'),
            'serial': self._counter.get('serial'),
            'current_value': numeric_value,
            'current_raw': current_value,
            'previous': self._counter.get('previous'),
            'model': self._counter.get('model'),
            'next_verification': self._counter.get('next_verification')
        }

    @property
    def native_unit_of_measurement(self):
        name = self._counter.get('name', '')
        if 'Электричество' in name:
            return "кВт⋅ч"
        elif 'водоснабжение' in name:
            return "м³"
        return None

    @property
    def device_info(self):
        user_data = self.hass.data[DOMAIN][self._entry.entry_id]['data'].get('user_data', {})
        accounts_number = user_data.get('accounts', 'Неизвестно')
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": f"Личный кабинет {accounts_number}",
            "manufacturer": "ТРИЦ",
            "model": "Личный кабинет",
        }

    async def async_update(self):
        _LOGGER.debug(f"Обновление сенсора {self._attr_name}")
        config = self.hass.data[DOMAIN][self._entry.entry_id]['config']
        
        try:
            data = await self.hass.async_add_executor_job(
                get_data,
                config[CONF_LOGIN],
                config[CONF_PASSWORD]
            )
            
            if data.get('auth_success') and data.get('counter_data'):
                for counter in data['counter_data']['counters']:
                    if counter.get('oid') == self._counter.get('oid'):
                        self._counter = counter
                        self._update_attributes()
                        self.async_write_ha_state()
                        break
        except Exception as e:
            _LOGGER.error(f"Ошибка обновления {self._attr_name}: {e}")