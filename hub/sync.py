"""Sync tasks from the source system to the ERP.

Idempotent: a state file remembers the target id and a hash of what was sent. An unchanged
task is skipped, a changed one is updated, a new one is created. Bad records go to a dead
letter file with the reason. Every record is traceable from source id to target id.
"""
import hashlib
import json
import logging

from . import http
from .mapping import ValidationError, map_task

log = logging.getLogger("hub.sync")


def _digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def fetch_all(source_url, tokens):
    items, page = [], 1
    while page:
        data = http.call("GET", f"{source_url}/tasks?page={page}", tokens)
        items += data["items"]
        page = data["next"]
    return items


def run(source_url, target_url, source_tokens, target_tokens, state_path, dead_letter_path, sleep=None):
    kw = {"sleep": sleep} if sleep else {}
    try:
        state = json.load(open(state_path))
    except FileNotFoundError:
        state = {}
    created = updated = unchanged = 0
    dead = []
    synced_amount = 0
    for task in fetch_all(source_url, source_tokens):
        try:
            line = map_task(task)
        except ValidationError as e:
            dead.append({"source_id": task.get("id"), "reason": str(e)})
            continue
        h = _digest(line)
        known = state.get(line["external_id"])
        if known and known["hash"] == h:
            unchanged += 1
        elif known:
            http.call("PUT", f"{target_url}/cost-lines/{line['external_id']}", target_tokens, body=line, **kw)
            state[line["external_id"]] = {"target_id": known["target_id"], "hash": h, "amount_ore": line["amount_ore"]}
            updated += 1
        else:
            res = http.call("POST", f"{target_url}/cost-lines", target_tokens, body=line,
                            headers={"Idempotency-Key": line["external_id"]}, **kw)
            state[line["external_id"]] = {"target_id": res["id"], "hash": h, "amount_ore": line["amount_ore"]}
            created += 1
    synced_amount = sum(v["amount_ore"] for v in state.values())
    json.dump(state, open(state_path, "w"), indent=1)
    with open(dead_letter_path, "a") as f:
        for d in dead:
            f.write(json.dumps(d) + "\n")
    target_total = http.call("GET", f"{target_url}/totals", target_tokens, **kw)["amount_ore"]
    log.info("created %s updated %s unchanged %s dead %s", created, updated, unchanged, len(dead))
    return {"created": created, "updated": updated, "unchanged": unchanged, "dead_letter": len(dead),
            "source_total_ore": synced_amount, "target_total_ore": target_total, "reconciled": synced_amount == target_total}
