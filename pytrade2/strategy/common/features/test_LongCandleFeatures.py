from datetime import datetime
from unittest import TestCase

import pandas as pd

from strategy.common.features.LongCandleFeatures import LongCandleFeatures


class TestLongCandleFeatures(TestCase):

    @staticmethod
    def candles_1m_5():
        return pd.DataFrame([
            {"close_time": datetime.fromisoformat("2023-05-21 07:01:00"), "symbol": "asset1", "interval": "1m",
             "open": 1, "high": 10, "low": 100, "close": 1000, "vol": 10000},

            {"close_time": datetime.fromisoformat("2023-05-21 07:02:00"), "symbol": "asset1", "interval": "1m",
             "open": 2, "high": 20, "low": 200, "close": 2000, "vol": 20000},

            {"close_time": datetime.fromisoformat("2023-05-21 07:03:00"), "symbol": "asset1", "interval": "1m",
             "open": 3, "high": 30, "low": 300, "close": 3000, "vol": 30000},

            {"close_time": datetime.fromisoformat("2023-05-21 07:04:00"), "symbol": "asset1", "interval": "1m",
             "open": 4, "high": 40, "low": 400, "close": 4000, "vol": 40000},

            {"close_time": datetime.fromisoformat("2023-05-21 07:05:00"), "symbol": "asset1", "interval": "1m",
             "open": 5, "high": 50, "low": 500, "close": 5000, "vol": 50000}]) \
            .set_index("close_time", drop=False)

    @staticmethod
    def candles_5m_5():
        return pd.DataFrame([
            {"close_time": datetime.fromisoformat("2023-05-21 06:40:00"), "symbol": "asset1", "interval": "5m",
             "open": 6, "high": 6.40, "low": 6.40, "close": 6.40, "vol": 6.40},

            {"close_time": datetime.fromisoformat("2023-05-21 06:45:00"), "symbol": "asset1", "interval": "5m",
             "open": 7, "high": 6.450, "low": 6.4500, "close": 6.45000, "vol": 6.450000},

            {"close_time": datetime.fromisoformat("2023-05-21 06:50:00"), "symbol": "asset1", "interval": "5m",
             "open": 9, "high": 6.500, "low": 6.5000, "close": 6.50000, "vol": 6.500000},

            {"close_time": datetime.fromisoformat("2023-05-21 06:55:00"), "symbol": "asset1", "interval": "5m",
             "open": 12, "high": 6.550, "low": 6.5500, "close": 6.55000, "vol": 6.550000},

            {"close_time": datetime.fromisoformat("2023-05-21 07:05:00"), "symbol": "asset1", "interval": "5m",
             "open": 16, "high": 7.0000, "low": 7.0000, "close": 7000, "vol": 70000}]) \
            .set_index("close_time", drop=False)

    def test_targets_of_buy(self):
        # Go up
        candles = pd.DataFrame(
            [{"close_time": datetime.fromisoformat("2023-05-21 07:01:00"), "symbol": "asset1", "interval": "1m",
              "open": 10, "high": 12, "low": 9, "close": 11, "vol": 1},
             {"close_time": datetime.fromisoformat("2023-05-21 07:02:00"), "symbol": "asset1", "interval": "1m",
              "open": 13, "high": 15, "low": 12, "close": 14, "vol": 1},
             {"close_time": datetime.fromisoformat("2023-05-21 07:03:00"), "symbol": "asset1", "interval": "1m",
              "open": 16, "high": 18, "low": 15, "close": 17, "vol": 1}]) \
            .set_index("close_time", drop=False)

        actual = LongCandleFeatures.targets_of(candles)
        self.assertSequenceEqual([1], actual["signal"].tolist())
        self.assertSequenceEqual([datetime.fromisoformat("2023-05-21 07:01:00")], actual.index)

    def test_targets_of_sell(self):
        # Go up
        candles = pd.DataFrame(
            [{"close_time": datetime.fromisoformat("2023-05-21 07:01:00"), "symbol": "asset1", "interval": "1m",
              "open": 16, "high": 18, "low": 15, "close": 17, "vol": 1},
             {"close_time": datetime.fromisoformat("2023-05-21 07:02:00"), "symbol": "asset1", "interval": "1m",
              "open": 13, "high": 15, "low": 12, "close": 14, "vol": 1},
             {"close_time": datetime.fromisoformat("2023-05-21 07:03:00"), "symbol": "asset1", "interval": "1m",
              "open": 10, "high": 12, "low": 9, "close": 11, "vol": 1}]) \
            .set_index("close_time", drop=False)

        actual = LongCandleFeatures.targets_of(candles)
        self.assertSequenceEqual([-1], actual["signal"].tolist())

    def test_targets_of_flat(self):
        # Go up
        candles = pd.DataFrame(
            [{"close_time": datetime.fromisoformat("2023-05-21 07:01:00"), "symbol": "asset1", "interval": "1m",
              "open": 16, "high": 18, "low": 15, "close": 17, "vol": 1},
             {"close_time": datetime.fromisoformat("2023-05-21 07:02:00"), "symbol": "asset1", "interval": "1m",
              "open": 16, "high": 18, "low": 15, "close": 17, "vol": 1},
             {"close_time": datetime.fromisoformat("2023-05-21 07:03:00"), "symbol": "asset1", "interval": "1m",
              "open": 16, "high": 18, "low": 15, "close": 17, "vol": 1}, ]) \
            .set_index("close_time", drop=False)

        actual = LongCandleFeatures.targets_of(candles)
        self.assertSequenceEqual([0], actual["signal"].tolist())

    def test_features_targets__same_index(self):
        actual_features, actual_targets = LongCandleFeatures.features_targets_of(
            {"1min": self.candles_1m_5(), "5min": self.candles_5m_5()},
            {"1min": 2, "5min": 2}, target_period="1min")

        self.assertSequenceEqual(actual_features.index.tolist(), actual_targets.index.tolist())
    #
    # def test_features_targets_of(self):
    #     # Receive 1 min candles
    #     # before prev to make diff() for prev not none
    #     candles_1min = (pd.DataFrame([
    #         # before prev to make diff() for prev not none
    #         {'open_time': datetime.fromisoformat('2023-10-15T09:57:00'),
    #          'close_time': datetime.fromisoformat('2023-10-15T09:58:00'),
    #          'interval': '1min', 'open': 10, 'high': 11, 'low': 9, 'close': 10, 'vol': 1},
    #         # prev
    #         {'open_time': datetime.fromisoformat('2023-10-15T09:58:00'),
    #          'close_time': datetime.fromisoformat('2023-10-15T09:59:00'),
    #          'interval': '1min', 'open': 10, 'high': 11, 'low': 9, 'close': 10, 'vol': 1},
    #         # Current
    #         {'open_time': datetime.fromisoformat('2023-10-15T09:59:00'),
    #          'close_time': datetime.fromisoformat('2023-10-15T10:00:00'),
    #          'interval': '1min', 'open': 10, 'high': 11, 'low': 9, 'close': 10, 'vol': 1},
    #         # next1
    #         {'open_time': datetime.fromisoformat('2023-10-15T10:00:00'),
    #          'close_time': datetime.fromisoformat('2023-10-15T10:01:00'),
    #          'interval': '1min', 'open': 10, 'high': 11, 'low': 9, 'close': 10, 'vol': 1},
    #         # next2
    #         {'open_time': datetime.fromisoformat('2023-10-15T10:01:00'),
    #          'close_time': datetime.fromisoformat('2023-10-15T10:02:00'),
    #          'interval': '1min', 'open': 10, 'high': 11, 'low': 9, 'close': 10, 'vol': 1}])
    #                     .set_index('close_time', drop=False))
    #
    #     candles_5min = (pd.DataFrame([
    #         # 5 min prev
    #         {'open_time': datetime.fromisoformat('2023-10-15T09:50:00'),
    #          'close_time': datetime.fromisoformat('2023-10-15T09:55:00'),
    #          'interval': '5min', 'open': 10, 'high': 11, 'low': 9, 'close': 10, 'vol': 1},
    #         # 5 min current
    #         {'open_time': datetime.fromisoformat('2023-10-15T09:55:00'),
    #          'close_time': datetime.fromisoformat('2023-10-15T10:00:00'),
    #          'interval': '5min', 'open': 10, 'high': 11, 'low': 9, 'close': 10, 'vol': 1}])
    #                     .set_index('close_time', drop=False))
    #
    #     candles_by_interval = {'1min': candles_1min, '5min': candles_5min}
    #     cnt_by_interval = {'1min': 1, '5min': 1}
    #
    #     X, y = LongCandleFeatures.features_targets_of(candles_by_interval,
    #                                                   cnt_by_interval,
    #                                                   '1min')
    #     self.assertFalse(X.empty)
    #     self.assertFalse(y.empty)