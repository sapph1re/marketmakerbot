# -*- coding: utf-8 -*-

# PLEASE DO NOT EDIT THIS FILE, IT IS GENERATED AND WILL BE OVERWRITTEN:
# https://github.com/ccxt/ccxt/blob/master/CONTRIBUTING.md#how-to-contribute-code

from ccxt.okcoinusd import okcoinusd


class allcoin (okcoinusd):

    def describe(self):
        return self.deep_extend(super(allcoin, self).describe(), {
            'id': 'allcoin',
            'name': 'Allcoin',
            'countries': ['CA'],
            'has': {
                'CORS': False,
            },
            'extension': '',
            'urls': {
                'logo': 'https://user-images.githubusercontent.com/1294454/31561809-c316b37c-b061-11e7-8d5a-b547b4d730eb.jpg',
                'api': {
                    'web': 'https://www.allcoin.com',
                    'public': 'https://api.allcoin.com/api',
                    'private': 'https://api.allcoin.com/api',
                },
                'www': 'https://www.allcoin.com',
                'doc': 'https://www.allcoin.com/api_market/market',
                'referral': 'https://www.allcoin.com',
            },
            'api': {
                'web': {
                    'get': [
                        'Home/MarketOverViewDetail/',
                    ],
                },
                'public': {
                    'get': [
                        'depth',
                        'kline',
                        'ticker',
                        'trades',
                    ],
                },
                'private': {
                    'post': [
                        'batch_trade',
                        'cancel_order',
                        'order_history',
                        'order_info',
                        'orders_info',
                        'repayment',
                        'trade',
                        'trade_history',
                        'userinfo',
                    ],
                },
            },
        })

    def fetch_markets(self, params={}):
        result = []
        response = self.webGetHomeMarketOverViewDetail()
        coins = response['marketCoins']
        for j in range(0, len(coins)):
            markets = coins[j]['Markets']
            for k in range(0, len(markets)):
                market = markets[k]['Market']
                base = market['Primary']
                quote = market['Secondary']
                baseId = base.lower()
                quoteId = quote.lower()
                id = baseId + '_' + quoteId
                symbol = base + '/' + quote
                active = market['TradeEnabled'] and market['BuyEnabled'] and market['SellEnabled']
                result.append({
                    'id': id,
                    'symbol': symbol,
                    'base': base,
                    'quote': quote,
                    'baseId': baseId,
                    'quoteId': quoteId,
                    'active': active,
                    'type': 'spot',
                    'spot': True,
                    'future': False,
                    'maker': market['AskFeeRate'],  # BidFeeRate 0, AskFeeRate 0.002, we use just the AskFeeRate here
                    'taker': market['AskFeeRate'],  # BidFeeRate 0, AskFeeRate 0.002, we use just the AskFeeRate here
                    'precision': {
                        'amount': market['PrimaryDigits'],
                        'price': market['SecondaryDigits'],
                    },
                    'limits': {
                        'amount': {
                            'min': market['MinTradeAmount'],
                            'max': market['MaxTradeAmount'],
                        },
                        'price': {
                            'min': market['MinOrderPrice'],
                            'max': market['MaxOrderPrice'],
                        },
                        'cost': {
                            'min': None,
                            'max': None,
                        },
                    },
                    'info': market,
                })
        return result

    def parse_order_status(self, status):
        statuses = {
            '-1': 'canceled',
            '0': 'open',
            '1': 'open',
            '2': 'closed',
            '10': 'canceled',
        }
        return self.safe_string(statuses, status, status)

    def get_create_date_field(self):
        # allcoin typo create_data instead of create_date
        return 'create_data'

    def get_orders_field(self):
        # allcoin typo order instead of orders(expected based on their API docs)
        return 'order'
