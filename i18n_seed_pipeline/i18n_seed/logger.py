import logging
import sys

def setup_logger(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("i18n-seed")
    if logger.handlers:
        return logger
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    h = logging.StreamHandler(sys.stdout)
    fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    h.setFormatter(fmt)
    logger.addHandler(h)
    return logger
