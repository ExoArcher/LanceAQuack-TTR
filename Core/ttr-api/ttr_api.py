"""Async client for Toontown Rewritten public APIs.

Thin async HTTP client wrapping aiohttp for the TTR public endpoints.
Supports: population, fieldoffices, doodles, sillymeter.
Does NOT support invasions (user constraint: no building data available).

Docs: https://github.com/toontown-rewritten/api-doc
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

log = logging.getLogger(__name__)

BASE = "https://www.toontownrewritten.com/api"

ENDPOINTS = {
    "population": f"{BASE}/population",
    "fieldoffices": f"{BASE}/fieldoffices",
    "doodles": f"{BASE}/doodles",
    "sillymeter": f"{BASE}/sillymeter",
}


class TTRApiClient:
    """Async context manager for Toontown Rewritten API access.

    Usage:
        async with TTRApiClient(user_agent) as client:
            data = await client.fetch("population")
    """

    def __init__(self, user_agent: str, timeout: float = 15.0) -> None:
        """Initialize TTR API client.

        Args:
            user_agent: User-Agent header string (from config.user_agent).
            timeout: Request timeout in seconds. Default 15.0.
        """
        self._user_agent = user_agent
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> TTRApiClient:
        """Enter async context manager; create and return session."""
        self._session = aiohttp.ClientSession(
            headers={"User-Agent": self._user_agent},
            timeout=self._timeout,
        )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        """Exit async context manager; close session."""
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def _get(self, url: str) -> dict[str, Any] | None:
        """Fetch and parse JSON from a URL.

        Args:
            url: Full URL to fetch.

        Returns:
            Parsed JSON response, or None on error (logs warning).

        Raises:
            AssertionError: If called outside async context manager.
        """
        assert self._session is not None, "Use `async with TTRApiClient(...)`"
        try:
            async with self._session.get(url) as resp:
                # TTR API returns 503 during maintenance; log and return None
                if resp.status == 503:
                    log.warning("TTR API maintenance (503) for %s", url)
                    return None
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            log.warning("TTR API request failed for %s: %s", url, e)
            return None

    async def fetch(self, endpoint: str) -> dict[str, Any] | None:
        """Fetch data from a TTR API endpoint.

        Args:
            endpoint: Endpoint key ("population", "fieldoffices", "doodles", "sillymeter").

        Returns:
            Parsed JSON response, or None on error.

        Raises:
            KeyError: If endpoint is not recognized.
        """
        if endpoint not in ENDPOINTS:
            raise KeyError(
                f"Unknown endpoint: {endpoint}. "
                f"Valid options: {', '.join(ENDPOINTS.keys())}"
            )
        url = ENDPOINTS[endpoint]
        return await self._get(url)
