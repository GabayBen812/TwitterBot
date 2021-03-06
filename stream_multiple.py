# Another method using streaming (mitigates the wait on rate limit issue)
import tweepy
import time
import json
import sys
from datetime import datetime
from tweepy import Stream
from tweepy.streaming import StreamListener
from check_exchange import *
import re
import threading

# Listener class
class Listener(StreamListener):
	def __init__(self, users, user_ids, sell_coin, hold_time, buy_volume, simulate, exchange, exchange_data, log_file=None):
		super(Listener,self).__init__()

		# Define variables for the class when listener is created
		self.users = users
		self.user_ids = user_ids
		self.sell_coin = sell_coin
		self.hold_time = hold_time
		self.buy_volume = buy_volume
		self.simulate = simulate
		self.exchange = exchange
		self.exchange_data = exchange_data
		self.log_file = log_file

	# Returns a pair of Coin symbol and base coin e.g. ['DOGE', 'BTC']
	def substring_match(self, text, num_letters):
		match = re.search('[A-Z]{%d}' % num_letters, text)
		if not match:
			return None

		match = match[0]
		# Specific ticker of 1INCH symbol
		if match == 'INCH':
			match = '1INCH'

		return [match, self.sell_coin]

	# Code to run on tweet
	def on_status(self, status):
	
		# Tweets with mentions
		try:
			if not status.truncated:
				full_text = status.text
			else:
				full_text = status.extended_tweet['full_text']

			if status.user.id not in self.user_ids:
				return

			print('\n\n\n%s: %s \n\n%s %s' % (datetime.now().strftime('%H:%M:%S'), full_text, status.user.screen_name, status.user.id_str))
			print(status.created_at)

			if any(substr in full_text.lower() for substr in self.users[status.user.screen_name]['keywords']) and status.in_reply_to_status_id is None and status.retweeted is False:
				print('\n\nMoonshot Inbound!\n\n')
				
				# Loop from maximum coin name length to shortest coin name length 
				for i in range(6, 2, -1):
					pair = self.substring_match(full_text, i)
					if not pair:
						continue
					try:
						# Get coin volume from cached trade volumes and execute trade
						coin_vol = self.exchange_data.buy_vols[pair[0]]
						self.exchange.execute_trade(pair, hold_time=self.hold_time, buy_volume=coin_vol, simulate=self.simulate)

						# If successful, break
						break

					except Exception as e:
						print('\nTried executing trade with ticker %s, did not work' % pair[0])
						print(e)

				# Log tweet
				if self.log_file:
					self.log_file.write(status)

		except Exception as e:
			print('\nError when handling tweet')
			print(e)

		print('\nRestarting stream\n')

	# Streaming error handling
	def on_error(self, status_code):
		print('Error in streaming: %d' % status_code)
		if status_code == 420:
			time.sleep(10)


# Stream tweets
def stream_tweets(api, users, sell_coin, hold_time, buy_volume, simulate, exchange, log_file=None):
	
	# Set and list of ids of users tracked
	user_ids_list = [i['id'] for i in users.values()]
	user_ids_set = [int(i) for i in user_ids_list]

	# Get exchange tickers and calculate volumes to buy for each tradeable crypto
	exchange_data = exchange_pull(exchange)
	
	# Create the Tweepy streamer
	listener = Listener(users, user_ids_set, sell_coin, hold_time, buy_volume, simulate, exchange, exchange_data, log_file=log_file)
	stream = Stream(auth=api.auth, listener=listener,wait_on_rate_limit=True, wait_on_rate_limit_notify=True)

	# Start stream and query prices
	print('\nStarting stream\n')
	
	# Try catch for different termination procedures
	try:
		# Create daemon thread which exits when other thread exits
		d = threading.Thread(name='daemon', target = exchange_data.buy_volumes, args=(buy_volume,20*60))
		d.setDaemon(True)
		d.start()

		# Start streaming tweets
		stream.filter(follow=user_ids_list)
		
	# Keyboard interrupt kills the whole program
	except KeyboardInterrupt as e:
		stream.disconnect()
		print("\nStopped stream")
		exit()
	
	# Disconnect the stream and kill the thread looking for prices
	finally:
		print('\nDone\n')
		exchange_data.stopflag = True
		stream.disconnect()

