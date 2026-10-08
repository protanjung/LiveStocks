"""Retry helper for crawler requests."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from livestocks.crawler.errors import UpstreamError

T = TypeVar("T")


async def with_retries(
    attempt: Callable[[], Awaitable[T]], *, attempts: int = 3, base_delay: float = 2.0
) -> T:
    """Call ``attempt`` until it succeeds, retrying only UpstreamError with exponential backoff.
    Any other exception, NotFoundError included, propagates immediately.
    After the last failed attempt the final UpstreamError is raised.
    """
    last: UpstreamError | None = None
    for n in range(attempts):
        try:
            return await attempt()
        except UpstreamError as e:
            last = e
            if n < attempts - 1:
                await asyncio.sleep(base_delay * 2**n)
    assert last is not None
    raise last
