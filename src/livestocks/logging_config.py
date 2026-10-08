"""Process-wide logging setup.
All loggers write to stderr in one format.
The level comes from the LIVESTOCKS_LOG_LEVEL setting.
"""

import logging

LOG_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"


def configure_logging(level: str = "INFO") -> None:
    """Send log records of every logger to stderr in one consistent format.
    level is a standard logging level name such as INFO or DEBUG.
    Call it once at start-up; logging ignores repeated calls.
    """
    logging.basicConfig(level=level.upper(), format=LOG_FORMAT)
