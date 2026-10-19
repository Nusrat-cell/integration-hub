"""HTTP calls with timeout, retry with backoff, Retry-After and one token refresh on 401."""
import json
import logging
import time
import urllib.error
import urllib.request

log = logging.getLogger("hub.http")
RETRY_STATUS = {429, 500, 502, 503, 504}


def call(method, url, tokens, body=None, headers=None, retries=4, backoff=0.05, sleep=time.sleep):
    refreshed = False
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None)
        req.add_header("Authorization", "Bearer " + tokens.get())
        req.add_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 401 and not refreshed:
                tokens.get(force=True)
                refreshed = True
                log.warning("401 from %s, token refreshed", url)
                continue
            if e.code in RETRY_STATUS and attempt < retries:
                wait = float(e.headers.get("Retry-After", backoff * (2 ** attempt)))
                log.warning("status %s from %s, retry %s in %.2fs", e.code, url, attempt + 1, wait)
                sleep(wait)
                continue
            detail = e.read().decode(errors="replace")[:200]
            raise RuntimeError(f"{method} {url} failed with {e.code}: {detail}") from None
        except (urllib.error.URLError, TimeoutError):
            if attempt < retries:
                sleep(backoff * (2 ** attempt))
                continue
            raise
    raise RuntimeError("retries exhausted")
