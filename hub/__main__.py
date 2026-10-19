"""Usage: python -m hub demo"""
import json
import sys
import tempfile
from pathlib import Path

from . import fakes
from .auth import TokenClient
from .sync import run

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] != "demo":
        sys.exit("usage: python -m hub demo")
    world = fakes.World(fakes.make_tasks(), fail_first=2, throttle_first=1)
    server, url = fakes.start(world)
    tmp = Path(tempfile.mkdtemp())
    tok = TokenClient(url + "/token", "demo", "secret")
    args = (url, url, tok, tok, str(tmp / "state.json"), str(tmp / "dead.jsonl"))
    print("first run :", run(*args))
    print("second run:", run(*args))
    print("dead letter sample:", open(tmp / "dead.jsonl").readline().strip())
    server.shutdown()
