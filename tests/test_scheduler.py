import os
import time
from datetime import datetime as dt, timedelta
from dateutil.parser import parse as date_parse
from flask_production import TaskScheduler
from flask_production.hols import TradingHolidays

def job(x, y):
	time.sleep(0.1)
	print(x, y)

def test_registry():
	s = TaskScheduler()
	s.every("businessday").at("10:00").do(job, x="hello", y="world")
	s.on('2019-05-16').do(job, x="hello", y="world")
	assert len(s.jobs) == 2


def test_regular():
	d = dt.now().replace(hour=23, minute=59, second=0, microsecond=0)
	s = TaskScheduler()
	s.every("day").at("23:59").do(job, x="hello", y="world")
	assert (s.jobs[0].next_timestamp==dt.timestamp(d))


def test_day_of_week():
	now = dt.now()
	today_str = now.strftime("%A").lower()
	in2sec_str = now.strftime("%H:%M")
	s = TaskScheduler()
	s.every(today_str).at(in2sec_str).do(job, x="hello", y=today_str)
	assert len(s.jobs) == 1
	time.sleep(0.5)
	s.check()
	# test if next run greater than 6 days, less than 8 days from now
	test_timestamp = time.time()
	assert s.jobs[0].next_timestamp > test_timestamp+(6*24*60*60)
	assert s.jobs[0].next_timestamp < test_timestamp+(8*24*60*60)


def test_holidays():
	s = TaskScheduler() # default holidays calendar
	s.every("businessday").at("10:00").do(job, x="hello", y="world")
	assert(s.jobs[0]._job_must_run_today(date_parse("2020-04-09"))==True)
	assert(s.jobs[0]._job_must_run_today(date_parse("2020-04-10"))==True) #Good Friday is not a US holiday by default

	s = TaskScheduler(holidays_calendar=TradingHolidays())
	s.every("businessday").at("10:00").do(job, x="hello", y="world")
	assert(s.jobs[0]._job_must_run_today(date_parse("2020-04-09"))==True)
	assert(s.jobs[0]._job_must_run_today(date_parse("2020-04-10"))==False) #test Custom Good Friday holiday
	assert(s.jobs[0]._job_must_run_today(date_parse("2020-04-11"))==False) #saturday


def test_onetime():
	yesterday = (dt.now() - timedelta(days=1)).replace(hour=23, minute=59, second=0, microsecond=0)
	tomorrow = (dt.now() + timedelta(days=1)).replace(hour=23, minute=59, second=0, microsecond=0)
	s = TaskScheduler()
	s.on(yesterday.strftime("%Y-%m-%d")).at("23:59").do(job, x="hello", y="world")
	s.on(tomorrow.strftime("%Y-%m-%d")).at("23:59").do(job, x="hello", y="world")
	for j in s.jobs:
		assert (j.next_timestamp==dt.timestamp(tomorrow) or j.next_timestamp==0)
	assert len(s.jobs) == 2
	s.check()
	assert len(s.jobs) == 1


def test_repeat():
	d = time.time()
	interval = 1
	s = TaskScheduler()
	s.every(interval).do(job, x="hello", y="world")
	assert (abs(s.jobs[0].next_timestamp - (d+interval)) < 0.1)
	time.sleep(interval)
	s.check()
	assert (abs(s.jobs[0].next_timestamp - (d+(2*interval))) < 0.1)


def test_repeat_parallel():
	d = time.time()
	interval = 1
	s = TaskScheduler()
	s.every(interval).do(job, x="hello", y="world", do_parallel=True)
	s.every(interval).do(job, x="hello", y="world", do_parallel=True)
	ts = s.jobs[0].next_timestamp
	assert (abs(ts - (d+interval)) < 0.1)
	time.sleep(interval)
	s.check()
	assert (s.jobs[0].next_timestamp == ts) # still not rescheduled
	time.sleep(0.2)
	assert (s.jobs[0].next_timestamp != ts) # rescheduled parallely
	assert (abs(s.jobs[0].next_timestamp - (d+(2*interval))) < 0.1)
	assert (abs(s.jobs[0].next_timestamp - s.jobs[1].next_timestamp) < 0.1)


def test_error_callback():
	interval = 1
	errors = []
	err_count = 0

	def failing_job(msg):
		raise Exception(msg)

	def err(e):
		nonlocal errors, err_count
		errors.append(str(e))
		err_count += 1

	def err_specific(e):
		nonlocal errors, err_count
		errors.append(str(e)+"_specific")
		err_count += 1

	s = TaskScheduler(on_job_error=err)
	s.every(interval).do(failing_job, msg='one', do_parallel=True)
	s.every(interval).do(failing_job, msg='two')
	s.every(interval).do(failing_job, msg='three', do_parallel=True).catch(err_specific)
	time.sleep(interval)
	s.check()
	time.sleep(0.2)
	assert(sorted(errors)==sorted(['one', 'two', 'three_specific'])) # err callbacks were called
	assert(err_count==3)
