"""Guards for live page code, so one failing refresh cannot blank a page or flood the log.
guarded wraps a timer step; render_or_notice wraps a first render and shows a notice on failure.
Expected domain and service errors are described to the visitor, anything else gets a generic line.
"""

import time
from collections.abc import Awaitable, Callable

from loguru import logger
from nicegui import ui

from livestocks.ui.errors import describe
from livestocks.ui.primitives import empty_card

LOG_EVERY = 60.0  # seconds between repeated log lines for the same failing step


def guarded(name: str, step: Callable[[], Awaitable[None]]) -> Callable[[], Awaitable[None]]:
    """Wrap a timer or refresh step so a failure is logged instead of raised on every tick.
    The same step logs at most once every LOG_EVERY seconds, so a broken service cannot flood the log.
    The wrapper keeps the timer alive, and the page keeps showing its last good content.
    """
    last_logged = {"at": float("-inf")}

    async def run() -> None:
        try:
            await step()
        except Exception as e:  # noqa: BLE001 - a live page must survive any refresh failure
            now = time.monotonic()
            if now - last_logged["at"] >= LOG_EVERY:
                last_logged["at"] = now
                logger.opt(exception=e).error("{} failed", name)

    return run


async def render_or_notice(body: Callable[[], Awaitable[None]]) -> None:
    """Run a page's first render, and show a notice in place of the content if it fails.
    The error is logged with its traceback, and the visitor sees its description when it is a known error.
    Pages call it for their first render only; later refreshes go through guarded.
    """
    try:
        await body()
    except Exception as e:  # noqa: BLE001 - show a notice rather than a blank page
        logger.opt(exception=e).error("page render failed")
        ui.html(empty_card("This page could not load", describe(e)), sanitize=False)
