"""Thin async Spotify Web API client.

Handles app-token injection (or a passed-through user token), 429 rate-limit backoff
honoring `Retry-After`, and a one-shot token refresh on 401. Endpoint-specific logic
lives in tools.py; this client only does transport.
"""

import asyncio

import httpx

from .auth import TokenCache

API_BASE = "https://api.spotify.com/v1"
_MAX_RETRY_SLEEP = 10.0


class SpotifyClient:
    def __init__(
        self, client_id: str, client_secret: str, *, max_retries: int = 3
    ) -> None:
        self._http = httpx.AsyncClient(timeout=15.0)
        self._tokens = TokenCache(client_id, client_secret)
        self._max_retries = max_retries

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
        user_token: str | None = None,
    ) -> dict:
        url = f"{API_BASE}{path}"
        last_resp: httpx.Response | None = None

        for attempt in range(self._max_retries + 1):
            token = user_token or await self._tokens.get_token(self._http)
            resp = await self._http.request(
                method,
                url,
                params=params,
                json=json,
                headers={"Authorization": f"Bearer {token}"},
            )
            last_resp = resp

            if resp.status_code == 429 and attempt < self._max_retries:
                retry_after = float(resp.headers.get("Retry-After", "1"))
                await asyncio.sleep(min(retry_after, _MAX_RETRY_SLEEP))
                continue

            # App token expired/revoked: drop it and retry once with a fresh one.
            if (
                resp.status_code == 401
                and user_token is None
                and attempt < self._max_retries
            ):
                self._tokens.invalidate()
                continue

            resp.raise_for_status()
            if resp.status_code == 204 or not resp.content:
                return {}
            return resp.json()

        # Retries exhausted — raise the last response's error.
        assert last_resp is not None
        last_resp.raise_for_status()
        return {}

    async def get(
        self, path: str, *, params: dict | None = None, user_token: str | None = None
    ) -> dict:
        return await self._request("GET", path, params=params, user_token=user_token)

    async def post(
        self, path: str, *, json: dict | None = None, user_token: str | None = None
    ) -> dict:
        return await self._request("POST", path, json=json, user_token=user_token)
