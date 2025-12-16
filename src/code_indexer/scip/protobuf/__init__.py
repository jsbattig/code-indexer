"""SCIP protobuf Python bindings."""

from .scip_pb2 import Index, Document, Occurrence, SymbolInformation, Relationship  # type: ignore[attr-defined]

__all__ = ["Index", "Document", "Occurrence", "SymbolInformation", "Relationship"]
