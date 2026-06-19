"""App-level (Client Credentials) token management.

Phase 1 uses only the Client Credentials flow: one app token, no user login. The token is
cached in memory and refreshed shortly before it expires. Phase 2 will add per-user tokens,
which are passed straight through to the API client (see SpotifyClient.user_token handling)
and never go through this cache.
"""

import base64
import time

import httpx

TOKEN_URL = "https://accounts.spotify.com/api/token"
_REFRESH_SKEW_SECONDS = 30


class TokenCache:
    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None
        self._expires_at: float = 0.0

    def invalidate(self) -> None:
        self._token = None
        self._expires_at = 0.0

    async def get_token(self, http: httpx.AsyncClient) -> str:
        if self._token and time.monotonic() < self._expires_at - _REFRESH_SKEW_SECONDS:
            return self._token

        basic = base64.b64encode(
            f"{self._client_id}:{self._client_secret}".encode()
        ).decode()
        resp = await http.post(
            TOKEN_URL,
            data={"grant_type": "client_credentials"},
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._expires_at = time.monotonic() + float(data.get("expires_in", 3600))
        return self._token
