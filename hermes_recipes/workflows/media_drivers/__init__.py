"""Media generation drivers — image, video, audio.

Port of clawrecipes/src/lib/workflows/media-drivers/. Each driver is a thin
wrapper around a Hermes skill (Python script under ``~/.hermes/skills/<slug>/``)
that does the heavy API call; the driver knows the contract (env vars, output
path parsing) so workflow nodes can invoke media generation uniformly.

This Phase 5 cut ports:
  - types.py            ← types.ts
  - utils.py            ← utils.ts (Hermes-flavored skill roots)
  - registry.py         ← registry.ts
  - openai_image_gen.py ← openai-image-gen.driver.ts (representative)

Remaining drivers (NanoBananaPro, RunwayVideo, KlingVideo, LumaVideo,
GenericDriver) follow the same shape; deferred until requested.
"""

from hermes_recipes.workflows.media_drivers.types import (
    DurationConstraints,
    MediaDriver,
    MediaDriverInvokeOpts,
    MediaDriverResult,
    parse_duration,
)
from hermes_recipes.workflows.media_drivers.registry import (
    get_all_drivers,
    get_available_drivers,
    get_available_drivers_by_type,
    get_driver,
    get_drivers_by_type,
    is_driver_available,
)

__all__ = [
    "DurationConstraints",
    "MediaDriver",
    "MediaDriverInvokeOpts",
    "MediaDriverResult",
    "parse_duration",
    "get_all_drivers",
    "get_available_drivers",
    "get_available_drivers_by_type",
    "get_driver",
    "get_drivers_by_type",
    "is_driver_available",
]
