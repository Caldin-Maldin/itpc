"""Config flow для ITPC интеграции."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
import requests
from bs4 import BeautifulSoup

from .const import DOMAIN, CONF_LOGIN, CONF_PASSWORD

class ITPCConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Обработчик config flow."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Первый шаг настройки."""
        errors = {}

        if user_input is not None:
            # Проверяем учетные данные
            try:
                await self.hass.async_add_executor_job(
                    self._test_credentials, 
                    user_input[CONF_LOGIN], 
                    user_input[CONF_PASSWORD]
                )
                return self.async_create_entry(
                    title=user_input[CONF_LOGIN],
                    data=user_input
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_LOGIN): str,
                vol.Required(CONF_PASSWORD): str,
            }),
            errors=errors,
        )

    def _test_credentials(self, login, password):
        """Тестирование учетных данных."""
        try:
            result = self._get_data(login, password)
            if result.get('error') and 'Неверный' in str(result.get('error')):
                raise InvalidAuth
            if not result.get('auth_success'):
                raise CannotConnect
        except requests.RequestException:
            raise CannotConnect

    def _get_data(self, login, password):
        """Получение данных с авторизацией."""
        s = requests.Session()
        s.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'ru-RU,ru;q=0.9',
            'Referer': 'https://lk.itpc.ru/',
            'X-Requested-With': 'XMLHttpRequest',
        })

        data_auth = {
            'login': login,
            'password': password,
            'submit': 'Войти'
        }

        login_response = s.post('https://lk.itpc.ru/', data=data_auth, timeout=10)

        if 'Неверный пользователь или пароль' in login_response.text:
            s.close()
            return {'error': 'Неверный логин или пароль', 'auth_success': False}

        try:
            user_response = s.get('https://lk.itpc.ru/v2/user/', timeout=10)
            if user_response.status_code != 200:
                s.close()
                return {'error': f'API error: {user_response.status_code}', 'auth_success': False}

            user_json = user_response.json()
            first_account = user_json.get('accounts', [{}])[0]
            
            result = {
                'auth_success': True,
                'user_data': {
                    'id': user_json.get('id'),
                    'accounts': first_account.get('oid'),
                    'address': first_account.get('address'),
                    'main': first_account.get('debt', {}).get('main'),
                    'penalties': first_account.get('debt', {}).get('penalties')
                }
            }

            ls_number = first_account.get('oid')
            if ls_number:
                counter_response = s.get(f'https://lk.itpc.ru/v2/account/{ls_number}/counter/', timeout=10)
                if counter_response.status_code == 200:
                    counter_json = counter_response.json()
                    counters = []
                    for counter in counter_json.get('counters', []):
                        counters.append({
                            'name': counter.get('service', {}).get('name'),
                            'oid': counter.get('oid'),
                            'serial': counter.get('serial'),
                            'current': counter.get('current'),
                            'previous': counter.get('previous'),
                            'model': counter.get('model'),
                            'next_verification': counter.get('next_verification')
                        })
                    result['counter_data'] = {'counters': counters}

            s.close()
            return result

        except Exception as e:
            s.close()
            return {'error': str(e), 'auth_success': False}

class CannotConnect(HomeAssistantError):
    """Ошибка подключения."""

class InvalidAuth(HomeAssistantError):
    """Ошибка авторизации."""