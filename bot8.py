# Copyright (c) 2013 Alan McIntyre

import decimal
import time
import collections

import btceapi
import btcebot
#import cancel_orders
from datetime import datetime, timedelta

import os

def iPrint(*args):
	if printingEnabled:
		for a in args:
			print a,
		print ""

class RangeTrader(btcebot.TraderBase):
	'''
	This is a simple trader that handles a single currency pair, selling
	all available inventory if price is above sell_price, buying with
	all available funds if price is below buy_price.  Use for actual trading
	at your own risk (and remember this is just a sample, not a recommendation
	on how to make money trading using this framework).
	'''
	def init_alfas(self, alfa, lastMinutes):
		alfa=decimal.Decimal(alfa)
		self.alfas={}
		self.alfas[(alfa, 0)]=decimal.Decimal(1)
		for i in range(1, lastMinutes*60+15):
			self.alfas[(alfa, i)]=truncate(self.alfas[(alfa, i-1)]*alfa, 12)


	
	
	def init_variables(self, api, pair, buy_margin, sell_margin, live_trades = False, logging=False, loggingTime=False, printing=False,
				gamma=0.65, eraSec=5, alfa=0.992, beta=1, buyChunk=0, sellChunk=0, lastMinutes=60, epsilonSize=2, singleM=False):
		global alfa2, loggingEnabled, printingEnabled, loggingTimeEnabled, toBeAddedToLocalTime, singleMode, avgVector
		self.fatalError= False
		avgVector=[]
		alfa2= 985
		self.cancel_response=""
		self.startLoopTime=datetime.now()
		toBeAddedToLocalTime = api.getInfo().server_time - datetime.now()
		self.lastTradeTime = self.startLoopTime + toBeAddedToLocalTime
		loggingEnabled=logging
		loggingTimeEnabled=loggingTime
		printingEnabled=printing
		singleMode = singleM
		self.epsilonSize=int(epsilonSize)
		self.api = api
		self.pair = pair
		self.alfa=decimal.Decimal(alfa)
		self.beta=beta
		self.buy_margin = decimal.Decimal(buy_margin)
		self.sell_margin = decimal.Decimal(sell_margin)
		self.live_trades = live_trades
		self.gamma = decimal.Decimal(gamma)
		self.eraSec = decimal.Decimal(eraSec)
		self.current_price, self.current_amount, self.current_order_id= {}, {}, {}
		self.current_price["buy"], self.current_price["sell"] =decimal.Decimal(0), decimal.Decimal(0)
		self.current_amount["buy"], self.current_amount["sell"] =decimal.Decimal(0), decimal.Decimal(0)
		self.current_order_id["buy"], self.current_order_id["sell"] =0, 0
		self.history=[]
		self.depthIndicator = 0
		self.depthIndicatorCount =0
		self.lastMinutes=int(lastMinutes)
		self.spaceCounter=0
		now= self._now()
		self.BuySectionHours, self.BuySectionMinutes = ((now.hour-1)%24, now.minute)
		self.SellSectionHours, self.SellSectionMinutes = ((now.hour-1)%24, now.minute)
		self.counter=0
		self.min_orders = btceapi.min_orders[self.pair]
		self.min_amount_to_trade={}
		self.min_amount_to_trade["ltc_usd"]=decimal.Decimal(9)
		self.min_amount_to_trade["ltc_btc"]=decimal.Decimal(2)
		self.min_amount_to_trade["btc_usd"]=decimal.Decimal(0.1)
		self.min_amount_to_trade["nmc_usd"]=decimal.Decimal(4)
		self.min_amount_to_trade["usd_rur"]=decimal.Decimal(4)
		self.min_amount_to_trade["btc_rur"]=decimal.Decimal(0.1)
		self.min_amount_to_trade["btc_eur"]=decimal.Decimal(0.1)
		self.min_amount_to_trade["eur_rur"]=decimal.Decimal(1)
		
	def init_chunks(self, pair, api, buyChunk=0,sellChunk=0,buyBudget=0, sellBudget=0):
		self.chunk, self.budget= {}, {}
		for type, inChunk, inBudget in [["buy", buyChunk, buyBudget], ["sell", sellChunk, sellBudget]]:
			iPrint ("type, buy/sell Chunk, buy/sell Budget: ", type, inChunk, inBudget)
			if inChunk is None:
				self.chunk[type]=0
			elif inChunk<0:
				if (pair=="eur_usd"):
					self.chunk[type] = decimal.Decimal(0.98)
				elif (pair=="btc_eur"):
					self.chunk[type] = decimal.Decimal(0.0102)
				elif (pair=="btc_usd"):
					self.chunk[type] = decimal.Decimal(0.0102)
				else:
					self.chunk[type] = decimal.Decimal(0.102)
			else: 
				self.chunk[type]=inChunk
			
			if inBudget is None:
				self.budget[type] = self.chunk[type]
			else:
				self.budget[type] = inBudget
			
		iPrint("chunks: ", self.chunk["buy"], self.chunk["sell"])
		iPrint("budget: ", self.budget["buy"], self.budget["sell"])

	def init_sections(self):
		#global bidSections, askSections
		bidSections=[]
		askSections=[]
		bidSum=0
		askSum=0
		with open("tradesASecondLtcUsdBids(z40h).txt",'rb') as f:
			while True:
				line=f.readline()
				if not line:
					break
				aSection=line.split(" ")
				aSection[0]=decimal.Decimal(aSection[0])
				aSection[1]=decimal.Decimal(aSection[1])
				aSection[2]=decimal.Decimal(aSection[2])
				bidSections+=[aSection]
				bidSum+=aSection[2]
			for bid in bidSections:
				bid[2]=truncate(bid[2]/bidSum, 6)
		with open("tradesASecondLtcUsdAsks(z40h).txt",'rb') as f:
			while True:
				line=f.readline()
				if not line:
					break
				aSection=line.split(" ")
				aSection[0]=decimal.Decimal(aSection[0])
				aSection[1]=decimal.Decimal(aSection[1])
				aSection[2]=decimal.Decimal(aSection[2])
				askSections+=[aSection]
				askSum+=aSection[2]
			for ask in askSections:
				ask[2]=truncate(ask[2]/askSum, 6)
				
	def init_10min_sections(self):
		global overTimeBidSections, overTimeBidSectionsSums, overTimeAskSections, overTimeAskSectionsSums, sectionLength
		overTimeBidSections, overTimeBidSectionsSums, overTimeAskSections, overTimeAskSectionsSums =[], [], [], []
		
		#10 144   = od 0:00 do 0:10 , a 144 nic waznego nie znaczy =24*6
			#1.0 1.5 561  -  ile bylo zamowien od 1.0 do 1.5
			#1.5 2.2 65
			#2.2 3.3 29
			#3.3 5.0 61
		with open("tradesAMinute_"+str(self.pair)+"Bids.txt",'rb') as f:
			line=f.readline()
			aSection=line.split(" ")
			x1=int(aSection[0])
			x2=int(aSection[1])
			sectionLength=(x2-x1)
			bidSum, bidSections =0,[]
			
			while True:
				line=f.readline()
				if not line:
					overTimeBidSections+=[bidSections]
					overTimeBidSectionsSums+=[bidSum]
					break
				
				aSection=line.split(" ")
				if (len(aSection)==2):
					overTimeBidSections+=[bidSections]
					overTimeBidSectionsSums+=[bidSum]
					bidSum=0
					bidSections=[]
				if (len(aSection)==3):
					aSection[0]=decimal.Decimal(aSection[0])
					aSection[1]=decimal.Decimal(aSection[1])
					aSection[2]=decimal.Decimal(aSection[2])
					bidSections+=[aSection]
					bidSum+=aSection[2]
				
		with open("tradesAMinute_"+str(self.pair)+"Asks.txt",'rb') as f:
			line=f.readline()
			aSection=line.split(" ")
			x1=int(aSection[0])
			x2=int(aSection[1])
			sectionLength=(x2-x1)
			askSum, askSections =0,[]
			
			while True:
				line=f.readline()
				if not line:
					overTimeAskSections+=[askSections]
					overTimeAskSectionsSums+=[askSum]
					break
				
				aSection=line.split(" ")
				if (len(aSection)==2):
					overTimeAskSections+=[askSections]
					overTimeAskSectionsSums+=[askSum]
					askSum=0
					askSections=[]
				if (len(aSection)==3):
					aSection[0]=decimal.Decimal(aSection[0])
					aSection[1]=decimal.Decimal(aSection[1])
					aSection[2]=decimal.Decimal(aSection[2])
					askSections+=[aSection]
					askSum+=aSection[2]
				
	def init_changeDict(self):
		d= {}
		d[0] = 0
		d[20] = decimal.Decimal("0.000544")
		d[40] = decimal.Decimal("0.00086")
		d[60] = decimal.Decimal("0.001131")
		d[80] = decimal.Decimal("0.002696")
		d[100] = decimal.Decimal("0.003076")
		d[120] = decimal.Decimal("0.003314")
		d[140] = decimal.Decimal("0.003950")
		d[9999999] = 0
		self.changeDict=d
		
		
				
	def __init__(self, api, pair, buy_margin, sell_margin, live_trades = False, logging=False, loggingTime = False, printing = False,
				gamma=0.65, eraSec=5, alfa=0.992, beta=1, buyChunk=0, sellChunk=0, buyBudget=0, sellBudget=0, lastMinutes=60, epsilonSize=2, singleMode=False):
		btcebot.TraderBase.__init__(self, (pair,))
		self.init_variables(api, pair, buy_margin, sell_margin, live_trades, logging, loggingTime, printing,
				gamma, eraSec, alfa, beta, buyChunk, sellChunk, lastMinutes, epsilonSize, singleMode)
		#self.init_sections()
		self.init_changeDict()
		self.init_10min_sections()
		
		if singleMode:
			self.init_chunks(pair, api, buyChunk, sellChunk, 999999, 999999)
		else:
			self.init_chunks(pair, api, buyChunk, sellChunk, buyBudget, sellBudget)
		
		self.init_chunks(pair, api, buyChunk, sellChunk, buyBudget, sellBudget)
		if alfa>0:
			self.init_alfas( alfa, lastMinutes)
		
		self.spaceCounter=0
		self.avg_price_calc_time = self._now() - timedelta(hours = 100)
		self.avg_price, self.buy_floor, self.sell_ceiling = 0,0,0
		#input("Press Enter to continue...")
		
		self.current_lowest_ask = None
		self.current_highest_bid = None
		
		# Apparently the API adds the fees to the amount you submit,
		# so dial back the order just enough to make up for the 
		# 0.2% trade fee.
		self.fee_adjustment = decimal.Decimal("0.998")
		
	def _now(self):
		logTime(self, "_nowStart")
		t=datetime.now()+toBeAddedToLocalTime
		logTime(self, "_nowDone")
		return t
	
	def initiazeCentralSection(self, someSections): 
		centralSections=someSections
		for i in range(len(centralSections)):
			aCentralSection=centralSections[i]
			for j in range(len(centralSections[i])):
				if (j==2):
					centralSections[i][j]=0
		return centralSections
		
	def findMySections(self, weights, type="buy"):
		now= self._now()
		hours, minutes = (now.hour, now.minute)
		sectionsNr = hours*6+minutes/10
		
		centralSum=decimal.Decimal(0)
		if (type=="buy"):
			sectionsSums = overTimeBidSectionsSums
			overTimeSections = overTimeBidSections
		else:
			sectionsSums = overTimeAskSectionsSums
			overTimeSections = overTimeAskSections
		
		centralSections=self.initiazeCentralSection(overTimeSections[0]) #Wyzerowanie, pamietaj w weights jest tez srodkowa!
		
		################### LICZENIE SREDNIEJ WAZONEJ WG WAG WEIGHTS #######################
		for (offset, weight) in weights:
			sectionNrModifiedByOffset = (sectionsNr+offset) % (24*6)
			offset, weight = (int(offset), decimal.Decimal(weight))
			centralSum+=sectionsSums[sectionNrModifiedByOffset]*weight
			for i in range(len(centralSections)):
				centralSections[i][2]+=overTimeSections[sectionNrModifiedByOffset][i][2]*weight
		
		##################### NORMALIZACJA ################################################
		for i in range(len(centralSections)):
			centralSections[i][2]=truncate(centralSections[i][2]/centralSum, 6)
		#PRZETESTOWAC!!!!!!!!!!
		return centralSections

	def getSections(self, weights, type):
		now= self._now()
		hours, minutes = (now.hour, now.minute)
		if type=="buy":
			sectionHours , sectionMinutes = (self.BuySectionHours,self.BuySectionMinutes)
		else:
			sectionHours , sectionMinutes = (self.SellSectionHours,self.SellSectionMinutes)
			
		if self.newSectionsNeeded(sectionHours , sectionMinutes, hours, minutes):
			if type=="buy": 
				self.BuySectionHours, self.BuySectionMinutes = (hours, minutes)
			else:
				self.SellSectionHours, self.SellSectionMinutes = (hours, minutes)
			
			logTime(self, "findMySectionsStart")
			Sections=self.findMySections(weights, type)
			logTime(self, "findMySectionsDone")
			if type=="buy":
				self.currentAskSections=Sections
			else:
				self.currentBidSections=Sections
			
			print "newTimeSections: ", type, hours, minutes
			#writeObjectToFile(askSections)
		else:
			Sections = self.currentAskSections if type=="buy" else self.currentBidSections
		maxShot=0
		for aSection in Sections:
			if aSection[2]>0:
				maxShot = aSection[1]
				
		#writeToFile("#my"+str(type)+"Sections:"+"\n")
		#writeObjectToFile(Sections)
		return Sections, maxShot

	def epsilon(self):
		return self.addEpsilon(0, 1)
		
	def addEpsilon(self, bid_price, sign):
		y=btceapi.max_digits[self.pair]
		sign = decimal.Decimal(sign)
		if y>1:
			tmp = decimal.Decimal(decimal.Decimal("0."+"0"*(y-1)+"1")*sign)
			x=decimal.Decimal(truncate(tmp,y))
		else: 
			x=decimal.Decimal((0.0001)*sign)
		q=truncate(bid_price+x, y)
		return q
	
	def getSleepMaybe(self, type, new_trade_price,  napSeconds=25, napCount=5, napCountTurboMode = 25):
		if not(new_trade_price):
			print "spie bo nie mam zadnej ceny do zaproponowania"
			time.sleep(10)
			self.counter=-1
			return
		available = self.getAvailable(type)
		future_trade_amount =  min (self.budget[type], available / new_trade_price if type=="buy" else available )
		tmpCounter=0
		sleepsCount = napCountTurboMode if (not(loggingEnabled) and not(printingEnabled)) else napCount
		while (future_trade_amount < self.min_amount_to_trade[self.pair]) and (tmpCounter < sleepsCount):
			if printingEnabled:
				iPrint("  ide spac za malo do handlowania ",future_trade_amount, self.min_amount_to_trade[self.pair])  
			else: 
				print tmpCounter,
			time.sleep(napSeconds)
			tmpCounter+=1
			available = self.getAvailable(type)
			future_trade_amount = min (self.budget[type], available / new_trade_price if type=="buy" else available )
		if tmpCounter ==sleepsCount:
			self.counter=-1
	
	def getAvailable(self, type):
		logTime(self, "api.getAvailable start")
		info = self.api.getInfo()
		curr1, curr2 = self.pair.split("_")
		if type=="sell":
			available = getattr(info, "balance_" + curr1)
		else:
			available = getattr(info, "balance_" + curr2)
		logTime(self, "api.getAvailable done")
		return available
	
	def clearTradeData(self, type, clearOrders=False):
		self.current_order_id[type], self.current_price[type] , self.current_amount[type]= (0,0,0)
		if clearOrders:
			cancel_all_active_orders_of_pair(self.api, self.pair, type=="buy", type=="sell") 
		
	def setCurrentTradeData(self, type, order_id, new_trade_price, trade_amount):
		self.current_order_id[type], self.current_price[type] , self.current_amount[type]= (order_id, new_trade_price, trade_amount)

	def trade(self, new_trade_price, type):
		logTime(self, "countTRADE "+type+" start")
		iPrint("entering trade w price: ", new_trade_price, type)
		currentID = self.current_order_id[type]
		if self.counter%20:
			if currentID>0:
				if new_trade_price == self.current_price[type]:
					iPrint("Ta sama cena, nic nie zmieniam")
					self.counter+=1
					return None
				logTime(self, "api.cancelOrder start")
				self.cancel_response = self.api.cancelOrder(currentID)
				logTime(self, "api.cancelOrder done")
				if not(self.cancel_response.info["success"]):
					self.clearTradeData(type, True)
					available = self.getAvailable(type)
				else:
					if type=="buy":
						available = self.cancel_response.info["funds"][self.pair.split("_")[1]]
					else:
						available = self.cancel_response.info["funds"][self.pair.split("_")[0]]
			else:
				available = self.getAvailable(type)
				iPrint("entering trade else available : ", available)
		else:
			iPrint(" uzyto counter ", self.counter)
			self.clearTradeData(type, True)
			self.getSleepMaybe(type, new_trade_price)
			available = self.getAvailable(type)
				
		iPrint(self.counter)
		self.counter+=1
		self.clearTradeData(type)     # byc moze niepotrzebne..
		
		if not(new_trade_price):
			return
		tmp = available / new_trade_price if type=="buy" else available
		trade_amount = truncate ( min (tmp, self.chunk[type], self.budget[type] ) * 9975/10000, btceapi.max_digits[self.pair])
			
		if trade_amount >= self.min_orders and self.live_trades and new_trade_price:
				logTime(self, "api.newTrade start")
				r = self.api.trade(self.pair, type, new_trade_price, trade_amount)
				logTime(self, "api.newTrade done")
				if r.order_id != 0:
					self.setCurrentTradeData(type, r.order_id, new_trade_price, trade_amount)
					iPrint( "added order: ", r.order_id, type, new_trade_price, trade_amount)
		logTime(self, "countTRADE "+type+" done")
		
	def countEV(self, type, aTrade, oppSections, aTradeInputSum, avg, gammaInput=1.1):
		# trade = [price, amount]  jeden trade tylko
		#               0      1         2
		# aSection = [ left, right, probability] left<right
		# depthSum = [price, sumAmount]
		backupAvg = avg
		newEpsilon  =   self.epsilonSize if type=="buy" else -self.epsilonSize
		newPrice	= 	decimal.Decimal(self.addEpsilon(aTrade[0], newEpsilon))
		trade		=	[newPrice, aTrade[1]]
		omega		=	decimal.Decimal("0.997") if type == "buy" else decimal.Decimal("1.003009")
		avg			=	decimal.Decimal(avg*omega)
		ev			=	decimal.Decimal(0)
		aTradeSum 	= 	decimal.Decimal(aTradeInputSum)*decimal.Decimal(gammaInput)
		
		if self.current_amount[type] >0:
			max_trade = min(self.current_amount[type], self.chunk[type], self.budget[type])
		else:
			max_trade = min (self.chunk[type], self.budget[type])
		
		
		#decimal.Decimal(gammaInput)
		#iPrint( "dla: " , bid[0], avg, ev)
		#writeToFile("dla: "+ str(trade[0])+" aTradeSum: " + str(aTradeSum)+"\n")
		#writeToFile("avg: "+str(backupAvg)+" omegaAvg: "+ str(avg)+"ev: "+ str(ev)+"\n")
		for aSection in oppSections:
			if (aSection[2]>0):
				left  = aSection[0]
				right = aSection[1]
				prob  = aSection[2]
				width = (right - left)
				center= width /decimal.Decimal(2)
				profit = (avg-trade[0]) if type=="buy" else -(avg-trade[0])
				if left >= aTradeSum:
					ev+= profit*prob*min(max_trade, center)
				elif (right > aTradeSum) and (left < aTradeSum):
					ev+= profit*prob* min(max_trade, center)* (right - aTradeSum)/width 
		ev=truncate(ev, 12)
		return decimal.Decimal(ev)
	
	def newSectionsNeeded(self, SectionHours, SectionMinutes, hours, minutes):
		oldSectionsNr = SectionHours*6+SectionMinutes/10
		SectionsNr = hours*6+minutes/10
		return SectionsNr!=oldSectionsNr
		
	def init_weights(self):
		weights=[]
		if self.pair == ("btc_rur") or (self.pair == "btc_eur"):
			for i in range(-25, 26):
				weights+=[[i,1]]
			return weights
		weights = [ [-3,1], [-2,1], [-1,1], [0,1], [1,1], [2,1], [3,1]]
		return weights
	
	def prepareDepth(self, depthIn, maxDepth, type="buy"):
		fi = decimal.Decimal("0.004")
		current_price = self.current_price[type]
		current_amount= self.current_amount[type]
		sumTemp=[]
		depth = map(lambda x: x if x[0]!=current_price else 
								x if x[0]==current_price and x[1]<current_amount else
								[x[0], x[1]- current_amount], depthIn)
		depth = filter(lambda x: x[1]>0, depth)
		depthCopy=depth
		depth=[]
		for i in range(len(depthCopy)):
			sumTemp+= [reduce(lambda a,b: [b[0], a[1]+b[1]], depthCopy[:(i+1)])]
		for i in range(len(depthCopy)):
			if (i==0):
				depth+=[[depthCopy[0][0], depthCopy[0][1], decimal.Decimal(0)]]
			else:
				depth+=[[depthCopy[i][0], depthCopy[i][1], sumTemp[i-1][1]]]
		if type=="buy":
			depth = filter(lambda x: x[0]<self.buy_floor*(1+fi) and x[2]<maxDepth, depth) 
		else:
			depth = filter(lambda x: x[0]>self.sell_ceiling*(1-fi) and x[2]<maxDepth, depth) 
		#writeToFile("#!" + type +"\n" + str(maxDepth))
		#print self.sell_ceiling*(1-fi), self.sell_ceiling
		#print depth
		return depth
		
	def oppType(self, type):
		return "sell" if type=="buy" else "buy"
	
	def findMaxProfit(self, depthIn):
		depth=depthIn
		max_index=-1
		max_profit = decimal.Decimal(0)
		for i in range(len(depth)):
			if depth[i][2]> max_profit:
				max_index=i
				max_profit=depth[i][2]
		return max_index, max_profit
	
	def onNewDepth(self, t, pair, asksInput, bidsInput):
		self.startLoopTime=datetime.now()
		self.spaceCounter=0
		logTime(self, "onNewDepth start")
		
		
		weights = self.init_weights()
		
		now = self._now()
		iPrint ("od ostatniej AVG PRICE: " , (now - self.avg_price_calc_time))
		iPrint (self.avg_price, self.buy_floor, self.sell_ceiling)
		if (now - self.avg_price_calc_time) > timedelta(seconds = 15):
			iPrint("Przestarzale avg!!")
		else:
			for type in ("buy", "sell"):
				chunk = self.chunk[type]
				if chunk and (self.budget[type] > 0):
					sections, maxDepth = self.getSections(weights, self.oppType(type))
					iPrint( "MaxDepth:", maxDepth)
					depth = self.prepareDepth(bidsInput if type=="buy" else asksInput, maxDepth, type) 
					logTime(self, "count " + type + " EVStart")
					
					print self.depthIndicator, self.depthIndicatorCount, "przed"
					depthIndictorValue = calcDepthIndictator(self.avg_price, asksInput, bidsInput)
					self.depthIndicator, self.depthIndicatorCount = predictChange(self.changeDict, self.depthIndicator, self.depthIndicatorCount, depthIndictorValue)
					print self.depthIndicator, self.depthIndicatorCount, "po"
					avg_price_depthIndicator = truncate(self.avg_price * (1+self.depthIndicator),8)
					if abs(avg_price_depthIndicator - self.avg_price)/self.avg_price > decimal.Decimal("0.004"):
						avg_price_depthIndicator = self.avg_price
						print "!#"*30
					
					#zastanowic sie czy jest nasz bid i czy go dopisywac
					print self.avg_price, "*", (1+self.depthIndicator), "=", avg_price_depthIndicator
					
					for i in range(len(depth)):
						depth[i]= [depth[i][0], depth[i][1], self.countEV(type, depth[i], sections, depth[i][2], avg_price_depthIndicator, self.gamma), depth[i][2]]
					logTime(self, "count "+type + " EVDone")
					#writeToFile("##Bids4D: "+"\n" )
					writeObjectToFile(depth)
									
					max_index, max_profit = self.findMaxProfit(depth)
					
					if  (max_index>(-1)) and max_profit:
						trade_price = self.addEpsilon( depth[max_index][0], self.epsilonSize if type=="buy" else -self.epsilonSize)
						self.trade(trade_price , type)
					else:
						self.trade(None , type)
						iPrint( max_index, max_profit, type, " weszlismy bez trade_price bo: (index, profit) !!!")
						self.clearTradeData(type, True)
						self.current_amount[type] =  self.getAvailable(type)
				
				
		iPrint( self.current_price["buy"], self.current_price["sell"])
		if self.eraSec:
				iPrint("SPIEEEEEEEEEEEE")
				time.sleep(self.eraSec)
		logTime(self, "AVG calc Start")
		if (self._now() - self.avg_price_calc_time) > timedelta(seconds = 4):
			self.buy_floor, self.avg_price, self.sell_ceiling = calcAvgPrice(self, pair, self.buy_margin, self.sell_margin, self.alfa, self.beta, self.lastMinutes)
		logTime(self, "AVG calc Done")
		logTime(self, "onNewDepthDone")


