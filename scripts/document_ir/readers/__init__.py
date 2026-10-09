"""Readers turn serialised content into the Document IR."""

from .structured import (
    DocumentReadError,
    document_from_data,
    read,
    read_json,
    read_yaml,
)

__all__ = ["DocumentReadError", "document_from_data", "read", "read_json", "read_yaml"]
