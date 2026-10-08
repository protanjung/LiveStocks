"""Process-wide logging setup built on loguru.
Everything is written to stderr in one format, as plain text or as one JSON object per line.
Records from the standard logging module (uvicorn, httpx, alembic) are routed into loguru too.
"""

import logging
import sys
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from loguru import Record


def _text_format(record: "Record") -> str:
    """Return the loguru format for one text line, showing bound fields only when present."""
    extra = " <dim>{extra}</dim>" if record["extra"] else ""
    return (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> <level>{level: <8}</level> "
        "<cyan>{name}</cyan> {message}" + extra + "\n{exception}"
    )


class InterceptHandler(logging.Handler):
    """Forward standard logging records to loguru, keeping their level and call site.
    It lets libraries that use the logging module share the application's sink and format.
    Install it on the root logger; configure_logging does so.
    """

    def emit(self, record: logging.LogRecord) -> None:
        """Re-emit one standard logging record through loguru.
        The level name is mapped when loguru knows it, otherwise the numeric level is used.
        The stack depth is adjusted so the reported call site is the original caller.
        """
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        named = logger.patch(lambda r: r.update(name=record.name))
        named.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def configure_logging(level: str = "INFO", *, json: bool = False) -> None:
    """Send every log record to stderr at the given level, as text or as JSON lines.
    Standard-library loggers are intercepted so uvicorn and httpx follow the same format.
    Calling it again replaces the previous configuration.
    """
    logger.remove()
    logger.add(
        sys.stderr,
        level=level.upper(),
        serialize=json,
        format="{message}" if json else _text_format,
    )
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        library_logger = logging.getLogger(name)
        library_logger.handlers = []
        library_logger.propagate = True
