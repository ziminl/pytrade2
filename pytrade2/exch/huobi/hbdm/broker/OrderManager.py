import datetime
from datetime import datetime
from logging import Logger
from multiprocessing import RLock
from typing import Optional

from sqlalchemy.orm.session import Session

from exch.huobi.hbdm.HuobiRestClient import HuobiRestClient
from exch.huobi.hbdm.broker.AccountManagerHbdm import AccountManagerHbdm
from model.Trade import Trade
from model.TradeStatus import TradeStatus


class OrderManager:
    """ Creation of main order with sl/tp """

    class HuobiOrderStatus:
        """
        Huobi rests response constants
        https://www.huobi.com/en-us/opend/newApiPages/?id=8cb85ba1-77b5-11ed-9966-0242ac110003
        """
        filled = 6

    class HuobiTradeType:
        """
        Huobi rests response constants
        https://www.huobi.com/en-us/opend/newApiPages/?id=8cb85ba1-77b5-11ed-9966-0242ac110003
        """
        buy = 17
        sell = 18

    class HuobiOrderType:
        """
        Huobi rests response constants
        https://www.huobi.com/en-us/opend/newApiPages/?id=8cb85ba1-77b5-11ed-9966-0242ac110003
        """
        all = 1
        finished = 2

    def __init__(self):
        # All variables will be redefined in child classes
        self._log: Optional[Logger] = None
        self.cur_trade: Optional[Trade] = None
        self.prev_trade: Optional[Trade] = None
        self.account_manager: Optional[AccountManagerHbdm] = None
        self.db_session: Optional[Session] = None
        self.rest_client: Optional[HuobiRestClient] = None
        self.trade_lock: Optional[RLock] = None
        self.allow_trade = False
        self.price_precision = 2

    def create_cur_trade(self, symbol: str, direction: int,
                         quantity: float,
                         price: Optional[float],
                         stop_loss_price: float,
                         take_profit_price: Optional[float]) -> Optional[Trade]:
        if not self.allow_trade:
            return None

        with self.trade_lock:
            if self.cur_trade:
                self._log.info(f"Can not create current trade because another exists:{self.cur_trade}")
            side = Trade.order_side_names[direction]
            # Adjust prices to precision
            limit_ratio = 0.01
            price, sl_trigger_price, sl_order_price, tp_trigger_price, tp_order_price = self.adjust_prices(
                direction, price, stop_loss_price, take_profit_price, self.price_precision, limit_ratio)
            self._log.info(
                f"Creating current {symbol} {side} trade. price: {price}, "
                f"sl trigger: {sl_trigger_price}, sl order: {sl_order_price},"
                f" tp trigger: {tp_trigger_price}, tp order: {tp_order_price},"
                f"price precision: {self.price_precision}, limit ratio: {limit_ratio}")
            # Prepare create order command
            path = "/linear-swap-api/v1/swap_cross_order"
            client_order_id = int(datetime.utcnow().timestamp())

            # Works, but order types are limit => risk that price would fly out
            # data = {"contract_code": symbol,
            #         "client_order_id": client_order_id,
            #         # "contract_type": "swap",
            #         "volume": quantity,
            #         "direction": side,
            #         "price": price,
            #         "lever_rate": 1,
            #         "order_price_type": "limit",
            #         "tp_trigger_price": tp_trigger_price,
            #         "tp_order_price": tp_order_price,
            #         "reduce_only": 0,  # 0 for opening order
            #         "sl_trigger_price": sl_trigger_price,
            #         "sl_order_price": sl_order_price,
            #         "tp_order_price_type": "limit",
            #         "sl_order_price_type": "limit"
            #         }
            # Works, but tp is limit => bad exec price, no profit
            # data = {"contract_code": symbol,
            #         "client_order_id": client_order_id,
            #         # "contract_type": "swap",
            #         "volume": quantity,
            #         "direction": side,
            #         "price": price,
            #         "lever_rate": 1,
            #         "order_price_type": "optimal_5_fok",
            #         "tp_trigger_price": tp_trigger_price,
            #         "tp_order_price": tp_order_price,
            #         "reduce_only": 0,  # 0 for opening order
            #         "sl_trigger_price": sl_trigger_price,
            #         "sl_order_price": sl_order_price,
            #         "tp_order_price_type": "limit",
            #         "sl_order_price_type": "limit"
            #         }
            data = {"contract_code": symbol,
                    "client_order_id": client_order_id,
                    # "contract_type": "swap",
                    "volume": quantity,
                    "direction": side,
                    "price": price,
                    "lever_rate": 1,
                    "order_price_type": "optimal_5_fok",
                    "tp_trigger_price": tp_trigger_price,
                    # "tp_order_price": tp_order_price,
                    "reduce_only": 0,  # 0 for opening order
                    "sl_trigger_price": sl_trigger_price,
                    "sl_order_price": sl_order_price,
                    "tp_order_price_type": "optimal_5",
                    "sl_order_price_type": "limit"
                    }
            self._log.debug(f"Create order params: {data}")
            # Request to create a new order
            res = self.rest_client.post(path=path, data=data)

            # Process result
            self._log.info(f"Create order response: {res}")
            if res["status"] == "ok":
                self._log.debug(f"Create order response: {res}")

                # Get order details, fill in current trade
                info = self.get_order_info(client_order_id, ticker=symbol)
                self.cur_trade = self.res2trade(info)
                # Fill in sltp info
                sltp_info = self.get_sltp_orders_info(self.cur_trade.open_order_id)
                self.update_trade_sltp(sltp_info, self.cur_trade)

                # Save current trade to db
                self.db_session.add(self.cur_trade)
                self.db_session.commit()
                self._log.info(f"Opened trade: {self.cur_trade}")
            else:
                self._log.error(f"Error creating order: {res}")

            return self.cur_trade

    @staticmethod
    def adjust_prices(direction, price: float, stop_loss_price: float, take_profit_price: float, price_precision: int,
                      limit_ratio: float) -> \
            (float, float, float, float, float):
        """ Calc trigger and order prices, adjust precision """
        price = float(round(price, price_precision))
        tp_trigger_price = float(round(take_profit_price, price_precision))
        tp_order_price = float(round(take_profit_price * (1 - direction * limit_ratio), price_precision))
        sl_trigger_price = float(round(stop_loss_price, price_precision))
        sl_order_price = float(round(stop_loss_price * (1 - direction * limit_ratio), price_precision))
        return price, sl_trigger_price, sl_order_price, tp_trigger_price, tp_order_price

    def get_sltp_orders_info(self, main_order_id):
        res = self.rest_client.post("/linear-swap-api/v1/swap_cross_relation_tpsl_order",
                                    {"contract_code": "BTC-USDT", "order_id": main_order_id})
        self._log.debug(f"Got sltp order info: f{res}")
        return res

    @staticmethod
    def update_trade_sltp(sltp_res, trade):
        """ Update trade from sltp"""
        # sl/tp response example
        # {'status': 'ok', 'data':
        # {'contract_type': 'swap', 'business_type': 'swap', 'pair': 'BTC-USDT', 'symbol': 'BTC',
        #  'contract_code': 'BTC-USDT', 'margin_mode': 'cross', 'margin_account': 'USDT', 'volume': 1, 'price': 26720,
        #  'order_price_type': 'limit', 'direction': 'buy', 'offset': 'both', 'lever_rate': 1,
        #  'order_id': 1119997217854570496, 'order_id_str': '1119997217854570496', 'client_order_id': 1687058944,
        #  'created_at': 1687069745272, 'trade_volume': 1, 'trade_turnover': 26.542, 'fee': -0.0106168,
        #  'trade_avg_price': 26542.0, 'margin_frozen': 0, 'profit': 0, 'status': 6, 'order_type': 1,
        #  'order_source': 'api', 'fee_asset': 'USDT', 'canceled_at': 0, 'tpsl_order_info': [
        #     {'volume': 1.0, 'direction': 'sell', 'tpsl_order_type': 'tp', 'order_id': 1119997217904902144,
        #      'order_id_str': '1119997217904902144', 'trigger_type': 'ge', 'trigger_price': 27000.0,
        #      'order_price': 27270.0, 'created_at': 1687069745290, 'order_price_type': 'limit',
        #      'relation_tpsl_order_id': '1119997217909096448', 'status': 2, 'canceled_at': 0, 'fail_code': None,
        #      'fail_reason': None, 'triggered_price': None, 'relation_order_id': '-1'},
        #     {'volume': 1.0, 'direction': 'sell', 'tpsl_order_type': 'sl', 'order_id': 1119997217909096448,
        #      'order_id_str': '1119997217909096448', 'trigger_type': 'le', 'trigger_price': 26000.0,
        #      'order_price': 25740.0, 'created_at': 1687069745291, 'order_price_type': 'limit',
        #      'relation_tpsl_order_id': '1119997217904902144', 'status': 2, 'canceled_at': 0, 'fail_code': None,
        #      'fail_reason': None, 'triggered_price': None, 'relation_order_id': '-1'}],
        #  'trade_partition': 'USDT'}, 'ts': 1687071763277}

        if "status" in sltp_res and sltp_res["status"] == "ok":
            if len(sltp_res["data"]["tpsl_order_info"]) != 2:
                raise RuntimeError(f"Error: sl/tp order count != 2: {sltp_res}")
            (sl_order, tp_order) = sorted(sltp_res["data"]["tpsl_order_info"], key=lambda item: item["order_price"],
                                          reverse=trade.direction() == -1)
            trade.stop_loss_order_id = ",".join([sl_order["order_id_str"], tp_order["order_id_str"]])
            trade.stop_loss_price = sl_order["order_price"]
            trade.take_profit_price = tp_order["order_price"] if tp_order["order_price"] else tp_order["trigger_price"]

        return trade

    @staticmethod
    def res2trade(res: dict):
        """ Convert get order response to trade model"""
        data = res["data"][0]
        dt = datetime.utcfromtimestamp(data["created_at"] / 1000)

        trade = Trade()
        trade.ticker = data["contract_code"]
        trade.side = data["direction"].upper()
        trade.quantity = data["volume"]
        trade.open_order_id = str(data["order_id"])
        trade.open_time = dt
        trade.open_price = data["trade_avg_price"]
        # ??? Process status better
        trade.status = TradeStatus.opened if data["status"] == OrderManager.HuobiOrderStatus.filled \
            else TradeStatus.opening
        return trade

    def get_order_info(self, client_order_id: int, ticker: str):
        """ Request order from exchange"""

        path = "/linear-swap-api/v1/swap_cross_order_info"
        data = {"client_order_id": client_order_id, "contract_code": ticker}
        res = self.rest_client.post(path, data)
        self._log.debug(f"Got order {res}")
        return res
