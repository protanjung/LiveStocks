"""Exceptions raised while fetching data from the outside world."""


class CrawlError(Exception):
    """Base class for every failure while crawling a ticker."""


class NotFoundError(CrawlError):
    """The ticker does not exist on TradingView, or has no forecast page."""


class UpstreamError(CrawlError):
    """A transient failure (network, rate limit, server error) that is worth retrying."""


class ParseError(CrawlError):
    """The page or feed loaded but its data was missing; the upstream layout probably changed."""
