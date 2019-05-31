import ccxt
import pyotp
from config import config
from custom_logging import get_logger
logger = get_logger(__name__)


class APIError(Exception):
    def __init__(self, message):
        self.message = message


class APIClient:
    def __init__(self):
        self.api = ccxt.mandala({
            'apiKey': config.get('Exchange', 'APIKey'),
            'secret': config.get('Exchange', 'APISecret'),
            'login': config.get('Exchange', 'Login'),
            'password': config.get('Exchange', 'Password')
        })
        self.otp = pyotp.TOTP(config.get('Exchange', 'TwoFASecret'))
        self.api.sign_in({'password': self.otp.now()})
        self.api.load_markets()

    def ticker(self, currency_pair):
        return self.api.fetch_ticker(currency_pair)

    def depth(self, currency_pair, limit=100):
        limits_allowed = [5, 10, 20, 50, 100, 500, 1000]
        if limit not in limits_allowed:
            # finding nearest allowed value
            limit = min(limits_allowed, key=lambda x: abs(x - limit))
        return self.api.fetch_order_book(currency_pair, limit=limit)

    def order_create(self, currency_pair, order_type, side, amount, price=None):
        try:
            return self.api.create_order(currency_pair, order_type, side, amount, price)
        except ccxt.errors.ExchangeError as e:
            logger.error('Failed to create order: {}', e)
            return None

    def order_remove(self, currency_pair, order_id, side):
        return self.api.cancel_order(order_id, currency_pair, params={'side': side})

    def my_open_orders(self):
        return self.api.fetch_open_orders()