def calcChange(dict, x):
	print dict
	print x
	
	iMin = max(filter(lambda y:y<=x, dict.keys()))
	iMax = min(filter(lambda y:y>x, dict.keys()))
	print iMin, iMax, "iMin, iMax"
	return truncate(dict[iMin] + (dict[iMax]-dict[iMin])*(x-iMin)/(iMax-iMin), 8)

def predictChange(changeDict, avgValue, count, aValue):
	max_change = decimal.Decimal("0.004")
	absValue = abs(aValue)
	aChange = calcChange(changeDict, absValue)
	if aValue<0:
		aChange = -aChange
	print aValue, "-->", aChange
	aChange = min(max_change, aChange) if aChange>0 else max(-max_change, aChange)
	
	return truncate((avgValue*count + aChange)/(count+1),8), count+1

def logTime(self, msg):
	if loggingTimeEnabled:
		if "START" in msg.upper():
			self.spaceCounter+=1
		timeElapsed = "   "*self.spaceCounter + str(datetime.now()-self.startLoopTime)
		open("bot5time.log", "a").write("%s   %s\n"  % (timeElapsed, msg))
		if "DONE" in msg.upper():
			self.spaceCounter-=1
		self.spaceCounter= max(self.spaceCounter, 0)

def writeToFile(msg):
	if loggingEnabled:
		open("bot5.log", "a").write("%s"  % (msg))

