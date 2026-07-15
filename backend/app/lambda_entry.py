from __future__ import annotations

from .main import app

try:
    from mangum import Mangum  # type: ignore[import-not-found]
except ImportError:  # Local development does not install Lambda dependencies.
    handler = None
else:
    handler = Mangum(app, lifespan="auto")
