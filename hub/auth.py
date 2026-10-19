"""OAuth 2.0 client credentials: fetch a token, cache it, refresh before it expires."""
import json
import time
import urllib.parse
import urllib.request


class TokenClient:
    def __init__(self, token_url, client_id, client_secret, clock=time.monotonic, margin=0.5):
        self.url, self.cid, self.secret = token_url, client_id, client_secret
        self.clock, self.margin = clock, margin
        self._token, self._expires_at = None, 0.0
        self.fetches = 0

    def get(self, force=False):
        if force or self._token is None or self.clock() >= self._expires_at - self.margin:
            body = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": self.cid, "client_secret": self.secret}).encode()
            with urllib.request.urlopen(urllib.request.Request(self.url, data=body), timeout=5) as r:
                data = json.load(r)
            self._token = data["access_token"]
            self._expires_at = self.clock() + data["expires_in"]
            self.fetches += 1
        return self._token
