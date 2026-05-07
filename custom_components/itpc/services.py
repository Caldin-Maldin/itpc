"""Сервисы для ITPC интеграции."""
import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
import requests
import logging

from .const import DOMAIN, CONF_LOGIN, CONF_PASSWORD

_LOGGER = logging.getLogger(__name__)

SERVICE_SEND_VALUES = "send_values"

SERVICE_SCHEMA_SEND_VALUES = vol.Schema({
    vol.Required('electric_day'): vol.Coerce(float),
    vol.Required('electric_night'): vol.Coerce(float),
    vol.Required('water_cold'): vol.Coerce(float),
    vol.Required('water_hot'): vol.Coerce(float),
})

async def async_setup_services(hass: HomeAssistant):
    """Настройка сервисов."""
    
    async def send_values(call: ServiceCall):
        """Передача показаний."""
        electric_day = call.data.get('electric_day')
        electric_night = call.data.get('electric_night')
        water_cold = call.data.get('water_cold')
        water_hot = call.data.get('water_hot')
        
        _LOGGER.info(f"Вызов службы send_values: день={electric_day}, ночь={electric_night}, ХВС={water_cold}, ГВС={water_hot}")
        
        # Получаем данные для первой интеграции
        for entry_id, entry_data in hass.data[DOMAIN].items():
            if 'data' in entry_data and entry_data['data']:
                counter_ids = entry_data['data'].get('counter_ids', {})
                config = entry_data.get('config', {})
                login = config.get(CONF_LOGIN)
                password = config.get(CONF_PASSWORD)
                
                if login and password and counter_ids:
                    _LOGGER.debug(f"Найдены ID счетчиков: {counter_ids}")
                    
                    # Передаем показания
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
                    
                    # Отправляем уведомление
                    await send_notification(hass, result, {
                        'electric_day': electric_day,
                        'electric_night': electric_night,
                        'water_cold': water_cold,
                        'water_hot': water_hot
                    })
                    
                    if result.get('result') == "Показания успешно переданы":
                        _LOGGER.info("Показания успешно переданы")
                        # После успешной передачи обновляем данные
                        await refresh_all_data(hass, entry_id, login, password)
                    else:
                        _LOGGER.error(f"Ошибка передачи показаний: {result.get('send_error', 'Неизвестная ошибка')}")
                    
                    break
                else:
                    _LOGGER.warning(f"Не найдены ID счетчиков или учетные данные для {entry_id}")
    
    async def refresh_all_data(hass, entry_id, login, password):
        """Обновление всех данных после передачи."""
        from . import get_data
        
        # Получаем свежие данные
        new_data = await hass.async_add_executor_job(
            get_data,
            login,
            password
        )
        
        if new_data.get('auth_success'):
            # Обновляем данные в хранилище
            hass.data[DOMAIN][entry_id]['data'] = new_data
            
            # Обновляем все сенсоры
            for entity in hass.data[DOMAIN][entry_id].get('entities', []):
                if hasattr(entity, 'async_update'):
                    await entity.async_update()
            
            _LOGGER.info("Данные обновлены после передачи показаний")
    
    async def send_notification(hass, result, values):
        """Отправка уведомления в Home Assistant."""
        # Получаем название persistent_notification
        notification_id = "itpc_send_values_notification"
        
        if result.get('result') == "Показания успешно переданы":
            # Успешная передача
            message = f"""✅ Показания успешно переданы!

Переданные показания:
- ⚡ Электричество (день): {values['electric_day']} кВт⋅ч
- ⚡ Электричество (ночь): {values['electric_night']} кВт⋅ч
- 💧 Холодная вода: {values['water_cold']} м³
- 💧 Горячая вода: {values['water_hot']} м³

Данные успешно отправлены в личный кабинет ТРИЦ."""
            
            title = "✅ Передача показаний ТРИЦ"
            
        else:
            # Ошибка передачи
            error_msg = result.get('send_error', 'Неизвестная ошибка')
            
            message = f"""❌ Ошибка передачи показаний!

Не удалось передать показания:
- ⚡ Электричество (день): {values['electric_day']} кВт⋅ч
- ⚡ Электричество (ночь): {values['electric_night']} кВт⋅ч
- 💧 Холодная вода: {values['water_cold']} м³
- 💧 Горячая вода: {values['water_hot']} м³

Ошибка: {error_msg}

Проверьте подключение к интернету и попробуйте позже."""
            
            title = "❌ Ошибка передачи показаний ТРИЦ"
        
        # Отправляем ТОЛЬКО ОДНО уведомление через persistent_notification
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
    
    # Регистрируем сервис
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
    """Отправка показаний в API."""
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
        
        # Подготовка данных для отправки
        data_send = {}
        
        if counter_ids.get('id_water_cold'):
            data_send[counter_ids['id_water_cold']] = float(water_cold)
        if counter_ids.get('id_water_hot'):
            data_send[counter_ids['id_water_hot']] = float(water_hot)
        if counter_ids.get('id_electric_day'):
            data_send[counter_ids['id_electric_day']] = float(electric_day)
        if counter_ids.get('id_electric_night'):
            data_send[counter_ids['id_electric_night']] = float(electric_night)
        
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