# NotionalQuoteManager.py
from __future__ import print_function
import sys
import logging
import os
import threading
import grpc
from datetime import datetime
from OrderbookManager import OrderBookManager
from kaiko_research.kaiko import KaikoAPIWrapper


class NotionalQuoteManager:
    def __init__(self):
        self.notional_quote_json = {
            'ask': None,
            'bid': None,
            'spread':None
        }
        self.size = None
        self.orderBookManager = None
        self.lock = threading.Lock()
        self.update_event = threading.Event() 

    def _fetch_notional_quote(self, channel, exchange, instrument_class, code, notionalAmount):
    # Thread loop to continuously calculate notional quote
        while True:
            # Wait for the order book update event
            self.orderBookManager.update_event.wait()
            self.orderBookManager.update_event.clear()

            with self.lock:
                # Access the updated order book
                order_book = self.orderBookManager.get_order_book()
                # Compute the Ask side
                ask = self._calculate_total_price(order_book['asks'], notionalAmount)
                #compute the Bid side
                bid = self._calculate_total_price(order_book['bids'], notionalAmount)
                spread=bid-ask
                #set the variables
                if spread>0:
                    self.notional_quote_json['ask']=ask
                    self.notional_quote_json['bid']=bid
                    self.notional_quote_json['spread']=spread 
                #notify of the update
                self.update_event.set()

    def _calculate_total_price(self, price_levels, notional_amount):
        total_price = 0
        remaining_amount = notional_amount
        # Iterate on the order book price levels
        for pricelevel in price_levels:
            if remaining_amount <= 0:
                break
            # Calculate the amount that can be transacted at this price level
            transactable_amount = min(pricelevel.amount, remaining_amount)
            # Update the total price
            total_price += transactable_amount * pricelevel.price
            # Decrement the remaining amount
            remaining_amount -= transactable_amount
        # Calculate the price per unit
        price_per_unit = total_price / notional_amount if notional_amount else 0
        return price_per_unit

    def start(self, channel, exchange, instrument_class, code, notionalAmount):
        #Init
        self.size = notionalAmount
        self.orderBookManager = OrderBookManager()
        # define threads
        orderbookthread = threading.Thread(target=self.orderBookManager.start, args=(channel, exchange, instrument_class, code))
        orderbookthread.daemon = True
        Quotethread = threading.Thread(target=self._fetch_notional_quote, args=(channel, exchange, instrument_class, code, notionalAmount))
        Quotethread.daemon = True
        # Start the OB process in a new thread
        orderbookthread.start()
        # Start the quote process in a new thread
        Quotethread.start()

    def get_notional_quote_json(self):
        with self.lock:
            return self.notional_quote_json


def test():
    # convert Notional in a size
    kw = KaikoAPIWrapper(os.environ['KAIKO_API_KEY'])
    print(kw.get_enpoints_information())
    print(kw.get_endpoint_parameters("Cross Price"))
    cross_price = kw.get_data("Cross Price", base_assets = "btc", quote_asset = "usd")
    print (cross_price)
    input("blah")
    # Requesting user input for the parameters
    exchange = input("Enter the exchange code (e.g., 'cbse'): ")
    instrument_class = input("Enter the instrument class (e.g., 'spot'): ")
    base = input("Enter the instrument code (e.g., 'btc'): ")
    quote = input("Enter the instrument code (e.g., 'usd'): ")
    code = f"{base}-{quote}"
    notional_amount = int(input ("Enter th notional amount in USD : "))
    # Redirect print output to the file
    now = datetime.now().strftime("%Y-%m-%d_b%H-%M-%S")
    filename = f"{now}_quote.log"
    log_file = open(filename, 'w')
    sys.stdout = log_file
    print(f"Markets: {exchange}:{instrument_class}:{code}")
    print(f"Quote size: {notional_amount}")
    #grpc config
    credentials = grpc.ssl_channel_credentials(root_certificates=None)
    call_credentials = grpc.access_token_call_credentials(os.environ['KAIKO_API_KEY'])
    composite_credentials = grpc.composite_channel_credentials(credentials, call_credentials)
    channel_OB = grpc.secure_channel('gateway-v0-grpc.kaiko.ovh', composite_credentials)
    # Notional Quote Manager instance
    manager = NotionalQuoteManager()
    # Start processing
    manager.start(channel_OB,exchange, instrument_class,code, notional_amount)
    try:
        while True:
            manager.update_event.wait()  # Block until data is updated
            #print(manager.orderBookManager.get_order_book_bbo_json()) # print the order book for debug purpose
            if manager.get_notional_quote_json()['spread']>0: print(manager.get_notional_quote_json())
            manager.update_event.clear()  # Reset the event
    except KeyboardInterrupt:
            pass
            log_file.close()

if __name__ == '__main__':
    logging.basicConfig()
    test()