def writeObjectToFile(object):
	
	if isinstance(object, collections.Iterable):
		tempBigString=""
		for i in range(len(object)):
			subObject=object[i]
			if isinstance (subObject, collections.Iterable):
				tempString=""
				for j in range(len(subObject)):
					tempString+=str(subObject[j])+" "
				tempBigString+=tempString+"\n"
	#writeToFile("###"+tempBigString)

def onBotError(msg, tracebackText):
    tstr = time.strftime("%Y/%m/%d %H:%M:%S")
    iPrint( "%s - %s" % (tstr, msg))
    open("bot7-error.log", "a").write(
        "%s - %s\n%s\n%s\n" % (tstr, msg, tracebackText, "-"*80))

def cancel_all_active_orders_of_pair(api, pair, typeBuy=True, typeSell=True):
	orders = api.activeOrders(pair = pair)
	iPrint( "Cancel Orders: tyle widze zamowien: ", len(orders))
	countBuy, countSell=0,0
	for ord in orders:
		if (ord.type=="buy" and typeBuy): 
			api.cancelOrder(ord.order_id)
			countBuy+=1
			iPrint( "cancelled order: ", ord.type, ord.pair, ord.amount, "@")
		elif (ord.type=="sell" and typeSell):
			api.cancelOrder(ord.order_id)
			countSell+=1
			iPrint( "cancelled order: ", ord.type, ord.pair, ord.amount, "@")
	iPrint( "cancelled#", countBuy, countSell)

