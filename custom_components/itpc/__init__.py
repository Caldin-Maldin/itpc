"""Интеграция ITPC для Home Assistant."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
import requests
import logging

from .const import DOMAIN, PLATFORMS, CONF_LOGIN, CONF_PASSWORD
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Настройка интеграции из config entry."""
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    
    data = await hass.async_add_executor_job(
        get_data, 
        entry.data[CONF_LOGIN], 
        entry.data[CONF_PASSWORD]
    )
    
    if data.get('auth_success'):
        hass.data[DOMAIN][entry.entry_id] = {
            'config': entry.data,
            'data': data,
            'entities': []
        }
        
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        await async_setup_services(hass)
        
        device_registry = dr.async_get(hass)
        accounts_number = data.get('user_data', {}).get('accounts', 'Неизвестно')
        
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Личный кабинет {accounts_number}",
            manufacturer="ТРИЦ",
            model="Личный кабинет",
            sw_version="1.0"
        )
        
        _LOGGER.info(f"Интеграция ТРИЦ успешно настроена для {accounts_number}")
        return True
    else:
        _LOGGER.error(f"Ошибка авторизации ТРИЦ: {data.get('error')}")
        return False

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Выгрузка интеграции."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        if entry.entry_id in hass.data[DOMAIN]:
            hass.data[DOMAIN].pop(entry.entry_id)
        await async_unload_services(hass)
    
    return unload_ok

def get_data(login_param, password_param):
    """Получение данных."""
    def autorisation_get_info():
        login = login_param
        password = password_param
        lk_url = 'https://lk.itpc.ru/'
        lk_user_url = 'https://lk.itpc.ru/v2/user/'
        lk_data = {}

        s = requests.Session()
        
        s.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
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
            login_response = s.post(lk_url, data=data_auth, timeout=30)

            if 'Неверный пользователь или пароль' in login_response.text:
                lk_data['error'] = 'Неверный логин или пароль'
                lk_data['auth_success'] = False
                return lk_data  

            else:
                lk_data['auth_success'] = True
                lk_data['error'] = 'Ошибок нет. Авторизация успешна'
                
            try:
                user_response = s.get(lk_user_url, timeout=30)

                if user_response.status_code == 200:
                    lk_data['auth'] = 'success'            

                    user_json = user_response.json()
                    
                    first_account = user_json['accounts'][0] if user_json.get('accounts') else {}
                    
                    lk_data['user_data'] = {
                        'id': user_json.get('id'),
                        'accounts': first_account.get('oid'),  
                        'address': first_account.get('address'),
                        'main': first_account.get('debt', {}).get('main'),  
                        'penalties': first_account.get('debt', {}).get('penalties')
                    }

                    ls_number = first_account.get('oid')
                    
                    if ls_number:
                        lk_counter_url = f'https://lk.itpc.ru/v2/account/{ls_number}/counter/'
                        lk_payment_url = f'https://lk.itpc.ru/v2/account/{ls_number}/payment/'
                    else:
                        lk_data['error'] = 'Не удалось получить номер лицевого счета'
                        return lk_data
                    
                else:
                    lk_data['auth'] = f'API error: {user_response.status_code}'
                    lk_data['response_text'] = user_response.text
                    return lk_data  
                    
            except Exception as e:
                lk_data['error'] = str(e)
                lk_data['status_code'] = 500 
                return lk_data

            # Получение данных счетчиков
            try:
                counter_response = s.get(lk_counter_url, timeout=30)

                if counter_response.status_code == 200:
                    counter_json = counter_response.json()

                    transformed_counters = []

                    id_electric_day = None
                    id_electric_night = None
                    id_water_cold = None
                    id_water_hot = None
                    
                    for counter in counter_json.get('counters', []):
                        counter_name = counter.get('service', {}).get('name')
                        
                        transformed_counter = {
                            'name': counter_name,
                            'oid': counter.get('oid'),
                            'serial': counter.get('serial'),
                            'current': counter.get('current'),
                            'previous': counter.get('previous')
                        }
                        
                        if counter.get('model'):
                            transformed_counter['model'] = counter.get('model')
                        
                        if counter.get('next_verification'):
                            transformed_counter['next_verification'] = counter.get('next_verification')
                        
                        transformed_counters.append(transformed_counter)

                        if counter_name == 'Электричество (день)':
                            id_electric_day = counter.get('oid')
                        elif counter_name == 'Электричество (ночь)':
                            id_electric_night = counter.get('oid')
                        elif counter_name == 'Холодное водоснабжение':
                            id_water_cold = counter.get('oid')
                        elif counter_name == 'Горячее водоснабжение':
                            id_water_hot = counter.get('oid')
                    
                    lk_data['counter_data'] = {
                        'counters': transformed_counters
                    }
                    
                    lk_data['counter_ids'] = {
                        'id_electric_day': id_electric_day,
                        'id_electric_night': id_electric_night,
                        'id_water_cold': id_water_cold,
                        'id_water_hot': id_water_hot
                    }

                else:
                    lk_data['counter_auth'] = f'API error: {counter_response.status_code}'
                    lk_data['counter_response_text'] = counter_response.text
                    
            except Exception as e:
                lk_data['counter_error'] = str(e)
                lk_data['counter_status_code'] = 500

            # Получение данных о платежах/квитанциях
            try:
                payment_response = s.get(lk_payment_url, timeout=30)

                if payment_response.status_code == 200:
                    payment_json = payment_response.json()
                    
                    # Пробуем разные варианты получения tickets
                    tickets = []
                    if 'payment' in payment_json and 'tickets' in payment_json['payment']:
                        tickets = payment_json['payment'].get('tickets', [])
                    elif 'tickets' in payment_json:
                        tickets = payment_json.get('tickets', [])
                    elif 'data' in payment_json and 'tickets' in payment_json['data']:
                        tickets = payment_json['data'].get('tickets', [])
                    
                    if tickets:
                        lk_data['payment'] = tickets[0]
                        lk_data['web_link_payment'] = f'https://lk.itpc.ru/v2/ticket/{ls_number}/{tickets[0]}/'
                    else:
                        lk_data['payment'] = None
                        lk_data['web_link_payment'] = None
                    
                else:
                    lk_data['payment'] = None
                    lk_data['web_link_payment'] = None
                    
            except Exception as e:
                lk_data['payment_error'] = str(e)
                lk_data['payment'] = None
                lk_data['web_link_payment'] = None

            s.close()
            return lk_data
            
        except requests.exceptions.Timeout:
            lk_data['error'] = 'Таймаут подключения'
            lk_data['auth_success'] = False
            s.close()
            return lk_data
        except Exception as e:
            lk_data['error'] = str(e)
            lk_data['auth_success'] = False
            s.close()
            return lk_data

    return autorisation_get_info()