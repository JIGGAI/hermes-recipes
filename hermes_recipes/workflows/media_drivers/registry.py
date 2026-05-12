"""Lookup table of known drivers.

Port of clawrecipes/src/lib/workflows/media-drivers/registry.ts. Tests
typically register a fake driver via ``register_driver`` to avoid hitting
the real skill subprocess.
"""

from typing import Iterable

from hermes_recipes.workflows.media_drivers.openai_image_gen import OpenAIImageGen
from hermes_recipes.workflows.media_drivers.types import MediaDriver, MediaType


_REGISTERED: list[MediaDriver] = [OpenAIImageGen()]


def register_driver(driver: MediaDriver) -> None:
    _REGISTERED.append(driver)


def reset_registry(initial: Iterable[MediaDriver] = (OpenAIImageGen(),)) -> None:
    """Reset the registry to *initial*. Intended for tests."""
    _REGISTERED.clear()
    _REGISTERED.extend(initial)


def get_driver(slug: str) -> MediaDriver | None:
    for driver in _REGISTERED:
        if driver.slug == slug:
            return driver
    return None


def get_drivers_by_type(media_type: MediaType) -> list[MediaDriver]:
    return [d for d in _REGISTERED if d.media_type == media_type]


def get_all_drivers() -> list[MediaDriver]:
    return list(_REGISTERED)


def is_driver_available(slug: str, env: dict[str, str]) -> bool:
    driver = get_driver(slug)
    if driver is None:
        return False
    return all(
        isinstance(env.get(var), str) and env[var].strip()
        for var in driver.required_env_vars
    )


def get_available_drivers(env: dict[str, str]) -> list[MediaDriver]:
    return [d for d in _REGISTERED if is_driver_available(d.slug, env)]


def get_available_drivers_by_type(
    media_type: MediaType, env: dict[str, str]
) -> list[MediaDriver]:
    return [d for d in get_drivers_by_type(media_type) if is_driver_available(d.slug, env)]
