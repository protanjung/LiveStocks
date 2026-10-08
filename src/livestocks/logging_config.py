"""Process-wide logging setup."""

import logging

LOG_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"


def configure_logging(level: str = "INFO") -> None:
    """Send log records of every logger to stderr in one consistent format."""
    logging.basicConfig(level=level.upper(), format=LOG_FORMAT)
