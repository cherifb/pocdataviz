from __future__ import print_function
import logging
import os
import grpc
import kaikosdk
from google.protobuf.json_format import MessageToJson
from kaikosdk import sdk_pb2_grpc
from kaikosdk.core import instrument_criteria_pb2
from kaikosdk.stream.aggregates_ohlcv_v1 import request_pb2 as pb_ohlcv
from kaikosdk.stream.aggregates_vwap_v1 import request_pb2 as pb_vwap
from kaikosdk.stream.market_update_v1 import request_pb2 as pb_market_update
from kaikosdk.stream.market_update_v1 import response_pb2 as pb_reponse_mu
from kaikosdk.stream.market_update_v1 import commodity_pb2 as pb_commodity
from kaikosdk.stream.trades_v1 import request_pb2 as pb_trades
from kaikosdk.stream.index_v1 import request_pb2 as pb_index
from kaikosdk.stream.index_multi_assets_v1 import request_pb2 as pb_index_multi_assets
from kaikosdk.stream.index_forex_rate_v1 import request_pb2 as pb_index_forex_rate
from kaikosdk.stream.aggregated_quote_v2 import request_pb2 as pb_aggregated_quote
import threading
import json

                
def fetch_ohlcv_request(channel: grpc.Channel, aggregate: str, exchange: str, instrument_class: str, code: str):
    try:
        with channel:
            stub = sdk_pb2_grpc.StreamAggregatesOHLCVServiceV1Stub(channel)
            responses = stub.Subscribe(pb_ohlcv.StreamAggregatesOHLCVRequestV1(
                aggregate=aggregate,
                instrument_criteria=instrument_criteria_pb2.InstrumentCriteria(
                    exchange=exchange,
                    instrument_class=instrument_class,
                    code=code
                )
            ))
            for response in responses:
                print("Received message %s" % (MessageToJson(response, including_default_value_fields=True)))
    except grpc.RpcError as e:
        print(e.details(), e.code())
        
def fetch_vvwap_arg(channel: grpc.Channel, aggregate: str, exchange: str, instrument_class: str, code: str):
    try:
        with channel:
            stub = sdk_pb2_grpc.StreamAggregatesVWAPServiceV1Stub(channel)
            responses = stub.Subscribe(pb_vwap.StreamAggregatesVWAPRequestV1(
                aggregate=aggregate,
                instrument_criteria=instrument_criteria_pb2.InstrumentCriteria(
                    exchange=exchange,
                    instrument_class=instrument_class,
                    code=code
                )
            ))
            for response in responses:
                print("Received message %s" % (MessageToJson(response, including_default_value_fields=True)))
    except grpc.RpcError as e:
        print(e.details(), e.code())
    

    try:
        with channel:
            stub = sdk_pb2_grpc.StreamMarketUpdateServiceV1Stub(channel)
            # Globbing patterns are also supported on all fields. See http://sdk.kaiko.com/#instrument-selection for all supported patterns
            responses = stub.Subscribe(pb_market_update.StreamMarketUpdateRequestV1(
                instrument_criteria = instrument_criteria_pb2.InstrumentCriteria(
                    exchange = "binc",
                    instrument_class = "spot",
                    code = "beta-usdt"
                ),
                commodities=[pb_commodity.SMUC_FULL_ORDER_BOOK]
            ))
            for response in responses:
                print("Received message %s" % (MessageToJson(response, including_default_value_fields = True)))
                # print("Received message %s" % list(map(lambda o: o.string_value, response.data.values)))
    except grpc.RpcError as e:
        print(e.details(), e.code())

class _Price_limit:
    def __init__(self, price, amount, side, exchange, timestamp):
        self.price = price
        self.amount = amount
        self.side = side
        self.exchange = exchange
        self.timestamp=timestamp

class _Trade:
    def __init__(self, price, amount, exchange, timestamp):
        self.price = price
        self.amount = amount
        self.exchange = exchange
        timestamp=timestamp

def _apply_order_book_update(order_book, update):
    side = 'bids' if update.StreamMarketUpdateType == 'UPDATED_BID' else 'asks'
    order_list = order_book[side]

    # Find the index of the order with the given price or None if not found
    order_index = next((i for i, order in enumerate(order_list) if order.price == update.price), None)

    # Update or add the order
    if order_index is not None:
        if update.amount == 0:
            # Remove the order from the book if the amount is zero
            order_book[side].pop(order_index)
        else:
            # Update the existing order's amount
            order_book[side][order_index].amount = update.amount
    else:
        if update.amount != 0:
            # Add a new order to the book
            order_book[side].append(Price_limit(update.price, update.amount, side, update.exchange))

    # Sort the order book correctly
    order_book[side].sort(key=lambda x: x.price, reverse=(side == 'asks'))

    # Remove any zero-amount orders
    order_book[side] = [order for order in order_book[side] if order.amount > 0]

