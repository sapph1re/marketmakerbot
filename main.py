import random
import time
import requests
from config import config
from helper import run_repeatedly, run_at_random_intervals
from api_client import APIClient
from decimal import Decimal
from custom_logging import get_logger
logger = get_logger(__name__)


def random_decimal(minimum, maximum, step):
    minimum = int(Decimal(minimum)/step)
    maximum = int(Decimal(maximum)/step)
    return Decimal(random.randint(minimum, maximum)) * step


class MarketMakerBot:
    def __init__(self, currency_pair):
        self.api = APIClient()
        self.currency_pair = currency_pair
        self.check_binance = True

        logger.info('Market Maker Bot started')
        self.stop_event_orderbook = self.generate_random_orderbook()
        # bot will start making trades <StartTradesDelay> seconds after it started placing orders
        time.sleep(config.getint('MarketMaker', 'StartTradesDelay'))
        self.stop_event_trades = self.generate_random_trades()

    def calculate_price_range(self, side, target_price_range, min_price_step):
        # get current bid, ask, last price
        depth = self.api.depth(currency_pair=self.currency_pair, limit=1)
        try:
            best_bid = Decimal(str(depth['bids'][0][0]))
        except IndexError:
            best_bid = None
        try:
            best_ask = Decimal(str(depth['asks'][0][0]))
        except IndexError:
            best_ask = None
        last_price = Decimal(str(self.api.ticker(currency_pair=self.currency_pair)['last']))
        # choose a price range
        price_max = None
        price_min = None
        if side == 'bids':
            if best_ask is not None:
                price_max = best_ask - min_price_step
            elif best_bid is not None:
                price_max = best_bid - min_price_step
            elif last_price > 0:
                price_max = last_price - min_price_step
            if price_max is None:
                price_max = self.get_ref_price()
            price_min = price_max / (Decimal(1) + target_price_range)
        if side == 'asks':
            if best_bid is not None:
                price_min = best_bid + min_price_step
            elif best_ask is not None:
                price_min = best_ask + min_price_step
            elif last_price > 0:
                price_min = last_price + min_price_step
            if price_min is None:
                price_min = self.get_ref_price()
            price_max = price_min * (Decimal(1) + target_price_range)
        if price_min is None and price_max is None:
            price_min = min_price_step
            price_max = price_min * 1000
        if price_min == 0:
            price_min += min_price_step
        return price_min, price_max

    def get_ref_price(self):
        # check reference price on Binance if it is present there
        if self.check_binance:
            try:
                symbol = self.currency_pair.replace('/', '')
                r = requests.get(f'https://api.binance.com/api/v3/ticker/price?symbol={symbol}').json()
                if 'msg' in r and r['msg'] == 'Invalid symbol.':
                    logger.info('Symbol {} is not present on Binance', symbol)
                    # do not ask anymore
                    self.check_binance = False
                else:
                    return Decimal(r['price'])
            except Exception as e:
                logger.info('Failed to load price from Binance: {}', e)
        # otherwise just use our own last price
        last_price = Decimal(str(self.api.ticker(currency_pair=self.currency_pair)['last']))
        if last_price > 0:
            return last_price
        # if we had no trades here yet, get price from config
        return config.getdecimal('MarketMaker', 'StartPrice')

    def calculate_spread_levels(self, max_spread: Decimal, price_step: Decimal) -> tuple:
        ref_price = self.get_ref_price()
        spread_bid = (ref_price - max_spread / 2).quantize(price_step)
        if spread_bid < price_step:
            spread_bid = price_step
        spread_ask = spread_bid + max_spread
        return spread_bid, spread_ask

    def generate_random_orderbook(self):
        interval = config.getint('MarketMaker', 'OrderbookUpdateInterval')
        max_spread = config.getdecimal('MarketMaker', 'OrderbookMaxSpread')
        min_orderbook_volume = config.getdecimal('MarketMaker', 'OrderbookMinVolume')
        max_orderbook_volume = config.getdecimal('MarketMaker', 'OrderbookMaxVolume')
        target_price_range = config.getdecimal('MarketMaker', 'OrderbookPriceRange')
        price_step = config.getdecimal('MarketMaker', 'OrderbookPriceStep')
        min_order_amount = config.getdecimal('MarketMaker', 'OrderbookMinOrderAmount')
        amount_step = config.getdecimal('MarketMaker', 'OrderbookMinAmountStep')
        min_order_size = config.getdecimal('MarketMaker', 'MinOrderSize')

        def maintain_orders():
            # maintain the spread
            spread_bid, spread_ask = self.calculate_spread_levels(max_spread, price_step)
            logger.info('Calculated spread levels: {:f} {:f}', spread_bid, spread_ask)
            depth = self.api.depth(currency_pair=self.currency_pair, limit=1)
            best_bid = Decimal(str(depth['bids'][0][0]))
            best_ask = Decimal(str(depth['asks'][0][0]))
            if spread_bid > best_bid:
                # place a bid at spread_bid
                min_amount = min_order_amount
                if min_order_amount * spread_bid < min_order_size:
                    min_amount = (min_order_size / spread_bid).quantize(amount_step)
                amount = random_decimal(min_amount, min_order_amount*3, amount_step)
                logger.info('Placing spread bid: {} @ {:f}', amount, spread_bid)
                self.api.order_create(
                    currency_pair=self.currency_pair,
                    order_type='limit',
                    side='buy',
                    amount=amount,
                    price=spread_bid
                )
            if spread_ask < best_ask:
                # place an ask at spread_ask
                min_amount = min_order_amount
                if min_order_amount * spread_ask < min_order_size:
                    min_amount = (min_order_size / spread_bid).quantize(amount_step)
                amount = random_decimal(min_amount, min_order_amount*3, amount_step)
                logger.info('Placing spread ask: {} @ {:f}', amount, spread_ask)
                self.api.order_create(
                    currency_pair=self.currency_pair,
                    order_type='limit',
                    side='sell',
                    amount=amount,
                    price=spread_ask
                )
            # get the orderbook now
            depth = self.api.depth(currency_pair=self.currency_pair, limit=100)
            # processing randomly first bids then asks or first asks then bids
            for side in random.choice([['bids', 'asks'], ['asks', 'bids']]):
                # check orderbook volume
                orderbook_volume = 0
                for level in depth[side]:
                    orderbook_volume += Decimal(str(level[1]))
                if orderbook_volume >= max_orderbook_volume:
                    continue
                # if volume is not enough place some orders
                target_orderbook_volume = random_decimal(min_orderbook_volume, max_orderbook_volume, amount_step)
                logger.debug('Target random orderbook volume ({}): {}', side, target_orderbook_volume)
                volume_to_add = target_orderbook_volume - orderbook_volume
                if volume_to_add > min_order_amount:
                    while volume_to_add > min_order_amount:
                        if side == 'bids':
                            order_side = 'buy'
                        elif side == 'asks':
                            order_side = 'sell'
                        # calculate the price range to operate within
                        price_min, price_max = self.calculate_price_range(side, target_price_range, price_step)
                        # choose a random price within the range
                        price = random_decimal(price_min, price_max, price_step)
                        # choose a random amount
                        amount = random_decimal(min_order_amount, volume_to_add, amount_step)
                        # place the order
                        logger.info('Creating random order: {} {} @ {}', order_side, amount, price)
                        self.api.order_create(
                            currency_pair=self.currency_pair,
                            order_type='limit',
                            side=order_side,
                            amount=amount,
                            price=price
                        )
                        # place more orders until target orderbook volume is reached
                        volume_to_add -= amount
                if volume_to_add < 0:
                    while volume_to_add < 0:
                        found = False
                        active_orders = self.api.my_open_orders()
                        for order in active_orders:
                            if order['symbol'] != self.currency_pair:
                                continue
                            order_amount = Decimal(str(order['amount']))
                            if order_amount < -volume_to_add:
                                found = True
                                logger.info(
                                    'Removing random order: {} {} {} {} @ {} (#{})',
                                    order['type'], order['info']['side'], order['amount'],
                                    order['symbol'], Decimal(str(order['price'])), order['id']
                                )
                                self.api.order_remove(
                                    currency_pair=self.currency_pair,
                                    order_id=order['id'],
                                    side=order['info']['side']
                                )
                                volume_to_add += order_amount
                        if not found:
                            break

            # check total volume of own orders on each side
            my_bids_volume = Decimal(0)
            my_asks_volume = Decimal(0)
            lowest_bid_order = None
            lowest_bid_price = None
            highest_ask_order = None
            highest_ask_price = None
            active_orders = self.api.my_open_orders()
            for order in active_orders:
                if order['symbol'] != self.currency_pair:
                    continue
                order_amount = Decimal(str(order['amount']))
                order_price = Decimal(str(order['price']))
                if order['info']['side'] == 'BUY':
                    my_bids_volume += order_amount
                    if lowest_bid_price is None or order_price < lowest_bid_price:
                        lowest_bid_order = order
                        lowest_bid_price = order_price
                elif order['info']['side'] == 'SELL':
                    my_asks_volume += order_amount
                    if highest_ask_price is None or order_price > highest_ask_price:
                        highest_ask_order = order
                        highest_ask_price = order_price
            # if we have too much volume on orders, cancel the farthest orders to free the funds
            if my_bids_volume > max_orderbook_volume:
                # too much volume on bids, remove the lowest bid
                logger.info(
                    'Removing lowest bid: {} {} @ {}',
                    lowest_bid_order['info']['side'],
                    Decimal(str(lowest_bid_order['amount'])),
                    Decimal(str(lowest_bid_order['price']))
                )
                self.api.order_remove(
                    currency_pair=self.currency_pair,
                    order_id=lowest_bid_order['id'],
                    side=lowest_bid_order['info']['side']
                )
            if my_asks_volume > max_orderbook_volume:
                # too much volume on asks, remove the highest ask
                logger.info(
                    'Removing highest ask: {} {} @ {}',
                    highest_ask_order['info']['side'],
                    Decimal(str(highest_ask_order['amount'])),
                    Decimal(str(highest_ask_order['price']))
                )
                self.api.order_remove(
                    currency_pair=self.currency_pair,
                    order_id=highest_ask_order['id'],
                    side=highest_ask_order['info']['side']
                )

        # launch it
        return run_repeatedly(maintain_orders, interval, 'Orderbook-Generator')

    def generate_random_trades(self):
        min_interval = config.getint('MarketMaker', 'TradeMinInterval'),
        max_interval = config.getint('MarketMaker', 'TradeMaxInterval'),
        min_amount = config.getdecimal('MarketMaker', 'TradeMinAmount'),
        max_amount = config.getdecimal('MarketMaker', 'TradeMaxAmount'),
        amount_step = config.getdecimal('MarketMaker', 'TradeAmountStep'),
        min_volume_24h = config.getfloat('MarketMaker', 'MinTradeVolume24h'),
        amount_deviation = config.getfloat('MarketMaker', 'TradeAmountVariation')
        max_price = config.getdecimal('MarketMaker', 'TradeMaxPrice')
        min_price = config.getdecimal('MarketMaker', 'TradeMinPrice')

        def make_a_trade():
            interval_ev = (max_interval + min_interval) / 2
            amount_ev = min_volume_24h * interval_ev / (24*60*60)
            amount = Decimal(
                random.normalvariate(amount_ev, amount_deviation*amount_ev)
            )
            if amount < min_amount:
                amount = min_amount
            elif amount > max_amount:
                amount = max_amount
            amount = amount.quantize(amount_step)
            side = random.choice(['buy', 'sell'])
            # find the nearest price to execute a trade
            depth = self.api.depth(currency_pair=self.currency_pair, limit=1)
            depth_side = {'buy': 'bids', 'sell': 'asks'}[side]
            best_price = Decimal(str(depth[depth_side][0][0]))
            # check the price limits
            if not min_price <= best_price <= max_price:
                logger.error('Best price {} is beyond the limits: {} {}', best_price, min_price, max_price)
                return
            # make a trade
            logger.info('Random trade: {} {} @ {} IOC', side, amount, best_price)
            result = self.api.order_create(
                currency_pair=self.currency_pair,
                order_type='limit',
                side=side,
                amount=amount,
                price=best_price,
                params={'timeInForce': 'IOC'}
            )
            if result is None:
                logger.error('Failed to make a random trade')

        return run_at_random_intervals(
            make_a_trade, min_interval, max_interval, 'Trades-Generator'
        )

    def __del__(self):
        try:
            self.stop_event_orderbook.set()
        except AttributeError:
            pass
        try:
            self.stop_event_trades.set()
        except AttributeError:
            pass
        time.sleep(1)  # let the threads complete
        logger.info('Market Maker Bot stopped')


if __name__ == '__main__':
    bot = MarketMakerBot(config.get('MarketMaker', 'CurrencyPair'))
    while 1:
        time.sleep(1)
