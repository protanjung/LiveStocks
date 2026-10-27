"""A wrapper around NiceGUI's user simulation that keeps the livestocks modules importable.
The simulation removes every page module and its parent packages from sys.modules when it ends.
Restoring them afterwards stops later tests, which patch livestocks modules by name, from failing.
"""

import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from nicegui.testing import User, user_simulation

MAIN = Path(__file__).parent / "main.py"


@asynccontextmanager
async def simulate() -> AsyncGenerator[User]:
    """Yield a simulated browser user connected to the pages registered on the fake services."""
    saved = {
        k: v for k, v in sys.modules.items() if k == "livestocks" or k.startswith("livestocks.")
    }
    try:
        async with user_simulation(main_file=MAIN) as user:
            yield user
    finally:
        sys.modules.update(saved)
