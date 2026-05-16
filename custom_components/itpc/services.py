"""Сервисы для ITPC интеграции."""
import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
import requests
import logging

from .const import DOMAIN, CONF_LOGIN, CONF_PASSWORD

_LOGGER = logging.getLogger(__name__)

SERVICE_SEND_VALUES = "send_values"

# Схема с необязательными полями
SERVICE_SCHEMA_SEND_VALUES = vol.Schema({
    vol.Optional('electric_day'): vol.Coerce(float),
    vol.Optional('electric_night'): vol.Coerce(float),
    vol.Optional('water_cold'): vol.Coerce(float),
    vol.Optional('water_hot'): vol.Coerce(float),
})

async def async_setup_services(hass: HomeAssistant):
    """Настройка сервисов."""
    
    async def send_values(call: ServiceCall):
        """Передача показаний (только указанные параметры)."""
        # Получаем только те параметры, которые были переданы
        data = call.data
        electric_day = data.get('electric_day')
        electric_night = data.get('electric_night')
        water_cold = data.get('water_cold')
        water_hot = data.get('water_hot')
        
        _LOGGER.info(f"Вызов службы send_values: день={electric_day}, ночь={electric_night}, ХВС={water_cold}, ГВС={water_hot}")
        
        for entry_id, entry_data in hass.data[DOMAIN].items():
            if 'data' in entry_data and entry_data['data']:
                counter_ids = entry_data['data'].get('counter_ids', {})
                config = entry_data.get('config', {})
                login = config.get(CONF_LOGIN)
                password = config.get(CONF_PASSWORD)
                
                if login and password and counter_ids:
                    _LOGGER.debug(f"Найдены ID счетчиков: {counter_ids}")
                    
                    # Передаём только те показания, которые присутствуют в вызове
                    result = await hass.async_add_executor_job(
                        send_values_to_api,
                        login,
                        password,
                        electric_day,
                        electric_night,
                        water_cold,
                        water_hot,
                        counter_ids
                    )
                    
                    # Отправляем уведомление (только с переданными значениями)
                    sent_values = {}
                    if electric_day is not None:
                        sent_values['electric_day'] = electric_day
                    if electric_night is not None:
                        sent_values['electric_night'] = electric_night
                    if water_cold is not None:
                        sent_values['water_cold'] = water_cold
                    if water_hot is not None:
                        sent_values['water_hot'] = water_hot
                    
                    await send_notification(hass, result, sent_values)
                    
                    if result.get('result') == "Показания успешно переданы":
                        _LOGGER.info("Показания успешно переданы")
                        await refresh_all_data(hass, entry_id, login, password)
                    else:
                        _LOGGER.error(f"Ошибка передачи показаний: {result.get('send_error', 'Неизвестная ошибка')}")
                    
                    break
                else:
                    _LOGGER.warning(f"Не найдены ID счетчиков или учетные данные для {entry_id}")
    
    async def refresh_all_data(hass, entry_id, login, password):
        """Обновление всех данных после передачи."""
        from . import get_data
        
        new_data = await hass.async_add_executor_job(
            get_data,
            login,
            password
        )
        
        if new_data.get('auth_success'):
            hass.data[DOMAIN][entry_id]['data'] = new_data
            
            for entity in hass.data[DOMAIN][entry_id].get('entities', []):
                if hasattr(entity, 'async_update'):
                    await entity.async_update()
            
            _LOGGER.info("Данные обновлены после передачи показаний")
    
    async def send_notification(hass, result, values):
        """Отправка уведомления в Home Assistant (только с переданными значениями)."""
        notification_id = "itpc_send_values_notification"
        
        if result.get('result') == "Показания успешно переданы":
            # Формируем сообщение только из переданных значений
            lines = []
            if 'electric_day' in values:
                lines.append(f"- ⚡ Электричество (день): {values['electric_day']} кВт⋅ч")
            if 'electric_night' in values:
                lines.append(f"- ⚡ Электричество (ночь): {values['electric_night']} кВт⋅ч")
            if 'water_cold' in values:
                lines.append(f"- 💧 Холодная вода: {values['water_cold']} м³")
            if 'water_hot' in values:
                lines.append(f"- 💧 Горячая вода: {values['water_hot']} м³")
            
            if not lines:
                message = "✅ Показания успешно переданы (без конкретных значений)"
            else:
                message = f"✅ Показания успешно переданы!\n\nПереданные показания:\n" + "\n".join(lines)
            
            title = "✅ Передача показаний ТРИЦ"
        else:
            error_msg = result.get('send_error', 'Неизвестная ошибка')
            message = f"❌ Ошибка передачи показаний!\n\nОшибка: {error_msg}"
            title = "❌ Ошибка передачи показаний ТРИЦ"
        
        await hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "message": message,
                "title": title,
                "notification_id": notification_id,
            },
            blocking=False,
        )
        
        _LOGGER.info(f"Уведомление отправлено: {title}")
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_VALUES,
        send_values,
        schema=SERVICE_SCHEMA_SEND_VALUES,
    )
    
    _LOGGER.info("Сервис itpc.send_values зарегистрирован")

