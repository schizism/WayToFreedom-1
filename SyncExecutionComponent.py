from __future__ import print_function

import os
import json
import urllib2
import boto3

from datetime import datetime, timedelta
from bittrexQuery import Bittrex
from holdingStatusTable import HoldingStatusTable

KEY=os.environ['key']
SECRET=os.environ['secret']
HOLDINTSTATUSTABLENAME = os.environ['holdingStatusTableName']
TRADINGSNS = os.environ['tradingSNS']
MAX_TRADING_PAIRS = int(os.environ['max_trading_pairs'])
BUY_PRICE_FACTOR = float(os.environ['buy_price_factor'])
SELL_PRICE_FACTOR = float(os.environ['sell_price_factor'])
MAX_BALANCE_PER_TRADING_PAIR = float(os.environ['max_balance_per_trading_pair'])
MIN_BALANCE_PER_TRADING_PAIR = float(os.environ['min_balance_per_trading_pair'])
SIGNAL_TICK_PRICE_TOLERANCE = float(os.environ['signal_tick_price_tolerance'])

holdingStatusTable = HoldingStatusTable(HOLDINTSTATUSTABLENAME)
bittrex = Bittrex(KEY, SECRET)

tradingMessage = ''


# dynamodb = boto3.resource('dynamodb')
# holdingStatusTable = dynamodb.Table('MarketHoldingStatus')
# transactionHistory = dynamodb.Table('TransactionHistory')

# tradingMessage = ''

def validateBittrex(rawMarketData):
	checkResult = rawMarketData['success']
	if not ('True' == str(checkResult)):
		raise Exception('Error: Validation failed! Failed to connect to Bittrex!')
	else:
		print('Validation passed! Connected to Bittrex')

def getCandidates(event):
	message = event['Records'][0]['Sns']['Message']
	return (json.loads(message)['buyingCandidates'], json.loads(message)['sellingCandidates'])

def sellExecution(sellingCandidates):
	for candidate in sellingCandidates:
		sell(candidate)
	return

def sell(candidate):
	pair = candidate['pair']
	currency = pair.split('-')[1]
	print('Start to sell: ' + currency)
	
	# Get quantity
	values = {'currency': currency}
	contents = bittrex.query('getbalance', values)
	print('The quantity info of ' + currency + ' is:')
	print(json.dumps(contents))
	quantity = contents['result']['Available']
	
	if (quantity is not None and quantity != 0):
		# Get rate
		values = {'market': pair}
		contents = bittrex.query('getticker', values)
		print('Tickker info for ' + currency + ' is: ')
		print(json.dumps(contents))
		rate = SELL_PRICE_FACTOR * contents['result']['Last']
	
		# Decide if the stock comes back first, if it comes back then stop selling
		comPrice = candidate['comPrice']
		tickLastPrice = contents['result']['Last']
		if (tickLastPrice > comPrice):
			snsLog('Warning: Quit selling ' + currency + ' because tick price (' + str(tickLastPrice) + ') comes back over compare price (' + str(comPrice) + ')')
			return
		
		# Sell currency
		orderUUID = None
		values = {'market': pair, 'quantity': quantity, 'rate': rate}
		contents = bittrex.query('selllimit', values)
		print('Sell currency info: ')
		print(json.dumps(contents))
		if (contents['success'] is False):
			snsLog('Warning: Fail to sell ' + currency)
			return
		else:
			orderUUID = contents['result']['uuid']
		
		# Give market some time, up to 10 seconds to do the trading
		orderFulfilled = waitTradingGracePeriod(pair)
		
		if (orderFulfilled is True):
			# Get order
			values = {'uuid': orderUUID}
			contents = bittrex.query('getorder', values)
			print('Order information is: ')
			print(json.dumps(contents))
			realRate = contents['result']['PricePerUnit']
			
			# Update holding status
			holdingStatusTable.setHoldingStatus(pair, 'False', 0, 0)
			
			# Update transaction record
			# updateTransactionHistory(pair, quantity, realRate, contents['result'], False)

			tradingRecord = 'Selling transaction finished: ' + pair + ', quantity: ' + str(quantity) + ', rate: ' + str(realRate)
			snsLog(tradingRecord)            
		else:
			# If the order has been fulfilled, cancel will make nothing
			# Otherwise cancel this out-of-date order
			cancelOutOfDateOrder(orderUUID)
			snsLog('Warning: order canceled because order is not fulfilled for selling ' + pair)
	else:
		snsLog('Warning: No quantity available for ' + currency)
	
	return

