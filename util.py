"""
Logging configuration and utilities.
"""

import logging
import logging.config
from typing import Optional
from functools import wraps
import time
from config.settings import LOGGING_CONFIG

# Configure logging
logging.config.dictConfig(LOGGING_CONFIG)

def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the specified name."""
    return logging.getLogger(name)


def log_performance(func):
    """Decorator to log function execution time."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger = get_logger(func.__module__)
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            elapsed_time = time.time() - start_time
            logger.info(f"{func.__name__} completed in {elapsed_time:.2f} seconds")
            return result
        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(f"{func.__name__} failed after {elapsed_time:.2f} seconds: {str(e)}")
            raise
    return wrapper


class TimingContext:
    """Context manager for timing operations."""
    
    def __init__(self, name: str, logger: Optional[logging.Logger] = None):
        self.name = name
        self.logger = logger or get_logger(__name__)
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, *args):
        elapsed = time.time() - self.start_time
        self.logger.info(f"{self.name} took {elapsed:.2f} seconds")
