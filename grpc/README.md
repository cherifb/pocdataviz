# Python SDK
The attached classes allow you to
- [Fetch a spot Full Order Book tick by tick ](OrderBookManager.py).
This will allow the user to instanciate an Order Book Manager that connects to Kaiko's stream, sync and maintain a consolidated order book accross exchanges (e.g. btc-usd market accross all exchanges covered by Kaiko Stream L2). The order book is maintained and updated upon each individual L2 tick level

- [Fetch a Notional Quote](NotionalQuoteManager.py).
This will allow the user to instanciate an Notinal Quote Manager that computes in real time the best quote available on the market based on the markets available on Kaiko Stream. The Notional Quote Manager instanciates an OrderBookManager as property and computes the quote asynchronously, recomputing each time the underlyin order book observes a tick level 2 change. While the quote computes, the order book can be see some updates for that will not be captured (edge effect of multi threading) - Still the quote is computed as close to RT and tick level 2 as possible. This can result to some negative spreads particularily while the OrderBookManager is still syncing all the different venues order books in a single one. Negative spread occurrences (that are the product of asynchrnocity) are excluded. Only if there is a large arbitrage opportunity accross venue would the spread be functionally negative (vs technically) - in which case the quote woul become stale, indicating the detection of an arbitrage opportnity on the market.
User can access the underlying consolidated order book used by the quote to get the Order book in real time (bearing in mind that the quote and the order book are asynchronous as run by two different threads)

- [how to handle end of stream / resubscription](resubscribe.py).
Disconnection can happen for lots of reasons (client or server side network, idle consumer for a very long time, etc.) and should be handled by resubscribing. Reconnection is already handled automatically by gRPC client library.

## Requirements

You will need to have Python 3.9 installed on your machine
Installation can be done via this tutorial (<https://realpython.com/installing-python/>) if not already present.

You will also need  dependency tools

- `pip` (usually already present in your Python 3 installation)
- `pipenv` that you can install with `pip install pipenv` (or other means, see <https://docs.pipenv.org/#install-pipenv-today>)

If you are using other tools like `conda`, `virtualenv` or `venv`, please refer to this documentation to see migration paths (<https://docs.pipenv.org/advanced/#pipenv-and-conda>) or your own tool documentation.

## Run with pipenv

- Install:

```bash
pipenv install
```

- Run :

```bash
pipenv run python endpoints.py
```

Note that for this particular step, you will need to setup an environment variable `KAIKO_API_KEY` with a valid Kaiko API key, otherwise you will get an error such as `PERMISSION_DENIED: not authorized`.

## Run with local python installation

- Install:

```bash
pip install -r requirements.txt
```

- Build :

```bash
python endpoints.py
```

Note that for this particular step, you will need to setup an environment variable `KAIKO_API_KEY` with a valid Kaiko API key, otherwise you will get an error such as `PERMISSION_DENIED: not authorized`.

## Fix potential SSL issues

If you're having gRPC errors such as `GPRC ERROR 14 - Unavailable` or `OPENSSL_internal:CERTIFICATE_VERIFY_FAILED`, check your machine certificates, and particulary that you have Let's Encrypt root certificate (ISRG Root X1).
Most of the gRPC bindings come with bundled root certificates which do not always reflect actual world since they can be outdated.

One known workaround is to point to your own root certificate, filling `gRPC_DEFAULT_SSL_ROOTS_FILE_PATH`.

For example:

```bash
gRPC_DEFAULT_SSL_ROOTS_FILE_PATH=/etc/ssl/certs/ca-certificates.crt pipenv run python main.py
```

## Check for more recent versions

```bash
pipenv update --outdated
```
