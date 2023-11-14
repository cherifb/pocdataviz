from __future__ import print_function
import sys
import logging
import os
import threading
import json
import grpc
import kaikosdk
from datetime import datetime
from kaikosdk import sdk_pb2_grpc
from kaikosdk.core import instrument_criteria_pb2
from kaikosdk.stream.market_update_v1 import request_pb2 as pb_market_update
from kaikosdk.stream.market_update_v1 import response_pb2 as pb_reponse_mu
from kaikosdk.stream.market_update_v1 import commodity_pb2 as pb_commodity


class _Price_limit:
    def __init__(self, price, amount, side, exchange, seconds, nanos):
        self.price = price
        self.amount = amount
        self.side = side
        self.exchange = exchange
        self.t_s= seconds
        self.t_n = nanos
    
    def get_PriceLimit_json(self):
        return json.dumps({
            'price': self.price,
            'amount': self.amount,
            'side': self.side,
            'exchange': self.exchange,
            'timestamp_seconds': self.t_s,
            'timestamp_nanos': self.t_n
        })
class OrderBookManager:
    def __init__(self):
        self.order_book = {'asks': [], 'bids': []}
        self.order_book_json = {} 
        self.lock = threading.Lock()
        self.update_event = threading.Event() 
        self.channel = None
        self.code = None
        self.instrument_class =None
        self.order_book_bbo = {
            'bestAsk': None, 
            'bestBid': None, 
        }
        self.order_book_bottom =   {
            'highAsk': None, 
            'lowBid': None
        }

    def _apply_order_book_update(self, update):
        side = 'bids' if update.StreamMarketUpdateType == 'UPDATED_BID' else 'asks'
        order_list = self.order_book[side]
        # Find the index of the order with the given price on the same venue or None if not found
        order_index = next((i for i, order in enumerate(order_list) if order.price == update.price and update.exchange==order.exchange), None)
        # Update or add the order
        if order_index is not None:
            if update.amount == 0:
                # Remove the order from the book if the amount is zero
                self.order_book[side].pop(order_index)
            else:
                # Update the existing order's amount
                self.order_book[side][order_index].amount = update.amount
        else:
            if update.amount != 0:
                # Add a new order to the book
                self.order_book[side].append(_Price_limit(update.price, update.amount, side, update.exchange, update.ts_event.seconds, update.ts_event.nanos))
        # Sort the order book correctly
        self.order_book[side].sort(key=lambda x: x.price, reverse=(side == 'bids'))
        # Remove any zero-amount orders
        self.order_book[side] = [order for order in self.order_book[side] if order.amount > 0]
    
    def _fetch_order_book_arg(self, channel: grpc.Channel, exchange: str, instrument_class : str, code : str):
        ob_synced=[]
        try:
            with channel:
                stub = sdk_pb2_grpc.StreamMarketUpdateServiceV1Stub(channel)
                responses = stub.Subscribe(pb_market_update.StreamMarketUpdateRequestV1(
                    instrument_criteria=instrument_criteria_pb2.InstrumentCriteria(
                        exchange=exchange,
                        instrument_class=instrument_class,
                        code=code
                    ),
                    commodities=[pb_commodity.SMUC_FULL_ORDER_BOOK]
                ))
                for response in responses:
                    with self.lock:
                        if response.exchange not in ob_synced and response.update_type == pb_reponse_mu.StreamMarketUpdateResponseV1.StreamMarketUpdateType.SNAPSHOT:
                            # first sync of the order book
                            print("Synced with: ", {response.exchange})
                            ob_synced.append(response.exchange)
                            # Create Price_limit objects from the snapshot for asks and bids
                            for ask in response.snapshot.asks:
                                self.order_book['asks'].append(_Price_limit(price=ask.price, amount=ask.amount, side='ask', exchange=response.exchange,seconds=response.ts_event.seconds, nanos=response.ts_event.nanos))
                            for bid in response.snapshot.bids:
                                self.order_book['bids'].append(_Price_limit(price=bid.price, amount=bid.amount, side='bid', exchange=response.exchange, seconds=response.ts_event.seconds, nanos=response.ts_event.nanos))
                            # Sort the asks and bids after initializing
                            self.order_book['asks'].sort(key=lambda x: x.price)
                            self.order_book['bids'].sort(key=lambda x: x.price, reverse=True)
                        elif response.exchange in ob_synced and  response.update_type == pb_reponse_mu.StreamMarketUpdateResponseV1.StreamMarketUpdateType.SNAPSHOT:
                            #snapshot recived for a given exchange while the OB was Synced
                            #we remove all price limits for that exchange in the OB
                            order_index = next((i for i, order in enumerate(self.order_book['asks']) if order.exchange == response.exchange), None)
                            while order_index is not None :
                                self.order_book['asks'].pop(order_index)
                                order_index = next((i for i, order in enumerate(self.order_book['asks']) if order.exchange == response.exchange), None)
                            order_index = next((i for i, order in enumerate(self.order_book['bids']) if order.exchange == response.exchange), None)
                            while order_index is not None :
                                self.order_book['bids'].pop(order_index)
                                order_index = next((i for i, order in enumerate(self.order_book['asks']) if order.exchange == response.exchange), None)
                            # Process the received snapshot and reorder the book
                            for ask in response.snapshot.asks:
                                self.order_book['asks'].append(_Price_limit(price=ask.price, amount=ask.amount, side='ask', exchange=response.exchange,seconds=response.ts_event.second, nanos=response.ts_event.nanos))
                            for bid in response.snapshot.bids:
                                self.order_book['bids'].append(_Price_limit(price=bid.price, amount=bid.amount, side='bid', exchange=response.exchange, seconds=response.ts_event.second, nanos=response.ts_event.nanos))
                            self.order_book['asks'].sort(key=lambda x: x.price)
                            self.order_book['bids'].sort(key=lambda x: x.price, reverse=True)
                        else :
                            #process the individual Tick level 2 udpate and update the order book
                            self._apply_order_book_update(response)
                        #update attributes
                        self.order_book_json = json.dumps({
                            side: [vars(order) for order in orders] for side, orders in self.order_book.items()
                        })
                        self.order_book_bbo['bestBid']=self.order_book['bids'][0].get_PriceLimit_json()
                        self.order_book_bbo['bestAsk']=self.order_book['asks'][0].get_PriceLimit_json()
                        self.order_book_bottom['highAsk']=self.order_book['asks'][-1].get_PriceLimit_json()
                        self.order_book_bottom['lowBid']=self.order_book['bids'][-1].get_PriceLimit_json()
                        self.update_event.set()
        except grpc.RpcError as e:
            print(e.details(), e.code())
            return None  # Return None or an appropriate error indicator
    
    def start(self, channel, exchange, instrument_class, code):
        #Init
        self.channel=channel
        self.code=code
        self.instrument_class = instrument_class
        # Start the fetching process in a new thread
        thread = threading.Thread(target=self._fetch_order_book_arg, args=(channel, exchange, instrument_class, code))
        thread.daemon = True
        thread.start()
    
    def get_order_book(self):
        #Safely retrieve the latest order book data
        with self.lock:
            return self.order_book
    
    def get_order_book_json(self):
        #Safely retrieve the latest order book data
        with self.lock:
            return self.order_book_json

    def get_order_book_bbo_json(self):
        #Safely retrieve the latest order book data
        with self.lock:
            return self.order_book_bbo
    def get_order_book_bottom_json(self):
        #Safely retrieve the latest order book data
        with self.lock:
            return self.order_book_bottom    