# def buyExecution(buyingCandidates):
# 	availableTradingPairs = getAvailableTradingPairs()
# 	print('Available trading pair number is: ' + str(availableTradingPairs))
	
# 	for candidate in buyingCandidates:
# 		if (availableTradingPairs <= 0):
# 			snsLog('Warning: No more trading pairs allowed!')
# 			break
# 		if (buy(candidate) is True):
# 			availableTradingPairs = availableTradingPairs - 1
		
# 	return

# def buy(candidate):
# 	pair = candidate['pair']
# 	currency = pair.split('-')[1]
# 	print('Start to buy: ' + currency)
	
# 	currentHoldingStatus = getHoldingStatus(pair)
# 	if (currentHoldingStatus is not None):
# 		snsLog('Warning: Currency has already been purchased: ' + pair)
# 		return False
	
# 	# Get buy price
# 	buyPrice = getBuyPrice(candidate)
# 	if (buyPrice == 0.0):
# 		snsLog('Warning: Quit buy execution for ' + pair)
# 		return False
# 	print('Buy price for ' + pair + ' is ' + str(buyPrice))
	
# 	# Get available balance
# 	availableBalance = getAvailableBalance()
# 	if (availableBalance == 0.0):
# 		snsLog('Warning: Quit buy execution for ' + pair)
# 		return False
		
# 	# Get trading quantity
# 	buyQuantity = availableBalance / buyPrice
# 	print('Buy quantity for ' + pair + ' is ' + str(buyQuantity))

# 	# Buy currency
# 	orderUUID = None
# 	values = {'market': pair, 'quantity': buyQuantity, 'rate': buyPrice}
# 	contents = query('buylimit', values)
# 	print('Buy currency info: ')
# 	print(json.dumps(contents))
# 	if (contents['success'] is False):
# 		snsLog('Warning: Fail to buy ' + currency)
# 		return False
# 	else:
# 		orderUUID = contents['result']['uuid']

# 	# Give market some time, up to 10 seconds to do the trading
# 	orderFulfilled = waitTradingGracePeriod(pair)
	
# 	if (orderFulfilled is True):
# 		# Get order
# 		values = {'uuid': orderUUID}
# 		contents = query('getorder', values)
# 		print('Order information is: ')
# 		print(json.dumps(contents))
# 		realRate = contents['result']['PricePerUnit']

# 		# Update holding status
# 		setHoldingStatus(pair, 'True', realRate, realRate)
		
# 		# Update transaction record
# 		updateTransactionHistory(pair, buyQuantity, realRate, contents['result'], True)
		
# 		tradingRecord = 'Buying transaction finished: ' + pair + ', quantity: ' + str(buyQuantity) + ', rate: ' + str(realRate)
# 		snsLog(tradingRecord)
# 		return True
		
# 	else:
# 		# If the order has been fulfilled, cancel will make nothing
# 		# Otherwise cancel this out-of-date order
# 		cancelOutOfDateOrder(orderUUID)
# 		snsLog('Warning: order canceled because order is not fulfilled for buying ' + pair)
# 		return True

# def getBuyPrice(candidate):
# 	pair = candidate['pair']
# 	signalBuyPrice = candidate['buyPrice']
	
# 	# Get tick price
# 	values = {'market': pair}
# 	contents = query('getticker', values)
# 	print('Tickker infor is: ')
# 	print(json.dumps(contents))
# 	tickLastPrice = contents['result']['Last']
	
# 	# difRatio = math.fabs((tickLastPrice - signalBuyPrice) / tickLastPrice)
# 	difRatio = (tickLastPrice - signalBuyPrice) / tickLastPrice
# 	if (tickLastPrice < signalBuyPrice) or (difRatio > SIGNAL_TICK_PRICE_TOLERANCE):
# 		# print('Warning: Will quit execution as difRatio(' + str(difRatio) + ') is greater than ' + str(SIGNAL_TICK_PRICE_TOLERANCE))
# 		snsLog('Warning: Will quit execution as signal price(' + str(signalBuyPrice) + ') is too different with tick price(' + str(tickLastPrice) +')')
		
# 		return 0.0
# 	else:
# 		return tickLastPrice * BUY_PRICE_FACTOR

