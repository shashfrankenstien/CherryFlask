import os, sys
from typing import Union, Callable
import time
from datetime import datetime as dt
from logging.handlers import RotatingFileHandler
import pickle
import hashlib

import holidays
from dateutil import tz
import tzlocal

from .print_logger import (
	LOGGER,
	LOG_FORMATTER
)

from .jobs import (
	# job types
	Job,
	OneTimeJob,
	RepeatJob,
	MonthlyJob,
	AsyncJobWrapper,
	NeverJob,

	# exceptions
	BadScheduleError
)

from .state import (
	BaseState,
	FileSystemState,
)



USHolidays = holidays.US()




class TaskScheduler(object):
	"""
	TaskScheduler: main class to setup, run and manage jobs

	Args:
	- check_interval (int): how often to check for pending jobs
	- holidays_calendar (holidays.HolidayBase): calendar to use for intervals like `businessday`
	- on_job_error (function(e)): function to call if any job fail
	- log_filepath (path): file to write logs to
	- log_maxsize (int): byte limit per log file
	- log_backups (int): number of backups of logs to retain
	- startup_grace_mins (int): grace period for tasks in case a schedule was missed because of app restart
	- persist_states (bool): store job logs on disk so that they can be read back on app restart
	"""

	def __init__(self,
		check_interval: int=5,
		holidays_calendar: Union[holidays.HolidayBase, None]=None,
		tzname: Union[str, None]=None,
		on_job_error: Union[Callable, None]=None,
		log_filepath: Union[str, None]=None,
		log_maxsize: int=5*1024*1024,
		log_backups: int=1,
		startup_grace_mins: int=0,
		persist_states: bool=True) -> None:

		self.jobs = []
		self._check_interval = check_interval
		self._startup_grace_mins = startup_grace_mins
		self.on_job_error = on_job_error

		tzname = tzname or tzlocal.get_localzone_name() # if None, default to local timezone
		if tz.gettz(tzname) is None:
			raise ValueError(f"unknown timezone '{tzname}'")
		self._tz_default = tzname

		if holidays_calendar is not None:
			self.holidays_calendar = holidays_calendar
		else:
			self.holidays_calendar = USHolidays

		# setup logging
		self.log_filepath = log_filepath
		if self.log_filepath is not None:
			fh = RotatingFileHandler(
				filename=self.log_filepath,
				maxBytes=log_maxsize,
				backupCount=log_backups
			)
			fh.setFormatter(LOG_FORMATTER)
			LOGGER.addHandler(fh)

		# setup state persistance over app restarts
		self._state_manager = None
		if persist_states:
			self._state_manager = FileSystemState()

		# set schedule defaults
		self.__reset_defaults()


	def __reset_defaults(self):
		self.interval = None
		self.temp_time = None
		self.tzname = self._tz_default # timezone default
		self._strict_monthly = None
		self.job_calendar = None

	# -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
	# -=-=-=-=-=-=-=-=-= New job definition methods =-=-=-=-=-=-=-=-=-
	# -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=

	def every(self, interval, calendar=None):
		'''
		interval is either one of the keys of RUNABLE_DAYS
		or integer denoting number of seconds for RepeatJob
		'''
		self.interval = interval
		self.job_calendar = calendar
		return self

	def on(self, *args, **kwargs):
		'''alias of .every() method'''
		return self.every(*args, **kwargs)

	def strict_date(self, strict):
		'''
		required to be called when scheduling MonthlyJob
		- see MonthlyJob docstring
		'''
		if not MonthlyJob.is_valid_interval(self.interval) or not isinstance(strict, bool):
			raise BadScheduleError(".strict_date(bool) only used for monthly schedule. ex: .every('31st').strict_date(True)..")
		self._strict_monthly = strict
		return self

	def at(self, time_string):
		'''
		24 hour time string of when to run job
		- example: '15:00' for 3PM
		'''
		if self.interval is None:
			self.every('day')
		self.temp_time = time_string
		return self

	def timezone(self, tzname):
		'''
		timezone string as defined in pytz module
		- example US/Eastern
		- defaults to system timezone
		'''
		test = tz.gettz(tzname)
		if test is None:
			raise BadScheduleError(f"unknown timezone '{tzname}'")
		self.tzname = tzname
		return self

	def tz(self, *args, **kwargs):
		'''alias of .timezone() method'''
		return self.timezone(*args, **kwargs)

	def do(self, func, do_parallel=False, **kwargs):
		'''
		register 'func' for the job
		- if do_parallel is True, run job in a prallel thread
		- pass kwargs into 'func' at execution
		'''
		if self.interval is None:
			raise Exception('Use .at()/.every().at() before .do()')
		if self.temp_time is None:
			self.temp_time = dt.now(tz.gettz(self._tz_default)).strftime("%H:%M") # FIXME: default timezone is fine?? Or not I guess

		new_jobid = len(self.jobs)
		if RepeatJob.is_valid_interval(self.interval):
			j = RepeatJob(new_jobid, self.interval, None, func, kwargs)
		elif OneTimeJob.is_valid_interval(self.interval):
			j = OneTimeJob(new_jobid, self.interval, self.temp_time, func, kwargs)
		elif MonthlyJob.is_valid_interval(self.interval):
			j = MonthlyJob(new_jobid, self.interval, self.temp_time, func, kwargs, strict_date=self._strict_monthly)
		elif Job.is_valid_interval(self.interval):
			j = Job(new_jobid, self.interval, self.temp_time, func, kwargs)
		elif NeverJob.is_valid_interval(self.interval):
			j = NeverJob(new_jobid, self.interval, self.temp_time, func, kwargs)
		else:
			raise BadScheduleError("{} is not valid\n".format(self.interval))

		j.init(
			calendar=self.holidays_calendar if self.job_calendar is None else self.job_calendar,
			tzname=self.tzname,
			generic_err_handler=self.on_job_error,
			startup_grace_mins=self._startup_grace_mins
		)
		# register callbacks to save job logs to file so it can be restored on app restart
		if isinstance(self._state_manager, BaseState):
			j.register_callback(self._state_manager.save_job_logs, cb_type="onenable")
			j.register_callback(self._state_manager.save_job_logs, cb_type="ondisable")
			j.register_callback(self._state_manager.save_job_logs, cb_type="oncomplete")
		if do_parallel:
			j = AsyncJobWrapper(j)
		print(j)
		self.jobs.append(j)
		self.__reset_defaults()
		return j

	def do_parallel(self, func, **kwargs):
		'''helper function to run job in a separate thread'''
		return self.do(func, do_parallel=True, **kwargs)

	# -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
	# -=-=-=-=-=-=-=-= Scheduler control methods =-=-=-=-=-=-=-=-=-=-=
	# -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=

	def check(self):
		'''check if a job is due'''
		for j in self.jobs.copy(): # work on a shallow copy of this list - safer in case the list changes. TODO: maybe use locks instead?
			if j.is_due() and not j.is_running:
				j.run()

	def start(self):
		'''blocking function that checks for jobs every 'check_interval' seconds'''
		try:
			if isinstance(self._state_manager, BaseState):
				self._state_manager.restore_all_job_logs(self.jobs)
		except Exception as e:
			print("unable to restore states:", str(e))
		self._running_auto = True
		try:
			while self._running_auto:
				try:
					self.check()
					time.sleep(self._check_interval)
				except KeyboardInterrupt:
					print("KeyboardInterrupt")
					self.stop()
		finally:
			print("Stopping. Please wait, checking active async jobs ..")
			self.join()
		print(self, "Done!")

	def join(self):
		'''wait for any async jobs to complete'''
		for j in self.jobs:
			if isinstance(j, AsyncJobWrapper) and j.is_running: # wait for any running parallel tasks
				j.proc.join()
				print(j, "exited")

	def stop(self):
		'''stop job started with .start() method'''
		self._running_auto = False

	def get_job_by_id(self, jobid):
		for j in self.jobs:
			if j.jobid==jobid:
				return j
		return None

	def rerun(self, jobid):
		selected_job = self.get_job_by_id(jobid)
		if selected_job is None:
			raise IndexError("Invalid job id")
		if selected_job.is_running:
			raise RuntimeError("Cannot rerun a running task")
		if not isinstance(selected_job, AsyncJobWrapper):
			selected_job = AsyncJobWrapper(selected_job)
		selected_job.run(is_rerun=True)

	def disable_all(self):
		for j in self.jobs:
			j.disable()

	def enable_all(self):
		for j in self.jobs:
			j.enable()