def truncate(f, n):
    '''Truncates/pads a float f to n decimal places without rounding'''
    s = '{}'.format(f)
    if 'e' in s or 'E' in s:
        return decimal.Decimal('{0:.{1}f}'.format(f, n))
    i, p, d = s.partition('.')
    return decimal.Decimal('.'.join([i, (d+'0'*n)[:n]]))

def writeBudget(self):
	buySell = " Buyer & Seller " if self.chunk["buy"] * self.chunk["sell"] else " Buyer " if self.chunk["buy"] else " Seller "
	writeToFile(str(self.pair)+ buySell +"\n")
	writeToFile("Budget Buy, Sell: " +str(self.budget["buy"]) + ", " + str(self.budget["sell"])+"\n")

def print_trade_history(self, api, pair):
	print "jestem w trade History	"
	logTime(self, "api.tradeHistory start")
	freshTrades = api.tradeHistory(pair=pair, count_number = 10)
	logTime(self, "api.tradeHistory done")
	freshTrades = filter(lambda x: getattr(x, "timestamp")  > self.lastTradeTime, freshTrades) 
	iPrint ("budzety buy, sell: ", self.budget["buy"], self.budget["sell"])
	
	if freshTrades:
		writeToFile("last trade time: "+ str(self.lastTradeTime)+"\n")
		self.lastTradeTime = getattr(freshTrades[0], "timestamp")
		revFreshTrades = freshTrades
		revFreshTrades.reverse()
		for tr in revFreshTrades:
			items = ("pair", "type", "amount", "rate", "order_id",
                 "is_your_order", "timestamp")
			for item in items:
				writeToFile(getattr(tr, item))
				writeToFile(" ")
			writeToFile("\n")

			writeBudget(self)
			type = getattr(tr, "type")
			if type=="buy":
				self.budget["buy"] -=  getattr(tr, "amount")
				self.budget["sell"] += getattr(tr, "amount")
				time.sleep(1)
				
			elif type=="sell":
				self.budget["buy"] +=  getattr(tr, "amount")
				self.budget["sell"] -= getattr(tr, "amount")
				time.sleep(1)
						
			if self.chunk["buy"]:
				self.clearTradeData("buy", True)
			if self.chunk["sell"]:
				self.clearTradeData("sell", True)
			writeBudget(self)
			
			iprint ("**budzety buy, sell: ", self.budget["buy"], self.budget["sell"])
	