async def async_unload_services(hass: HomeAssistant):
    """Выгрузка сервисов."""
    if hass.services.has_service(DOMAIN, SERVICE_SEND_VALUES):
        hass.services.async_remove(DOMAIN, SERVICE_SEND_VALUES)
        _LOGGER.info("Сервис itpc.send_values удален")

def send_values_to_api(login, password, electric_day, electric_night, water_cold, water_hot, counter_ids):
    """Отправка показаний в API (только для существующих счётчиков и указанных значений)."""
    lk_url = 'https://lk.itpc.ru/'
    lk_data = {}
    
    s = requests.Session()
    
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'ru-RU,ru;q=0.9',
        'Referer': lk_url,
        'X-Requested-With': 'XMLHttpRequest',
    })
    
    data_auth = {
        'login': login,
        'password': password,
        'submit': 'Войти'
    }
    
    try:
        # Авторизация
        login_response = s.post(lk_url, data=data_auth, timeout=30)
        
        if 'Неверный пользователь или пароль' in login_response.text:
            lk_data['error'] = 'Неверный логин или пароль'
            lk_data['auth_success'] = False
            lk_data['result'] = "Ошибка авторизации"
            lk_data['send_error'] = "Неверный логин или пароль"
            return lk_data
        
        # Получаем номер лицевого счета
        user_response = s.get('https://lk.itpc.ru/v2/user/', timeout=30)
        if user_response.status_code != 200:
            lk_data['result'] = "Ошибка получения данных пользователя"
            lk_data['send_error'] = f"HTTP {user_response.status_code}"
            return lk_data
            
        user_json = user_response.json()
        first_account = user_json.get('accounts', [{}])[0]
        ls_number = first_account.get('oid')
        
        if not ls_number:
            lk_data['result'] = "Не найден лицевой счет"
            lk_data['send_error'] = "Лицевой счет не найден"
            return lk_data
            
        lk_counter_url = f'https://lk.itpc.ru/v2/account/{ls_number}/counter/'
        
        # Формируем данные для отправки (только для указанных и существующих счётчиков)
        data_send = {}
        
        if electric_day is not None and counter_ids.get('id_electric_day'):
            data_send[counter_ids['id_electric_day']] = float(electric_day)
        elif electric_day is not None and not counter_ids.get('id_electric_day'):
            lk_data['warning_electric_day'] = "Счётчик Электричество (день) не найден, показания не отправлены"
        
        if electric_night is not None and counter_ids.get('id_electric_night'):
            data_send[counter_ids['id_electric_night']] = float(electric_night)
        elif electric_night is not None and not counter_ids.get('id_electric_night'):
            lk_data['warning_electric_night'] = "Счётчик Электричество (ночь) не найден, показания не отправлены"
        
        if water_cold is not None and counter_ids.get('id_water_cold'):
            data_send[counter_ids['id_water_cold']] = float(water_cold)
        elif water_cold is not None and not counter_ids.get('id_water_cold'):
            lk_data['warning_water_cold'] = "Счётчик холодной воды не найден, показания не отправлены"
        
        if water_hot is not None and counter_ids.get('id_water_hot'):
            data_send[counter_ids['id_water_hot']] = float(water_hot)
        elif water_hot is not None and not counter_ids.get('id_water_hot'):
            lk_data['warning_water_hot'] = "Счётчик горячей воды не найден, показания не отправлены"
        
        if not data_send:
            lk_data['result'] = "Показания не переданы (нет данных для отправки или все счётчики отсутствуют)"
            return lk_data
        
        _LOGGER.debug(f"Отправка данных: {data_send}")
        
        # Отправляем показания
        response = s.put(lk_counter_url, json=data_send, timeout=30)
        
        if response.status_code == 200:
            try:
                response_json = response.json()
                if response_json.get('status') == True:
                    lk_data['result'] = "Показания успешно переданы"
                    lk_data['send_success'] = True
                    _LOGGER.info("Показания успешно переданы")
                else:
                    lk_data['result'] = "Ошибка в передаче показаний"
                    lk_data['send_error'] = str(response_json)
                    lk_data['send_success'] = False
                    _LOGGER.error(f"Ошибка API: {response_json}")
            except Exception as e:
                lk_data['result'] = "Ошибка в передаче показаний"
                lk_data['send_error'] = f"Не удалось распарсить JSON: {str(e)}"
                lk_data['send_success'] = False
                _LOGGER.error(f"JSON ошибка: {e}")
        else:
            lk_data['result'] = "Ошибка в передаче показаний"
            lk_data['send_error'] = f"HTTP {response.status_code}: {response.text}"
            lk_data['send_success'] = False
            _LOGGER.error(f"HTTP ошибка: {response.status_code}")
    
    except requests.exceptions.Timeout:
        lk_data['result'] = "Ошибка: таймаут подключения"
        lk_data['send_error'] = "Превышено время ожидания ответа от сервера"
        lk_data['send_success'] = False
        _LOGGER.error("Таймаут при отправке показаний")
    except Exception as e:
        lk_data['result'] = f"Ошибка: {str(e)}"
        lk_data['send_error'] = str(e)
        lk_data['send_success'] = False
        _LOGGER.exception(f"Неожиданная ошибка: {e}")
    finally:
        s.close()
    
    return lk_data