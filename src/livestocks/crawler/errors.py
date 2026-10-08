"""Exceptions raised while fetching data from the outside world.
CrawlError is the base; the subclasses say whether a retry could help.
Callers catch CrawlError to treat any crawl failure alike.
"""


class CrawlError(Exception):
    """Base class for every failure while crawling a ticker.
    Catch it to handle any crawl problem in one place.
    The subclasses separate permanent from transient causes.
    """


class NotFoundError(CrawlError):
    """The ticker does not exist on TradingView or has no forecast page.
    This is permanent, so the crawler never retries it.
    Later layers can report it as an unknown ticker.
    """


class UpstreamError(CrawlError):
    """A transient failure such as a network error, rate limit or server error.
    Worth retrying with backoff; it is raised after the last attempt fails.
    Also used for websocket and price-feed failures.
    """


class ParseError(CrawlError):
    """The page or feed loaded but the expected data was missing.
    This usually means TradingView changed its layout.
    It is not retried because the response would be the same.
    """
