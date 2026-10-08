"""Public HTTP API: routes, response models and error mapping.
build_router mounts the endpoints; register_error_handlers turns service errors into HTTP answers.
Both depend only on the services layer, never on storage or the crawler.
"""

from livestocks.api.errors import register_error_handlers
from livestocks.api.models import ErrorResponse, ForecastResponse
from livestocks.api.routes import build_router

__all__ = ["ErrorResponse", "ForecastResponse", "build_router", "register_error_handlers"]