def interpolate(x, x_values, y_values):
	def _basis(j):
		p = [(x - x_values[m])/(x_values[j] - x_values[m]) for m in xrange(k) if m != j]
		return reduce(operator.mul, p)
	assert len(x_values) != 0 and (len(x_values) == len(y_values)), 'x and y cannot be empty and must have the same length'
	k = len(x_values)
	return sum(_basis(j)*y_values[j] for j in xrange(k))
	
	
def vortex(periodCount, period, history,  now, alf2):
	alfa2=alf2*decimal.Decimal("0.001")
	min, max = {}, {}
	for h in history:
		q=h.__getstate__()
		slotNr = int((now-q["date"]).total_seconds()/( period))
		#print slotNr, "slotNr"
		if (slotNr > periodCount-1):
			break
		if slotNr not in min :
			min[slotNr]=q["price"]
		else:
			if q["price"] < min[slotNr]:
				min[slotNr]=q["price"]
		if slotNr not in max :
			max[slotNr]=q["price"]
		else:
			if q["price"] > max[slotNr]:
				max[slotNr]=q["price"]
	size = len(min)
	if size <6:
		return None,None, size-1
	
	max_occupied_index=-1
	for i in range(periodCount-1, -1, -1):
		if i in min:
			max_occupied_index = i
			break
	print "max_occupied" , max_occupied_index
	
	for i in range(max_occupied_index, -1, -1):
		if i in min:
			min_saved, max_saved = min[i], max[i]
			#writeToFile(" min:",i,"=", truncate(min[i],6))
			#writeToFile(" max:",i,"=", truncate(max[i],6))
		else:
			min[i], max[i]= min_saved, max_saved
			#writeToFile(" min:",i,"=", truncate(min[i],6))
			#writeToFile(" max:",i,"=", truncate(max[i],6))
	
	TR=0
	VM_plus = 0
	VM_minus = 0
	for i in range(max_occupied_index-1, -1, -1):
		print i, min[i], max[i]
		TR+= max[i]-min[i]
		VM_plus += (max[i]-min[i+1])*(alfa2**i)
		VM_minus += (max[i+1]-min[i])*(alfa2**i)
	
	iPrint ("VORTEX:", TR, VM_plus, VM_minus, max_occupied_index)
	
	TR=truncate(TR,6)
	if TR !=0:
		VM_plus = truncate(VM_plus / TR, 6)
		VM_minus = truncate(VM_minus / TR,6)
		return VM_plus, VM_minus, size
	else:
		return None,None, size
	

