"""Retry helper for crawler requests, built on tenacity.
Only transient UpstreamError failures are retried; everything else surfaces at once.
Delays grow exponentially from a base value and carry a little random jitter.
"""

import asyncio
from collections.abc import Awaitable, Callable

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from livestocks.crawler.errors import UpstreamError

MAX_DELAY = 30.0  # seconds; one wait never exceeds this
JITTER = 1.0  # seconds of random extra delay, so parallel retries do not line up


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


async def with_retries[T](
    attempt: Callable[[], Awaitable[T]], *, attempts: int = 3, base_delay: float = 2.0
) -> T:
    """Call ``attempt`` until it succeeds, retrying only UpstreamError with backoff and jitter.
    Any other exception, NotFoundError included, propagates immediately.
    After the last failed attempt the final UpstreamError is raised.
    """
    retrying = AsyncRetrying(
        retry=retry_if_exception_type(UpstreamError),
        stop=stop_after_attempt(attempts),
        wait=wait_exponential_jitter(multiplier=base_delay, max=MAX_DELAY, jitter=JITTER),
        sleep=_sleep,
        reraise=True,
    )
    return await retrying(attempt)
