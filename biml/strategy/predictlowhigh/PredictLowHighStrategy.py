import logging
from pathlib import Path
from typing import Dict, Deque, List
from feed.BinanceBidAskFeed import BinanceBidAskFeed
from feed.BinanceWebsocketFeed import BinanceWebsocketFeed
from strategy.PeriodicalLearnStrategy import PeriodicalLearnStrategy
from strategy.StrategyBase import StrategyBase
import pandas as pd
from datetime import datetime, timedelta

from strategy.predictlowhigh.PredictLowHighFeatures import PredictLowHighFeatures


class PredictLowHighStrategy(StrategyBase, PeriodicalLearnStrategy):
    """
    Listen price data from web socket, predict future low/high
    """

    def __init__(self, broker, config: Dict):
        StrategyBase.__init__(self, broker, config)
        PeriodicalLearnStrategy.__init__(self, config)
        self._log = logging.getLogger(self.__class__.__name__)

        self.config = config
        self.tickers = self.config["biml.tickers"].split(",")
        self.model_dir = self.config["biml.model.dir"]
        self.min_history_interval = pd.Timedelta("2 seconds")

        if self.model_dir:
            self.model_weights_dir = str(Path(self.model_dir, self.__class__.__name__, "weights"))
            self.model_Xy_dir = str(Path(self.model_dir, self.__class__.__name__, "Xy"))
            Path(self.model_Xy_dir).mkdir(parents=True, exist_ok=True)

        self._logger = logging.getLogger(self.__class__.__name__)
        self.ticker = pd.DataFrame(columns=BinanceBidAskFeed.bid_ask_columns).set_index("datetime")
        self.buffer = []

        self.bid_ask: pd.DataFrame = pd.DataFrame()
        self.level2: pd.DataFrame = pd.DataFrame()

    def run(self, client):
        """
        Attach to the feed and listen
        """
        feed = BinanceWebsocketFeed(tickers=self.tickers)
        feed.consumers.append(self)
        feed.run()

    def on_level2(self, level2: List[Dict]):
        """
        Got new order book items event
        """
        new_df = pd.DataFrame([level2], columns=level2.keys()).set_index("datetime", drop=False)
        self.level2 = self.level2.append(new_df)
        #self.level2 = pd.concat([self.level2, new_df]) if self.level2 is not None else new_df
        self.learn_or_skip()

    def on_ticker(self, ticker: dict):
        new_df = pd.DataFrame([ticker], columns=ticker.keys()).set_index("datetime", drop=False)
        self.bid_ask = self.bid_ask.append(new_df)
        #self.bid_ask = self.bid_ask if self.bid_ask is not None else new_df
        self.learn_or_skip()

    def learn(self):
        self._log.info("Learning")
        interval = self.bid_ask.index.max() - self.bid_ask.index.min()

        if interval < self.min_history_interval:
            print(f"Not enough data to learn. Required {self.min_history_interval} but exists {interval}")
            return

        features, targets = PredictLowHighFeatures.features_targets_of(self.bid_ask)