# def getAvailableBalance():
# 	# Get account info for BTC
# 	values = {'currency': 'BTC'}
# 	contents = query('getbalance', values)
# 	print('Account information is: ')
# 	print(json.dumps(contents))
# 	BTCBalance = contents['result']['Available']
# 	print('Total BTC balance is ' + str(BTCBalance))

# 	# Quantify Buy Quantity
# 	if (BTCBalance >= MAX_BALANCE_PER_TRADING_PAIR):
# 		print('Available balance is ' + str(MAX_BALANCE_PER_TRADING_PAIR))
# 		return MAX_BALANCE_PER_TRADING_PAIR
# 	elif (BTCBalance >= MIN_BALANCE_PER_TRADING_PAIR):
# 		print('Available balance is ' + str(BTCBalance))
# 		return BTCBalance
# 	else:
# 		snsLog('Warning: Available blance is a dust training, will quit trading')
# 		return 0.0

# def getAvailableTradingPairs():
# 	response = holdingStatusTable.scan(
# 		FilterExpression=Key('HoldingStatus').eq('True')
# 	)
# 	holdingPairs = len(response['Items'])
	
# 	if (holdingPairs < MAX_TRADING_PAIRS):
# 		return MAX_TRADING_PAIRS - holdingPairs
# 	# In very special test case, there could be more than MAX_TRADING_PAIRS pairs in the table
# 	else:
# 		return 0

# Return True if order is fulfilled, return False if not
def waitTradingGracePeriod(pair):
	# Give market some time, up to 10 seconds to do the trading
	for i in range(1 , 5):
		time.sleep(2)
		# Get open orders
		values = {'market': pair}
		contents = bittrex.query('getopenorders', values)
		if (len(contents['result']) == 0):
			print('No open orders')
			return True
		print('Open orders status in ' + str(i) + ' is: ')
		print(json.dumps(contents))
	return False

def cancelOutOfDateOrder(orderUUID):
	if (orderUUID is not None):
		values = {'uuid': orderUUID}
		contents = bittrex.query('cancel', values)
		print('Cancel order info: ')
		print(json.dumps(contents))
	return

# def triggerTradingSNS():
# 	sns = boto3.client(service_name="sns")
# 	topicArn = TRADINGSNS
# 	print('Trading is executed!')
# 	global tradingMessage
# 	print(tradingMessage)
# 	sns.publish(
# 		TopicArn = topicArn,
# 		Message = 'Trading is executed!\n' + tradingMessage
# 	)
# 	return

def snsLog(message):
	print(str(message))
	global tradingMessage
	tradingMessage += str(message)
	tradingMessage += '\n'
	return

def lambda_handler(event, context):
	try:
		# Validate Bittrex connection
		rawMarketSummaryData = bittrex.query('getmarketsummaries')
		validateBittrex(rawMarketSummaryData)
		
		global tradingMessage
		tradingMessage = ''
		
		# Get candidates from event
		buyingCandidates, sellingCandidates = getCandidates(event)
		print('BuyingCandidates: ')
		print(json.dumps(buyingCandidates))
		print('SellingCandidates: ')
		print(json.dumps(sellingCandidates))
		
		# Start to sell
		sellExecution(sellingCandidates)
		
	except Exception, e:
		print('Error: ' + str(e))
		raise
	else:
		print('Execution successfully')
		return str(datetime.now())
	finally:
		print('Execution complete at {}'.format(str(datetime.now())))

# def lambda_handler(event, context):
#     try:
#         rawMarketData = json.loads(urlopen(SITE).read())
#         if not validateBittrex(rawMarketData):
#             raise Exception('Validation failed')
			
#         global tradingMessage
#         tradingMessage = ''
		
#         buyingCandidates, sellingCandidates = getCandidates(event)
#         print("BuyingCandidates: ")
#         print(json.dumps(buyingCandidates))
#         print("SellingCandidates: ")
#         print(json.dumps(sellingCandidates))
		
#         # Start to sell
#         sellExecution(sellingCandidates)
		
#         # Start to buy
#         buyExecution(buyingCandidates)

#         triggerTradingSNS()
#     except:
#         print('Check failed!')
#         raise
#     else:
#         print('Check passed!')
#         return str(datetime.now())
#     finally:
#         print('Check complete at {}'.format(str(datetime.now())))