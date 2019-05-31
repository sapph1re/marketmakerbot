import threading
import time
import random


def run_repeatedly(func, interval, thread_name=None, *args, **kwargs):
    """
    In a new thread executes func() every <interval> seconds
    if func() execution takes more than <interval> seconds it will repeat right after the previous execution completes
    :param func: function to execute repeatedly
    :param interval: number of seconds between executions
    :param thread_name: name of the thread to be created (useful for logging)
    :param args: arbitrary arguments passed to func()
    :param kwargs: arbitrary keyword arguments passed to func()
    :return: threading.Event, when you .set() it, execution stops
    """
    def _run(stop_event):
        while not stop_event.is_set():
            last_time = time.time()
            func(*args, **kwargs)
            time_passed = time.time() - last_time
            if time_passed < interval:
                time.sleep(interval - time_passed)
    stop = threading.Event()
    thread = threading.Thread(target=_run, args=(stop,), name=thread_name)
    thread.setDaemon(True)
    thread.start()
    return stop


def run_at_random_intervals(func, min_interval, max_interval, thread_name=None, *args, **kwargs):
    """
    In a new thread executes func() every random interval anywhere from <min_interval> to <max_interval> seconds.
    :param func: function to execute at random intervals
    :param min_interval: min number of seconds between executions
    :param max_interval: max number of seconds between executions
    :param thread_name: name of the thread to be created (useful for logging)
    :param args: arbitrary arguments passed to func()
    :param kwargs: arbitrary keyword arguments passed to func()
    :return: threading.Event, when you .set() it, execution stops
    """
    def _run(stop_event):
        while not stop_event.is_set():
            interval = random.randint(min_interval, max_interval)
            last_time = time.time()
            func(*args, **kwargs)
            time_passed = time.time() - last_time
            if time_passed < interval:
                time.sleep(interval - time_passed)
    stop = threading.Event()
    thread = threading.Thread(target=_run, args=(stop,), name=thread_name)
    thread.setDaemon(True)
    thread.start()
    return stop
