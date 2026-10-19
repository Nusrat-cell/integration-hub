"""Verify a signed inbound webhook on the raw body, with a time window against replays."""
import hashlib
import hmac
import time


def sign(secret, raw_body, timestamp):
    return hmac.new(secret.encode(), f"{timestamp}.".encode() + raw_body, hashlib.sha256).hexdigest()


def verify(secret, raw_body, timestamp, signature, now=None, tolerance=300):
    now = time.time() if now is None else now
    if abs(now - int(timestamp)) > tolerance:
        return False
    return hmac.compare_digest(sign(secret, raw_body, timestamp), signature)
