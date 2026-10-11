"""Public HTTP API: routes, response models and error mapping.
build_router and build_suggestions_router mount the endpoints; register_error_handlers maps errors.
Both depend only on the services layer, never on storage or the crawler.
"""

from livestocks.api.errors import register_error_handlers
from livestocks.api.models import ErrorResponse, ForecastResponse, SuggestionsResponse
from livestocks.api.routes import build_router
from livestocks.api.suggestions import build_suggestions_router

__all__ = [
    "ErrorResponse",
    "ForecastResponse",
    "SuggestionsResponse",
    "build_router",
    "build_suggestions_router",
    "register_error_handlers",
]
