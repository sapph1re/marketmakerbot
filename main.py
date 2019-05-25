import random
import time
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
        self.traction_rate_up = config.getdecimal('MarketMaker', 'TractionRateUp')
        self.traction_rate_down = config.getdecimal('MarketMaker', 'TractionRateDown')
        self.attractor_price = config.getdecimal('MarketMaker', 'AttractorPrice')
        self.api = APIClient()
        self.currency_pair = currency_pair

        logger.info('Market Maker Bot started')
        orderbook_interval = config.getint('MarketMaker', 'OrderbookUpdateInterval')
        self.stop_event_orderbook = self.generate_random_orderbook(
            interval=orderbook_interval,
            min_orderbook_volume=config.getdecimal('MarketMaker', 'OrderbookMinVolume'),
            max_orderbook_volume=config.getdecimal('MarketMaker', 'OrderbookMaxVolume'),
            target_price_range=config.getdecimal('MarketMaker', 'OrderbookPriceRange'),
            min_price_step=config.getdecimal('MarketMaker', 'OrderbookPriceStep'),
            min_order_amount=config.getdecimal('MarketMaker', 'OrderbookMinOrderAmount'),
            min_amount_step=config.getdecimal('MarketMaker', 'OrderbookMinAmountStep')
        )
        # bot will start making trades <StartTradesDelay> seconds after it started placing orders
        time.sleep(config.getint('MarketMaker', 'StartTradesDelay'))
        self.stop_event_trades = self.generate_random_trades(
            min_interval=config.getint('MarketMaker', 'TradeMinInterval'),
            max_interval=config.getint('MarketMaker', 'TradeMaxInterval'),
            min_amount=config.getdecimal('MarketMaker', 'TradeMinAmount'),
            max_amount=config.getdecimal('MarketMaker', 'TradeMaxAmount')
        )

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
                price_max = self.attractor_price
            price_min = price_max / (Decimal(1) + target_price_range)
            if price_max > self.attractor_price:
                price_max -= (price_max - price_min) * self.traction_rate_down * (price_max / self.attractor_price)
        if side == 'asks':
            if best_bid is not None:
                price_min = best_bid + min_price_step
            elif best_ask is not None:
                price_min = best_ask + min_price_step
            elif last_price > 0:
                price_min = last_price + min_price_step
            if price_min is None:
                price_min = self.attractor_price
            price_max = price_min * (Decimal(1) + target_price_range)
            if price_min < self.attractor_price:
                price_min += (price_max - price_min) * self.traction_rate_up * (self.attractor_price / price_min)
        if price_min is None and price_max is None:
            price_min = min_price_step
            price_max = price_min * 1000
        if price_min == 0:
            price_min += min_price_step
        return price_min, price_max

    # runs every <interval> seconds
    # <decimal> min_orderbook_volume: minimal size of the orderbook on each side (bid/ask) to maintain
    # <decimal> max_orderbook_volume: maximal size of the orderbook on each side (bid/ask) to maintain
    # <decimal> target_price_range: relative value, the neighbourhood around the current market prices within which orders will be placed
    # note: as the price shifts up and down, orders will spread farther than the neighbourhood of the initial price
    # so target_price_range doesn't set a fixed price range, instead it regulates the price volatility
    # <decimal> min_price_step: minimal price variation
    # <decimal> min_order_amount: minimal amount for every single order
    # <decimal> min_amount_step: minimal order amount variation
    def generate_random_orderbook(self, interval, min_orderbook_volume, max_orderbook_volume, target_price_range, min_price_step, min_order_amount, min_amount_step):
        def maintain_orders():
            # on each side
            # processing randomly first bids then asks or first asks then bids
            depth = self.api.depth(currency_pair=self.currency_pair, limit=100)
            for side in random.choice([['bids', 'asks'], ['asks', 'bids']]):
                # check orderbook volume
                orderbook_volume = 0
                for level in depth[side]:
                    orderbook_volume += Decimal(level[1])
                if orderbook_volume >= max_orderbook_volume:
                    continue
                # if volume is not enough place some orders
                target_orderbook_volume = random_decimal(min_orderbook_volume, max_orderbook_volume, min_amount_step)
                logger.debug('Target random orderbook volume ({}): {}', side, target_orderbook_volume)
                volume_to_add = target_orderbook_volume - orderbook_volume
                if volume_to_add > min_order_amount:
                    while volume_to_add > min_order_amount:
                        if side == 'bids':
                            order_side = 'buy'
                        elif side == 'asks':
                            order_side = 'sell'
                        # calculate the price range to operate within
                        price_min, price_max = self.calculate_price_range(side, target_price_range, min_price_step)
                        # choose a random price within the range
                        price = random_decimal(price_min, price_max, min_price_step)
                        # choose a random amount
                        amount = random_decimal(min_order_amount, volume_to_add, min_amount_step)
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

    def generate_random_trades(self, min_interval, max_interval, min_amount, max_amount):
        def make_a_trade():
            amount = Decimal(random.randint(min_amount*100, max_amount*100)) / 100
            side = random.choice(['buy', 'sell'])
            logger.info('Random trade: {} {}', side, amount)
            result = self.api.order_create(
                currency_pair=self.currency_pair,
                order_type='market',
                side=side,
                amount=amount
            )
            if result is None:
                logger.error('Failed to make a random trade')
        return run_at_random_intervals(make_a_trade, min_interval, max_interval, 'Trades-Generator')

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
        logger.info('Trader bot stopped')


if __name__ == '__main__':
    bot = MarketMakerBot(config.get('MarketMaker', 'CurrencyPair'))
    while 1:
        time.sleep(1)
