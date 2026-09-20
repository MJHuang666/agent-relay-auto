"""Build an exact Planner wake adapter without cross-tool fallback."""

from __future__ import annotations

from typing import Callable, Mapping


class WakeAdapterUnavailable(ValueError):
    pass


def create_planner_wake_factory(
    builders: Mapping[str, Callable[[], object]] | None = None,
) -> Callable[[str], object]:
    configured = dict(builders or {})

    def build(tool: str) -> object:
        builder = configured.get(tool)
        if builder is None:
            raise WakeAdapterUnavailable(f"Planner wake adapter is unavailable for {tool}")
        return builder()

    return build
