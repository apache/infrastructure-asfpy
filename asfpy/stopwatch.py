import time
import logging
import inspect
import asyncio
import functools

class Stopwatch:
    def __init__(self, name=None):
        self.name = name
        # Initialize logger in constructor; default to root logger
        frame = inspect.currentframe().f_back
        module = inspect.getmodule(frame)
        self.logger = getattr(module, '_LOGGER', logging.getLogger())
        self.start_time = time.time()  # set this, at exit time from function

    def format(self, duration_ms=None):
        duration_ms = duration_ms or self.elapsed_ms()
        return f"{self.name or 'Operation'} took {duration_ms:.2f} ms"

    def elapsed_ms(self):
        return (time.time() - self.start_time) * 1000

    def reset(self):
        self.start_time = time.time()

    def __call__(self, func):
        if self.name is None:
            self.name = f"Function '{func.__name__}'"
        # Check if the function is async
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                self.start_time = time.time()  # Reset start_time at function call
                try:
                    return await func(*args, **kwargs)
                finally:
                    self.logger.info(self.format())
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                self.start_time = time.time()  # Reset start_time at function call
                try:
                    return func(*args, **kwargs)
                finally:
                    self.logger.info(self.format())
            return sync_wrapper

    def __enter__(self):
        # Update name for context manager if not set
        if self.name is None:
            frame = inspect.currentframe().f_back
            self.name = f"Block in {frame.f_code.co_name} at line {frame.f_lineno}"
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logger.info(self.format())
