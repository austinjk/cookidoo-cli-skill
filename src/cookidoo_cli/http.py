from __future__ import annotations

import socket
import ssl

import certifi
from aiohttp import TCPConnector


def cookidoo_connector() -> TCPConnector:
    """Create an IPv4 connector with normal certificate validation enabled."""
    context = ssl.create_default_context(cafile=certifi.where())
    return TCPConnector(family=socket.AF_INET, ssl=context)