def predictAvg(avg, future_factor, s):
	teta = 200
	sigma = decimal.Decimal("0.001")*s* teta * decimal.Decimal("0.001")
	new_avg = avg + avg*sigma * min(10, future_factor) if future_factor >=0 else avg + avg*sigma * max(-10, future_factor)
	return new_avg

def calcDepthIndictator(avg, asks, bids, zet = 15):
	pr_limit = decimal.Decimal("0.0"+str(zet))
	sum_a=sum_b=0
	licznik=0
	for a in asks:
		licznik+=1
		price, amount = a
		zeta = (pr_limit - ((price-avg)/avg))
		sum_a+= max(0,zeta) * amount
		if zeta<=0:
			break

	for b in bids:
		licznik+=1
		price, amount = b
		zeta= (pr_limit - ((avg-price)/avg))
		sum_b+= max(0,zeta) * amount
		if zeta<=0:
			break
	return truncate(sum_b - sum_a, 4)

def calcAvgPrice(self, pair, buy_margin, sell_margin, alfa=0.994, beta=1, lastMinutes=60, count =150 ):
	
	if not(singleMode):
		print_trade_history(self, self.api, pair)
	
	buy_margin, sell_margin = (int(buy_margin), int(sell_margin))
	avg_price, licznik, mianownik, volume=(0,0,0,0)
	ile=count
	dlugosc=0
	nowStart= self._now()
	freshHistory = btceapi.getTradeHistory(pair, None, count)
	freshHistory = filter(lambda x: nowStart - x.__getstate__()["date"]<timedelta(minutes=lastMinutes), freshHistory)
	if freshHistory:
		lastFreshRecord = freshHistory[-1].__getstate__()
		self.history = filter(lambda x: nowStart - x.__getstate__()["date"]<timedelta(minutes=lastMinutes), self.history)
		self.history = filter(lambda x: lastFreshRecord["date"] - x.__getstate__()["date"] > timedelta(minutes=0), self.history)
	self.history = freshHistory+self.history
	
	if self.history:
		q=self.history[-1].__getstate__()
		ost_date=q["date"]
	else:
		print "no history available"
		self.live_trades=False
	
	range = truncate((nowStart - ost_date).total_seconds()/60,0) 
	if (range < lastMinutes/8) or not(self.history) or self.fatalError:
		self.live_trades=False
		iPrint( "No trades! range: " , range ,"<", lastMinutes, "div 8!", "error:",self.fatalError)
		iPrint("%"*30)
	else:
		self.live_trades=True
	
	now= self._now()
	for h in self.history:
		q=h.__getstate__()
		if (now-q["date"])>=timedelta(minutes=0):
			wspolczynnik = self.alfas[alfa,int((now - q["date"]).total_seconds())]
			volume+=q["amount"]
			licznik+=q["price"]*q["amount"]*wspolczynnik
			mianownik+=q["amount"]*wspolczynnik
	

	
	
	avg_price = truncate(licznik/mianownik, 8)
	volume=truncate(volume, 2)

	VM_plus, VM_minus, size = vortex(10, 90, self.history, nowStart, alfa2)
	iPrint(VM_plus, VM_minus, size)
	if (VM_plus is not None) and (VM_minus is not None) and (size>5):
		future_factor = VM_plus - VM_minus
	else:
		future_factor=0
	post_avg_prediction = predictAvg(avg_price, future_factor, 2)
	avg_price_backup = avg_price
	if abs(post_avg_prediction - avg_price)/avg_price < decimal.Decimal("0.02"):
		avg_price= post_avg_prediction
		
	else:
		print ("!"*50)
		print avg_price , post_avg_prediction, VM_plus, VM_minus, abs(post_avg_prediction - avg_price)/avg_price, decimal.Decimal("0.02")
		cancel_all_active_orders_of_pair(self.api, self.pair)
		self.fatalError=True
		self.live_trades=False
		print "fatalError"
		
		
	'''if abs(self.depthIndicator)<decimal.Decimal("0.004"):
		if self.depthIndicatorCount>0:
			bak=avg_price
			avg_price = avg_price*(1+ self.depthIndicator)
			print bak, "-->", avg_price
	else:
		print ("!"*50)
		cancel_all_active_orders_of_pair(self.api, self.pair)
		self.fatalError=True
		self.live_trades=False
		print "fatalError"'''
	
	iPrint( "alfa= ", alfa, len(self.history), "orders", range, "/", lastMinutes, "min. vol", volume, pair)
	iPrint( "AVG: ",avg_price_backup, "-->", avg_price )
	iPrint(VM_plus, VM_minus, "-->" , future_factor)
	
	
	
	###################### UWZGLEDNIA BETA CZYNNIK!!! ###########################################
	if (beta<1):
		ticker = btceapi.getTicker(pair, None)
		avg_price_ticker=truncate(getattr(ticker, 'avg'),8)
		avg_price= truncate(avg_price*beta + avg_price_ticker*(1-beta), 8)
		iPrint( "Beta" , beta)
		iPrint( "AVG:",avg_price)
	
	#avgVector+=[[avg_price, now]]
	
	
	buy_floor=truncate(avg_price*(100000-buy_margin)/100000, 6)
	sell_ceiling=truncate(avg_price*(100000+sell_margin)/100000, 6)
	iPrint( "low: ",buy_floor)
	iPrint( "AVG:",avg_price)
	iPrint( "high:", sell_ceiling)
	self.avg_price_calc_time = self._now()
	print "AVGbedzieRowne1", self.avg_price_calc_time
	self.depthIndicator, self.depthIndicatorCount = 0,0
	
	
	return (buy_floor, avg_price, sell_ceiling)

