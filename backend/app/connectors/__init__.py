"""Connector registry: maps a source's `connector` value to its implementation."""

from __future__ import annotations

from app.connectors.base import Connector, ConnectorError, ConnectorResult, RawItem
from app.connectors.rss import RssConnector
from app.core.http import PoliteHttpClient

__all__ = ["Connector", "ConnectorError", "ConnectorResult", "RawItem", "build_connectors"]


def build_connectors(http: PoliteHttpClient) -> dict[str, Connector]:
    return {"rss": RssConnector(http)}