class _Trade:
    def __init__(self, price, amount, exchange, timestamp):
        self.price = price
        self.amount = amount
        self.exchange = exchange
        timestamp=timestamp

   


def test():
    # Requesting user input for the parameters
    exchange = input("Enter the exchange code (e.g., 'cbse'): ")
    instrument_class = input("Enter the instrument class (e.g., 'spot'): ")
    code = input("Enter the instrument code (e.g., 'btc-usd'): ")
    # Redirect print output to the file
    now = datetime.now().strftime("%Y-%m-%d_b%H-%M-%S")
    filename = f"{now}.log"
    log_file = open(filename, 'w')
    sys.stdout = log_file
    print(f"{exchange}:{instrument_class}:{code}")
    #grpc config
    credentials = grpc.ssl_channel_credentials(root_certificates=None)
    call_credentials = grpc.access_token_call_credentials(os.environ['KAIKO_API_KEY'])
    composite_credentials = grpc.composite_channel_credentials(credentials, call_credentials)
    channel_OB = grpc.secure_channel('gateway-v0-grpc.kaiko.ovh', composite_credentials)
    # Order Book Manager instance
    manager = OrderBookManager()
    # Start processing
    manager.start(channel_OB,exchange, instrument_class,code)
    try:
        while True:
            manager.update_event.wait()  # Block until data is updated
            print("NEW UPDATE")
            print(manager.get_order_book_json())
            manager.update_event.clear()  # Reset the event
    except KeyboardInterrupt:
            pass
            log_file.close()


if __name__ == '__main__':
    logging.basicConfig()
    test()
