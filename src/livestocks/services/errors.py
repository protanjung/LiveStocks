"""Exceptions raised by the application services.
ServiceError is the base class; the subclasses say why a ticker could not be served.
The api layer maps each one to an HTTP status, the ui layer to a notification.
"""


class ServiceError(Exception):
    """Base class for every failure of a service operation.
    Catch it to handle any service problem in one place.
    Subclasses name the specific cause.
    """


class TickerNotFoundError(ServiceError):
    """The ticker does not exist on TradingView.
    Raised after the first crawl proved it, or when a known failure is replayed.
    Permanent, so retrying will not help.
    """


class UpstreamUnavailableError(ServiceError):
    """TradingView could not be reached or its data could not be read.
    Usually transient; the updater keeps retrying with backoff.
    A later request may succeed.
    """


class CrawlTimeoutError(ServiceError):
    """The first crawl of a ticker did not finish in time.
    The crawl keeps running in the background.
    Asking again later returns the data once it is stored.
    """


class SuggestionNotFoundError(ServiceError):
    """No stock suggestion report is stored for the requested date, or none at all yet.
    The routine that produces them runs on weekday mornings.
    Asking again after its next run may succeed.
    """
