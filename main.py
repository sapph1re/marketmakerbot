import random
import time
import requests
import argparse
import ccxt
from config import config
from helper import run_repeatedly, run_at_random_intervals
from decimal import Decimal
from api_client import APIClient
from custom_logging import get_logger
logger = get_logger(__name__)

ap = argparse.ArgumentParser()
ap.add_argument('-c', dest='config_file')
args = ap.parse_args()

config_file = args.config_file
if config_file is None:
    config_file = 'config.ini'

config.read(config_file)


def random_decimal(minimum, maximum, step):
    minimum = int(Decimal(minimum)/step)
    maximum = int(Decimal(maximum)/step)
    return Decimal(random.randint(minimum, maximum)) * step


class MarketMakerBot:
    def __init__(self):
        self.api = APIClient()
        self.currency_pair = config.get('MarketMaker', 'CurrencyPair')
        self.check_binance = True

        self.min_order_size = config.getdecimal('MarketMaker', 'MinOrderSize')
        self.amount_step = config.getdecimal('MarketMaker', 'OrderbookMinAmountStep')

        logger.info('Market Maker Bot started at {}', self.currency_pair)
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

    def respect_order_size(self, amount: Decimal, price: Decimal) -> Decimal:
        if amount * price < self.min_order_size:
            return (self.min_order_size / price).quantize(self.amount_step)
        return amount

    def generate_random_orderbook(self):
        interval = config.getint('MarketMaker', 'OrderbookUpdateInterval')
        max_spread = config.getdecimal('MarketMaker', 'OrderbookMaxSpread')
        min_orderbook_volume = config.getdecimal('MarketMaker', 'OrderbookMinVolume')
        max_orderbook_volume = config.getdecimal('MarketMaker', 'OrderbookMaxVolume')
        target_price_range = config.getdecimal('MarketMaker', 'OrderbookPriceRange')
        price_step = config.getdecimal('MarketMaker', 'OrderbookPriceStep')
        min_order_amount = config.getdecimal('MarketMaker', 'OrderbookMinOrderAmount')

        def maintain_orders():
            try:
                # maintain the spread
                spread_bid, spread_ask = self.calculate_spread_levels(max_spread, price_step)
                logger.info('Calculated spread levels: {:f} {:f}', spread_bid, spread_ask)
                depth = self.api.depth(currency_pair=self.currency_pair, limit=1)
                best_bid = Decimal(str(depth['bids'][0][0])) if len(depth['bids']) > 0 else None
                best_ask = Decimal(str(depth['asks'][0][0])) if len(depth['asks']) > 0 else None
                logger.info('Actual spread right now: {:f} {:f}', best_bid, best_ask)
                if best_bid is None or best_bid < spread_bid:
                    # place a bid at spread_bid
                    min_amount = self.respect_order_size(min_order_amount, spread_bid)
                    amount = random_decimal(min_amount, min_amount*3, self.amount_step)
                    logger.info('Placing spread bid: {} @ {:f}', amount, spread_bid)
                    self.api.order_create(
                        currency_pair=self.currency_pair,
                        order_type='limit',
                        side='buy',
                        amount=amount,
                        price=spread_bid
                    )
                if best_ask is None or best_ask > spread_ask:
                    # place an ask at spread_ask
                    min_amount = self.respect_order_size(min_order_amount, spread_ask)
                    amount = random_decimal(min_amount, min_amount*3, self.amount_step)
                    logger.info('Placing spread ask: {} @ {:f}', amount, spread_ask)
                    self.api.order_create(
                        currency_pair=self.currency_pair,
                        order_type='limit',
                        side='sell',
                        amount=amount,
                        price=spread_ask
                    )
                logger.info('Checking orderbook volume...')
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
                    target_orderbook_volume = random_decimal(min_orderbook_volume, max_orderbook_volume, self.amount_step)
                    logger.debug('Target random orderbook volume ({}): {}', side, target_orderbook_volume)
                    volume_to_add = target_orderbook_volume - orderbook_volume
                    if volume_to_add > min_order_amount:
                        while volume_to_add > min_order_amount:
                            # calculate the price range to operate within
                            price_min, price_max = self.calculate_price_range(side, target_price_range, price_step)
                            if side == 'bids':
                                order_side = 'buy'
                                price_max = spread_bid  # don't go above our spread
                            elif side == 'asks':
                                order_side = 'sell'
                                price_min = spread_ask  # don't go below our spread
                            # choose a random price within the range
                            price = random_decimal(price_min, price_max, price_step)
                            # choose a random amount
                            min_amount = self.respect_order_size(min_order_amount, price)
                            if volume_to_add <= min_amount:
                                amount = min_amount
                            else:
                                amount = random_decimal(min_amount, volume_to_add, self.amount_step)
                            # place the order
                            logger.info('Creating random order: {} {} @ {:f}', order_side, amount, price)
                            self.api.order_create(
                                currency_pair=self.currency_pair,
                                order_type='limit',
                                side=order_side,
                                amount=amount,
                                price=price
                            )
                            # place more orders until target orderbook volume is reached
                            volume_to_add -= amount

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
                        'Removing lowest bid: {} {} @ {:f}',
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
                        'Removing highest ask: {} {} @ {:f}',
                        highest_ask_order['info']['side'],
                        Decimal(str(highest_ask_order['amount'])),
                        Decimal(str(highest_ask_order['price']))
                    )
                    self.api.order_remove(
                        currency_pair=self.currency_pair,
                        order_id=highest_ask_order['id'],
                        side=highest_ask_order['info']['side']
                    )
            except ccxt.errors.BaseError as e:
                logger.error('Exchange API error: {}', e)

        # launch it
        return run_repeatedly(maintain_orders, interval, 'Orderbook-Generator')

    def generate_random_trades(self):
        min_interval = config.getint('MarketMaker', 'TradeMinInterval')
        max_interval = config.getint('MarketMaker', 'TradeMaxInterval')
        min_amount = config.getdecimal('MarketMaker', 'TradeMinAmount')
        max_amount = config.getdecimal('MarketMaker', 'TradeMaxAmount')
        min_volume_24h = config.getfloat('MarketMaker', 'MinTradeVolume24h')
        amount_deviation = config.getfloat('MarketMaker', 'TradeAmountVariation')
        max_price = config.getdecimal('MarketMaker', 'TradeMaxPrice')
        min_price = config.getdecimal('MarketMaker', 'TradeMinPrice')

        def make_a_trade():
            try:
                interval_ev = (max_interval + min_interval) / 2
                amount_ev = min_volume_24h * interval_ev / (24*60*60)
                amount = Decimal(
                    random.normalvariate(amount_ev, amount_deviation*amount_ev)
                )
                if amount < min_amount:
                    amount = min_amount
                elif amount > max_amount:
                    amount = max_amount
                amount = amount.quantize(self.amount_step)
                side = random.choice(['buy', 'sell'])
                # find the nearest price to execute a trade
                depth = self.api.depth(currency_pair=self.currency_pair, limit=1)
                depth_side = {'buy': 'asks', 'sell': 'bids'}[side]
                best_price = Decimal(str(depth[depth_side][0][0]))
                # check the price limits
                if not min_price <= best_price <= max_price:
                    logger.error('Best price {:f} is beyond the limits: {:f} {:f}', best_price, min_price, max_price)
                    return
                amount = self.respect_order_size(amount, best_price)
                # make a trade
                logger.info('Random trade: {} {} @ {:f} IOC', side, amount, best_price)
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
            except ccxt.errors.BaseError as e:
                logger.error('Exchange API error: {}', e)

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
    bot = MarketMakerBot()
    while 1:
        time.sleep(1)
