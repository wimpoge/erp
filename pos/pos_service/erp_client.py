"""REST client for the ERP. The POS never touches the ERP database directly."""

import threading
import time
from typing import Any

import httpx


class ErpError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(f"ERP answered {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail

    @property
    def retryable(self) -> bool:
        # Server trouble, throttling or auth may clear up; a validation error will not.
        return self.status_code >= 500 or self.status_code in (401, 403, 408, 429)


class ErpClient:
    def __init__(self, http: httpx.Client, client_id: str, client_secret: str, app_code: str):
        self.http = http
        self._credentials = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "app_code": app_code,
        }
        self._token: str | None = None
        self._token_expires = 0.0
        self._lock = threading.Lock()

    def _get_token(self, force: bool = False) -> str:
        with self._lock:
            if force or self._token is None or time.monotonic() >= self._token_expires:
                r = self.http.post("/oauth/token", json=self._credentials)
                if r.status_code != 200:
                    raise ErpError(r.status_code, r.text)
                body = r.json()
                self._token = body["access_token"]
                # Renew a little early so a token never expires mid-request.
                self._token_expires = time.monotonic() + body["expires_in"] - 30
            return self._token

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        token = self._get_token()
        r = self.http.request(method, path, headers={"Authorization": f"Bearer {token}"}, **kwargs)
        if r.status_code in (401, 403):
            # Token revoked or expired on the ERP side: fetch a new one and retry once.
            token = self._get_token(force=True)
            r = self.http.request(method, path, headers={"Authorization": f"Bearer {token}"}, **kwargs)
        if r.status_code >= 400:
            raise ErpError(r.status_code, r.text[:300])
        return r.json() if r.content else None

    def list_all(self, path: str, page_size: int = 200) -> list[dict]:
        """Follow pagination until every row of an ERP list has been read."""
        items: list[dict] = []
        page = 1
        while True:
            body = self.request("GET", path, params={"page": page, "page_size": page_size})
            items.extend(body["items"])
            if not body["items"] or len(items) >= body["total"]:
                return items
            page += 1
