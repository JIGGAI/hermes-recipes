"""Constants shared across hermes-recipes.

Port of clawrecipes/src/lib/constants.ts.
"""

from typing import Final, Literal

VALID_ROLES: Final[tuple[str, ...]] = ("dev", "devops", "lead", "test")
ValidRole = Literal["dev", "devops", "lead", "test"]

VALID_STAGES: Final[tuple[str, ...]] = ("backlog", "in-progress", "testing", "done")
ValidStage = Literal["backlog", "in-progress", "testing", "done"]

MAX_RECIPE_ID_AUTO_INCREMENT: Final[int] = 1000

DEFAULT_TICKET_NUMBER: Final[str] = "0000"
