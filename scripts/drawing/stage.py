"""The stage a drawing is composed on.

Every family used to compose on one fixed 960-unit canvas. That is right for a
standalone artifact and wrong for a figure inside a narrow column: the type
tiers are units on the stage, so a 960-unit drawing placed in a 350px slot
delivers its smallest tier at 3.5px. Enlarging the plate does not help (it
scales the type and the empty margin together), and scaling the payload is
refused, because the author does not decide the stage — the host does.

The stage is therefore a *compile-time* input, alongside profile, detail and
audience, and it is deliberately not a payload field. A family that knows how
to compose at another width scales its chrome (padding, gaps, gutters) with the
stage and leaves the type scale alone, so the type-to-stage ratio rises as the
stage falls and the delivered size rises with it.

Families are listed in `STAGE_AWARE` only once their geometry actually scales.
A stage other than the default is refused for every other kind: silently
composing at 960 and shipping a 3.5px figure is the failure this module exists
to prevent.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from .canvas_contract import CANVAS_WIDTH

# The kinds whose geometry scales with the stage. Adding a kind here is a
# promise that its padding, gaps and label columns are expressed in stage
# units rather than as literals measured against 960.
STAGE_AWARE = frozenset({"architecture", "state-machine", "swimlane"})

# The stage is a multiple of the same 4-unit grid every geometry constant sits
# on. The floor is where a node box still holds a two-line label; below it the
# drawing needs a different composition, not a smaller number.
MIN_STAGE_WIDTH = 240


@dataclass(frozen=True)
class StageSpec:
    """One stage width, and the name it is recorded under."""

    width: int = CANVAS_WIDTH
    key: str = "folio-960"

    def __post_init__(self) -> None:
        if self.width % 4:
            raise ValueError(f"stage width must be a multiple of 4, got {self.width}")
        if not MIN_STAGE_WIDTH <= self.width <= CANVAS_WIDTH:
            raise ValueError(
                f"stage width must be {MIN_STAGE_WIDTH}-{CANVAS_WIDTH}, got {self.width}")

    @property
    def scale(self) -> float:
        """How much this stage shrinks the 960-unit geometry."""
        return self.width / CANVAS_WIDTH

    @property
    def is_default(self) -> bool:
        return self.width == CANVAS_WIDTH

    def to_dict(self) -> dict[str, object]:
        return {"key": self.key, "width": self.width, "scale": round(self.scale, 4)}


DEFAULT_STAGE = StageSpec()

_CURRENT: ContextVar[StageSpec] = ContextVar("folio_stage", default=DEFAULT_STAGE)


def current() -> StageSpec:
    """The stage of the compile in progress."""
    return _CURRENT.get()


@contextmanager
def use(stage: StageSpec):
    """Compose inside ``stage`` for the duration of the block."""
    token = _CURRENT.set(stage)
    try:
        yield stage
    finally:
        _CURRENT.reset(token)


def require_aware(kind: str, stage: StageSpec) -> None:
    """Refuse a non-default stage for a family that cannot compose at one."""
    if stage.is_default or kind in STAGE_AWARE:
        return
    raise ValueError(
        f"{kind} cannot compose on a {stage.width}-unit stage; "
        f"stage-aware kinds: {', '.join(sorted(STAGE_AWARE))}")
