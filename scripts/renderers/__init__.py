"""Renderer adapters. The boundary lives in `base`; engines implement it."""

from .base import (
    ArtifactSet,
    CapabilityReport,
    CapabilityRequirement,
    Downgrade,
    Renderer,
    RendererError,
    RendererInfo,
    RenderRequest,
    negotiate,
)

__all__ = [
    "ArtifactSet",
    "CapabilityReport",
    "CapabilityRequirement",
    "Downgrade",
    "RenderRequest",
    "Renderer",
    "RendererError",
    "RendererInfo",
    "negotiate",
]