def run(key_file, pair, buy_margin, sell_margin,logging, loggingTime, printing,  live_trades, gamma, eraSec, alfa, beta, buyChunk, sellChunk, buyBudget, sellBudget, interval, lastMinutes, epsilonSize, singleMode):
#Load the keys and create an API object from the first one.
	handler = btceapi.KeyHandler(key_file, resaveOnDeletion=True)
	key = handler.getKeys()[0]
	print "Trading with key %s" % key
	api = btceapi.TradeAPI(key, handler=handler)
	# Create a trader 
	trader = RangeTrader(api, pair, buy_margin, sell_margin, logging, loggingTime, printing , live_trades, gamma, eraSec, alfa, beta,
						buyChunk, sellChunk, buyBudget, sellBudget, lastMinutes, epsilonSize, singleMode)
	# Create a bot and add the trader to it.
	bot = btcebot.Bot()
	bot.addTrader(trader)
	# Add an error handler so we can iPrint( info about any failures
	bot.addErrorHandler(onBotError)    
    # The bot will provide the traders with updated information every
    # 15 seconds.
	bot.setCollectionInterval(interval)
	bot.start()
	print "Running; press Ctrl-C to stop"
	try:
		while 1:
			# you can do anything else you prefer in this loop while 
			# the bot is running in the background
			time.sleep(96000)
	except KeyboardInterrupt:
		print "Stopping..."
		
	finally:    
		bot.stop()
		cancel_all_active_orders_of_pair(api, pair)
        
