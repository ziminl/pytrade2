import logging
import multiprocessing
import os
from datetime import datetime
from pathlib import Path
from typing import Dict
import pandas as pd

from exch.Exchange import Exchange
from strategy.feed.CandlesDownloader import CandlesDownloader


class CandlesFeed:
    """ Decorator for strategies. Reads candles from exchange """

    def __init__(self, config, ticker: str, exchange_provider: Exchange, data_lock: multiprocessing.RLock,
                 new_data_event: multiprocessing.Event, tag):
        self._logger = logging.getLogger(self.__class__.__name__)
        self.data_lock = data_lock
        self.exchange_candles_feed = exchange_provider.candles_feed(config["pytrade2.exchange"])
        self.exchange_candles_feed.consumers.add(self)
        self.downloader = CandlesDownloader(config, self.exchange_candles_feed, tag)

        self.ticker = ticker
        self.candles_by_interval: Dict[str, pd.DataFrame] = dict()
        self.candles_by_interval_buf: Dict[str, pd.DataFrame] = dict()
        self.new_data_event = new_data_event

        periods = config["pytrade2.feed.candles.periods"]
        counts = config["pytrade2.feed.candles.counts"]
        self.candles_cnt_by_interval = self.candles_cnt_by_interval_of(periods, counts)

    def apply_history_days(self, history_days: int):
        """History days parameter changed, load absent"""
        self._logger.info(f"Applying new history days param: {history_days}")
        self.downloader.days = history_days
        self.downloader.download_absent_days(datetime.now())

    def apply_periods_counts(self, periods_str: str, counts_str: str):
        """Candles configuration changed: periods, counts, reload them"""
        new_counts = self.candles_cnt_by_interval_of(periods_str, counts_str)

        if self.candles_cnt_by_interval != new_counts:
            # If changed, reload all candles
            with self.data_lock:
                self._logger.info(f"Applying candles counts to {new_counts}. Resetting accumulated data.")
                self.candles_cnt_by_interval = new_counts
                # Clear candles and buffers
                self.candles_by_interval: Dict[str, pd.DataFrame] = dict()
                self.candles_by_interval_buf: Dict[str, pd.DataFrame] = dict()

                # If changed, redownload candles
                self.read_candles()

    @staticmethod
    def candles_cnt_by_interval_of(periods_str: str, counts_str: str):
        """ Create dictionary of candles_cnt_by_interval from periods like M1, M5 and counts like 10, 20"""

        periods = [s.strip() for s in periods_str.split(",")]
        counts = [int(s) for s in counts_str.split(",")]

        return dict(zip(periods, counts))

    def read_candles(self):
        # Download history to common folder. Minimal period to be resampled during merge later
        # downloader is already configured with history days to download
        self.downloader.download_candles_inc()
        self.downloader.download_absent_days(datetime.now())
        candles_1min = self.read_candles_downloaded()

        # Produce initial candles
        for period, cnt in self.candles_cnt_by_interval.items():
            # Read cnt + 1 extra for diff candles
            candles_new = pd.DataFrame(self.exchange_candles_feed.read_candles(self.ticker, period, cnt)) \
                .set_index("close_time", drop=False)

            candles_history = candles_1min.resample(period).agg({'open_time': 'first',
                                                                 'close_time': 'last',
                                                                 'open': 'first',
                                                                 'high': 'max',
                                                                 'low': 'min',
                                                                 'close': 'last'})
            candles_history = candles_history[candles_history.index < candles_new.index.min()]
            candles = pd.concat([candles_history, candles_new])

            self._logger.debug(f"Got {len(candles.index)} initial {self.ticker} {period} candles")
            self.candles_by_interval[period] = candles

    def read_candles_downloaded(self):
        """ Read 1min candles from downloaded folder. Do not resample to other periods here. """
        candles_dir = self.downloader.download_dir
        period = self.downloader.period
        days = self.downloader.days
        files = sorted([f for f in os.listdir(candles_dir) if f'_candles_{period}' in f])
        # Read last days' files to one dataframe
        df = pd.concat(
            [pd.read_csv(Path(candles_dir, fname), parse_dates=["open_time", "close_time"]) for fname in files[-days:]])
        df = df.set_index("close_time", drop=False)
        return df

    def apply_buf(self):
        """ Combine candles with buffers"""

        with (self.data_lock):
            for period, buf in self.candles_by_interval_buf.items():
                if buf.empty:
                    continue
                # candles + buf
                candles = self.candles_by_interval.get(period, pd.DataFrame())
                candles = pd.concat([df for df in [candles, buf] if not df.empty]).set_index("close_time", drop=False)
                candles = candles.resample(period).agg(
                    {'open_time': 'first', 'close_time': 'last', 'open': 'first', 'high': 'max', 'low': 'min',
                     'close': 'last', 'vol': 'max'}).sort_index()

                self.candles_by_interval[period] = candles
                self.candles_by_interval_buf[period] = pd.DataFrame()

    def on_candle(self, candle: {}):
        candle_df = pd.DataFrame([candle]).set_index("close_time", drop=False)
        with (self.data_lock):
            period = str(candle["interval"])
            self._logger.debug(f"Got {period} candle: {candle}")
            prev_buf = self.candles_by_interval_buf.get(period, pd.DataFrame())
            # Add to buffer
            self.candles_by_interval_buf[period] = pd.concat([prev_buf, candle_df])
        self.new_data_event.set()

    def has_min_history(self):
        """ If gathered required history """
        for period, min_count in self.candles_cnt_by_interval.items():
            if period not in self.candles_by_interval or len(self.candles_by_interval[period]) < min_count:
                return False
        return True

    def is_alive(self, _):
        dt = datetime.now()
        for i, c in self.candles_by_interval.items():
            candle_max_delta = pd.Timedelta(i)
            if dt - c.index.max() > candle_max_delta * 2:
                # If double candle interval passed, and we did not get a new candle, we are dead
                return False
        return True
