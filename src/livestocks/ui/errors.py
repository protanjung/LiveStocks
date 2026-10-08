"""Translation of domain and service errors into text a visitor can read.
HANDLED lists the exception types the pages catch and show as notifications.
Anything else is a bug and is allowed to propagate.
"""

from livestocks.domain import DomainError
from livestocks.services import ServiceError

HANDLED = (DomainError, ServiceError)


def describe(error: Exception) -> str:
    """Return the notification text for an error raised by a domain or service call.
    Domain and service errors already carry a user-facing message, which is used as is.
    Any other exception gets a generic sentence so internals never reach the browser.
    """
    if isinstance(error, HANDLED):
        return str(error)
    return "Something went wrong. Try again in a moment."