def _display_order_book_cmd(order_book):
    # Function to display the order book
    print("Order Book:")
    for side in ['asks', 'bids']:
        print(f"{side.capitalize()}:")
        for order in order_book[side]:
            print(f"Price: {order.price}, Amount: {order.amount}, Venue: {order.exchange}" )
        
def fetch_order_book_arg(channel: grpc.Channel, exchange: str, instrument_class : str, code : str):
    order_book = {'asks': [], 'bids': []}
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
                if response.update_type == pb_reponse_mu.StreamMarketUpdateResponseV1.StreamMarketUpdateType.SNAPSHOT:
                    order_book = {'asks': [], 'bids': []}
                    # Create Price_limit objects from the snapshot for asks and bids
                    order_book['asks'] = [Price_limit(price=ask.price, amount=ask.amount, side='ask', exchange=response.exchange,timestamp=response.ts_event) 
                                          for ask in response.snapshot.asks]
                    order_book['bids'] = [Price_limit(price=bid.price, amount=bid.amount, side='bid', exchange=response.exchange, timestamp=response.ts_event) 
                                          for bid in response.snapshot.bids]
                    # Sort the asks and bids after initializing
                    order_book['asks'].sort(key=lambda x: x.price)
                    order_book['bids'].sort(key=lambda x: x.price, reverse=True)
                else:
                    apply_order_book_update(order_book, response)
    except grpc.RpcError as e:
        print(e.details(), e.code())
        return None  # Return None or an appropriate error indicator

def fetch_trades_arg(channel: grpc.Channel, exchange: str, instrument_class : str, code : str):
    try:
        with channel:
            stub = sdk_pb2_grpc.StreamMarketUpdateServiceV1Stub(channel)
            responses = stub.Subscribe(pb_market_update.StreamMarketUpdateRequestV1(
                instrument_criteria=instrument_criteria_pb2.InstrumentCriteria(
                    exchange=exchange,
                    instrument_class=instrument_class,
                    code=code
                ),
                commodities=[pb_commodity.SMUC_TRADE]
            ))
            for response in responses:
                print(response)
    except grpc.RpcError as e:
        print(e.details(), e.code())
        return None  # Return None or an appropriate error indicator

def fetch_aggregated_quote_arg(channel: grpc.Channel, instrument_class : str, code : str):
    try:
        with channel:
            stub = sdk_pb2_grpc.StreamAggregatedQuoteServiceV2Stub(channel)
            # Globbing patterns are also supported on all fields. See http://sdk.kaiko.com/#instrument-selection for all supported patterns
            responses = stub.Subscribe(pb_aggregated_quote.StreamAggregatedQuoteRequestV2(
                instrument_class=instrument_class,
                code = code
            ))
            for response in responses:
                print("Received message %s" % (MessageToJson(response, including_default_value_fields = True)))
                # print("Received message %s" % list(map(lambda o: o.string_value, response.data.values)))
    except grpc.RpcError as e:
        print(e.details(), e.code())

def run():
    credentials = grpc.ssl_channel_credentials(root_certificates=None)
    call_credentials = grpc.access_token_call_credentials(os.environ['KAIKO_API_KEY'])
    composite_credentials = grpc.composite_channel_credentials(credentials, call_credentials)
    # Requesting user input for the parameters
    aggregate = input("Enter the aggregate time (e.g., '1s', '1m', '1h'): ")
    exchange = input("Enter the exchange code (e.g., 'cbse'): ")
    instrument_class = input("Enter the instrument class (e.g., 'spot'): ")
    code = input("Enter the instrument code (e.g., 'btc-usd'): ")
    # Process the Order Book market updates if the stream is valid
    channel_OB = grpc.secure_channel('gateway-v0-grpc.kaiko.ovh', composite_credentials)
    fetch_order_book_arg(channel_OB, exchange,instrument_class, code)
    # Process the Trades if the Stream is valid
    channel_trades = grpc.secure_channel('gateway-v0-grpc.kaiko.ovh', composite_credentials)
    fetch_trades_arg(channel_trades,exchange,instrument_class,code)
    # Process the Aggregated quote if the Stream is valid
    channel_aggquote = grpc.secure_channel('gateway-v0-grpc.kaiko.ovh', composite_credentials)
    fetch_aggregated_quote_arg(channel_aggquote)
    #Process the OHLCV if the Stream is valid
    channel_OHLCVs = grpc.secure_channel('gateway-v0-grpc.kaiko.ovh', composite_credentials)
    fetch_ohlcv_request(channel_OHLCVs,aggregate, exchange, instrument_class,code)
    #Process the VWAP if the Stream is valid
    channel_VWAPs = grpc.secure_channel('gateway-v0-grpc.kaiko.ovh', composite_credentials)
    fetch_ohlcv_request(channel_VWAPs,aggregate, exchange, instrument_class,code)


   




if __name__ == '__main__':
    logging.basicConfig()
    run()
