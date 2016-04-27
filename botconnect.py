import btcelib
from pprint import pprint
papi = btcelib.PublicAPIv3('btc_usd-ltc_xxx')
data = papi.call('ticker', ignore_invalid=1)
pprint(data)
# The next instance used the same connection...
apikey = {    # Replace with your API-Key/Secret!
    'Key': 'YOUR-KEY',
'Secret': 'YOUR-SECRET'
}
tapi = btcelib.TradeAPIv1(apikey, compr=True)
data = tapi.call('TradeHistory', pair='btc_usd', count=2)
pprint(data)