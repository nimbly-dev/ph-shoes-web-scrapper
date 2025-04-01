import logging
import os
import sys

def get_logger(name: str, log_file: str = None) -> logging.Logger:
    """
    Create and return a logger with the given name.
    If log_file is provided, log to that file as well as to the console.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Clear existing handlers if any (avoids duplicate logs)
    if logger.hasHandlers():
        logger.handlers.clear()

    formatter = logging.Formatter(f'{name} %(asctime)s - %(levelname)s: %(message)s')

    # Console output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Optional file output
    if log_file:
        # Auto-create parent directory if it doesn't exist
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

        file_handler = logging.FileHandler(log_file, mode='w')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
