"""Two fake systems and a token service on local ports, for tests and the demo.
They can fail on purpose: 503 for the first calls, 429 with Retry-After, expired tokens."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


class World:
    def __init__(self, tasks, fail_first=0, throttle_first=0, token_ttl=60):
        self.tasks, self.fail_first, self.throttle_first, self.token_ttl = tasks, fail_first, throttle_first, token_ttl
        self.lines, self.keys = {}, {}
        self.target_calls = 0
        self.tokens_issued = 0
        self.valid = set()
        self.revoke_all_next = False
        self.lock = threading.Lock()


def make_handler(world):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, obj, headers=None):
            raw = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(raw)

        def _authed(self):
            tok = self.headers.get("Authorization", "").replace("Bearer ", "")
            return tok in world.valid

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return self.rfile.read(n)

        def do_POST(self):
            path = urlparse(self.path).path
            raw = self._body()
            with world.lock:
                if path == "/token":
                    world.tokens_issued += 1
                    tok = f"tok-{world.tokens_issued}"
                    world.valid.add(tok)
                    return self._send(200, {"access_token": tok, "expires_in": world.token_ttl})
                if world.revoke_all_next:
                    world.valid.clear()
                    world.revoke_all_next = False
                if not self._authed():
                    return self._send(401, {"error": "bad token"})
                world.target_calls += 1
                if world.throttle_first > 0:
                    world.throttle_first -= 1
                    return self._send(429, {"error": "slow down"}, {"Retry-After": "0.01"})
                if world.fail_first > 0:
                    world.fail_first -= 1
                    return self._send(503, {"error": "unavailable"})
                line = json.loads(raw)
                key = self.headers.get("Idempotency-Key")
                if key in world.keys:
                    return self._send(200, {"id": world.keys[key]})
                new_id = f"ERP-{len(world.lines) + 1:05d}"
                world.lines[line["external_id"]] = {**line, "id": new_id}
                world.keys[key] = new_id
                return self._send(201, {"id": new_id})

        def do_PUT(self):
            raw = self._body()
            with world.lock:
                if not self._authed():
                    return self._send(401, {"error": "bad token"})
                world.target_calls += 1
                ext = urlparse(self.path).path.rsplit("/", 1)[-1]
                if ext not in world.lines:
                    return self._send(404, {"error": "unknown"})
                world.lines[ext] = {**json.loads(raw), "id": world.lines[ext]["id"]}
                return self._send(200, {"id": world.lines[ext]["id"]})

        def do_GET(self):
            u = urlparse(self.path)
            with world.lock:
                if not self._authed():
                    return self._send(401, {"error": "bad token"})
                if u.path == "/tasks":
                    page = int(parse_qs(u.query).get("page", ["1"])[0])
                    size = 50
                    chunk = world.tasks[(page - 1) * size: page * size]
                    return self._send(200, {"items": chunk, "next": page + 1 if page * size < len(world.tasks) else None})
                if u.path == "/totals":
                    return self._send(200, {"amount_ore": sum(v["amount_ore"] for v in world.lines.values()), "lines": len(world.lines)})
                return self._send(404, {})
    return H


def start(world):
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(world))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def make_tasks(n=120, bad=6):
    tasks = []
    for i in range(n):
        tasks.append({"id": f"TASK-{i:04d}", "wbs": ["A-100", "A-200", "B-100"][i % 3], "amount_ore": 10_000 + i * 137,
                      "currency": "DKK", "booked_on": f"2026-10-{1 + i % 28:02d}", "title": f"Work package {i}"})
    defects = [{"wbs": "Z-999"}, {"currency": "USD"}, {"booked_on": "31/10/2026"}, {"amount_ore": -5}, {"wbs": ""}, {"amount_ore": 1.5}]
    for j in range(bad):
        tasks[j * 10].update(defects[j])
    return tasks
