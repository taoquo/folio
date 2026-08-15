from __future__ import annotations

from dataclasses import dataclass

from ..theme.folio import FolioTheme


@dataclass(frozen=True)
class ConnectorStyle:
    stroke: str
    width: float
    dash: tuple[float, ...] = ()


def resolve_connector_style(channel: str, emphasis: str, theme: FolioTheme) -> ConnectorStyle:
    # V5 accent policy: connectors signal rank with weight, not with the cinnabar accent.
    # Cinnabar stays reserved for the focal object so the accent budget (VQ103/VQ104) holds.
    if emphasis == "focal":
        return ConnectorStyle(theme.near_black, 1.8)
    if channel == "primary-flow":
        return ConnectorStyle(theme.near_black, 1.4)
    if channel == "async-flow":
        return ConnectorStyle(theme.stone, 1.0, (5, 4))
    if emphasis == "background":
        return ConnectorStyle(theme.stone, 1.0)
    return ConnectorStyle(theme.olive, 1.2)