if __name__ == '__main__':
	import argparse
	parser = argparse.ArgumentParser()
	parser.add_argument('key_file', 
						help='Path to a file containing key/secret/nonce data.')
	parser.add_argument('pair', 
						help='ltc_rur, eur_rur..')
	parser.add_argument('buy_margin', type=decimal.Decimal, default=399,
						help='buy margin f.i. 400 = 0.4%')
	parser.add_argument('sell_margin', type=decimal.Decimal, default=399,
						help='buy margin f.i. 400 = 0.4%')
	parser.add_argument('--live-trades', action="store_true",
						help='Actually make trades.')
	parser.add_argument('--gamma',type=decimal.Decimal, default=1.1, 
						help='gamma - see count EV function')
	parser.add_argument('--eraSec', type=decimal.Decimal,  default=0,
						help='ile spi miedzy pytaniami default=0')
	parser.add_argument('--alfa', type=decimal.Decimal, default=decimal.Decimal(0.994),
						help='default 0.997')
	parser.add_argument('--beta', type=decimal.Decimal, default=1,
						help='what part of alphaAVG goes to the AVG')
	parser.add_argument('--buyChunk', type=decimal.Decimal,
						help='how much 1st currency in one buy transaction')
	parser.add_argument('--sellChunk', type=decimal.Decimal,
						help='how much 1st currency in one sell transaction')
	parser.add_argument('--buyBudget', type=decimal.Decimal,
						help='what is our buy budget in 1st currency')
	parser.add_argument('--sellBudget', type=decimal.Decimal,
						help='what is our buy budget in 1st currency')
	parser.add_argument('--interval', type=decimal.Decimal, default=0.002,
						help='how often bot updates a trader')
	parser.add_argument('--lastMinutes', type=decimal.Decimal, default=60,
						help='how many minutes taken to avg')
	parser.add_argument('--logging', action="store_true",
						help='logging to the file')
	parser.add_argument('--loggingTime', action="store_true",
						help='logging timestamps to the file')
	parser.add_argument('--printing', action="store_true",
						help='printing stdout')
	parser.add_argument('--epsilonSize', type=decimal.Decimal, default=2,
						help='how big is epsilon')
	parser.add_argument('--singleMode', action="store_true",
						help='turbo if only one pair')
	args = parser.parse_args()
	run(args.key_file, args.pair, args.buy_margin, args.sell_margin, args.live_trades, args.logging, args.loggingTime, args.printing,
						args.gamma, args.eraSec, args.alfa, args.beta, args.buyChunk, args.sellChunk, args.buyBudget, args.sellBudget,
						args.interval, args.lastMinutes, args.epsilonSize, args.singleMode) 