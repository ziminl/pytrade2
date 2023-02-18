import logging
from typing import List, Dict, Optional
from binance.spot import Spot as Client
from broker.PairOrdersBroker import PairOrdersBroker


class BinanceBroker(PairOrdersBroker):
    """
    Orders management: buy, sell etc
    """

    def __init__(self, client: Client):
        super().__init__()
        self._log = logging.getLogger(self.__class__.__name__)
        self.client: Client = client
        self.order_sides = {1: "BUY", -1: "SELL"}

        self._log.info(f"Current opened trade: {self.cur_trade}")
        self._log.info("Completed init broker")

    def create_order(self, symbol: str, order_type: int, quantity: float, price: Optional[float], stop_loss: Optional[float]) -> float:
        """
        Buy or sell with take profit and stop loss
        Binance does not support that in single order, so make 2 orders: main and stoploss/takeprofit
        """
        return 0
        if not order_type:
            return
        ticker_size = 2

        side = self.order_sides[order_type]

        self._log.info(
            f"Create {symbol} {side} order, price: {price}, stop loss: {stop_loss}, quantity: {quantity}")
        stop_loss = round(stop_loss, ticker_size)

        # Main buy or sell order with stop loss
        res = self.client.new_order(
            symbol=symbol,
            side=side,
            type="MARKET",
            stop_loss=stop_loss,
            quantity=quantity)
        filled_price = float(res["fills"][0]["price"] if res["fills"] else price)
        if not filled_price:
            raise Exception("New order filled_price is empty")

        # Take profit
        res = self.client.new_order(
            symbol=symbol,
            side=side,
            type="MARKET",
            quantity=quantity)
        self._log.debug(f"Take profit order response: {res}")

        return filled_price

    def close_opened_positions(self, ticker: str):
        if not self.client:
            return
        opened_quantity, opened_orders = self.get_opened_positions(ticker)
        if opened_orders:
            self._log.info("Cancelling opened orders")
            self.client.cancel_open_orders(ticker)
        if opened_quantity:
            # if we sold (-1) we should buy and vice versa
            side = "BUY" if opened_quantity < 0 else "SELL"
            self._log.info(f"Creating {-opened_quantity} {side} order to close existing positions")
            res = self.client.new_order(symbol=ticker, side=side, type="MARKET",
                                        quantity=abs(opened_quantity))
            self._log.info(res)

    def get_opened_positions(self, symbol: str) -> (float, List[Dict]):
        """
        Quantity of symbol we have in portfolio
        """
        self._log.debug("Checking opened orders")

        orders, opened_quantity = self.client.get_open_orders(symbol), 0
        if orders:
            # Currently opened orders is trailing stop loss against main order
            last_order = orders[-1]
            opened_quantity = float(last_order["origQty"])
            # stoploss is buy => main order was sell
            if last_order["side"] == "BUY": opened_quantity *= -1.0
        # [{'symbol': 'BTCUSDT', 'orderId': 6104154, 'orderListId': -1, 'clientOrderId': 'Rwcdh0uW8Ocux22TXmpFmD', 'price': '21910.94000000', 'origQty': '0.00100000', 'executedQty': '0.00000000', 'cummulativeQuoteQty': '0.00000000', 'status': 'NEW', 'timeInForce': 'GTC', 'type': 'STOP_LOSS_LIMIT', 'side': 'SELL', 'stopPrice': '21481.31000000', 'trailingDelta': 200, 'icebergQty': '0.00000000', 'time': 1656149854953, 'updateTime': 1656159716195, 'isWorking': True, 'origQuoteOrderQty': '0.00000000'}]
        self._log.info(f"We have {opened_quantity} {symbol} in portfolio and {len(orders)} opened orders for {symbol}")
        return opened_quantity, orders
