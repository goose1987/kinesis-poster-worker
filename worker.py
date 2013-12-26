import sys
# until Kinesis Python SDK is released the absolute path 
# to the Kinesis SDK must be included
sys.path.insert(0, 
	'/Users/brettf/dev/AWSSA-collab/examples/python/kinesis-poster-worker/boto-2.9.8')
import boto
import argparse
import json
import threading
import time

from argparse import RawTextHelpFormatter
import datetime
from boto.canal.exceptions import ResourceNotFoundException
from boto.canal.exceptions import ProvisionedThroughputExceededException
import poster


kinesis = boto.connect_canal()
iter_type_at = 'AT_SEQUENCE_NUMBER'
iter_type_after = 'AFTER_SEQUENCE_NUMBER'
iter_type_trim = 'TRIM_HORIZON'
iter_type_latest = 'LATEST'

def find_eggs(records):
	for record in records:
		text = record['Data'].lower()
		locs = [n for n in xrange(len(text)) if text.find('egg', n) == n]
		if len(locs) > 0:
			print '+--> egg location:', locs, '<--+'


class KinesisWorker(threading.Thread):
	"""docstring for KinesisWorker"""
	def __init__(self, stream_name, shard_id, iterator_type, 
				 worker_time=30, sleep_interval=0.5,
				 name=None, group=None, args=(), kwargs={}):
		super(KinesisWorker, self).__init__(name=name, group=group, 
										  args=args, kwargs=kwargs)
		self.stream_name = stream_name
		self.shard_id = str(shard_id)
		self.iterator_type = iterator_type
		self.worker_time = worker_time
		self.sleep_interval = sleep_interval
		self.total_records = 0


	def run(self):
		my_name = threading.current_thread().name
		print '+ KinesisWorker:', my_name
		print '+-> working with iterator:', self.iterator_type
		response = kinesis.get_shard_iterator(self.stream_name, 
			self.shard_id, self.iterator_type)
		next_iterator = response['ShardIterator']
		print '+-> getting next records using iterator:', next_iterator
		
		start = datetime.datetime.now()
		finish = start + datetime.timedelta(seconds=self.worker_time)
		while finish > datetime.datetime.now():
			try:
				response = kinesis.get_next_records(next_iterator, limit=25)
				self.total_records += len(response)

				if len(response['Records']) > 0:
					print '\n+-> {1} Got {0} Worker Records'.format(
						len(response['Records']), my_name)
					find_eggs(response['Records'])
				else:
					sys.stdout.write('.')
					sys.stdout.flush()
				next_iterator = response['NextShardIterator']
				time.sleep(self.sleep_interval)
			except ProvisionedThroughputExceededException as ptee:
				print ptee.message
				time.sleep(5)

if __name__ == '__main__':
	parser = argparse.ArgumentParser(
		description='''Create or connect to a Kinesis stream and create workers 
that hunt for "egg" in records from each shard.''', 
		formatter_class=RawTextHelpFormatter)
	parser.add_argument('stream_name', 
		help='''the name of the Kinesis stream to either create or connect''')
	parser.add_argument('--worker_time', type=int, default=30, 
		help='''the worker's duration of operation''')
	parser.add_argument('--sleep_interval', type=float, default=0.5, 
		help='''the worker's work loop sleep interval''')

	args = parser.parse_args()

	stream = kinesis.describe_stream(args.stream_name)
	print json.dumps(stream, sort_keys=True, indent=2, separators=(',', ': '))
	shards = stream['StreamDescription']['Shards']
	print '# Shard Count:', len(shards)

	threads = []
	start_time = datetime.datetime.now()
	for shard_id in xrange(len(shards)):
		worker_name = 'shard_worker:'+str(shard_id)
		print '#-> shardId:', shards[shard_id]['ShardId']
		worker = KinesisWorker(
			stream_name=args.stream_name, 
			shard_id=shards[shard_id]['ShardId'], 
			# iterator_type=iter_type_trim, 
			iterator_type=iter_type_latest,
			worker_time=args.worker_time,
			sleep_interval=args.sleep_interval,
			name=worker_name
			)
		worker.daemon = True
		threads.append(worker)
		print '#-> starting: ', worker_name
		worker.start()

	# Wait for all threads to complete
	for t in threads:
	    t.join()
	finish_time = datetime.datetime.now()
	duration = (finish_time - start_time).total_seconds()
	total_records = poster.sum_posts(threads)
	print "-=> Exiting Worker Main <=-"
	print "  Total Records:", total_records
	print "     Total Time:", duration
	print "  Records / sec:", total_records / duration