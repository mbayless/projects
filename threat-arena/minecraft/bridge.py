"""Bridge: reads the threat feed and plays it out in Minecraft through RCON.

Usage: python3 minecraft/bridge.py [--source sample|sentinel] [--rate 30] [--dry-run]
       (./start runs it for you; ./start --source sentinel for real honeypot attacks)

Needs only the Python standard library. Reads RCON_PASSWORD from minecraft/.env.
--dry-run prints the commands instead of sending them, so you can see exactly
what the bridge does without a server.
"""
import argparse
import os
import random
import re
import sys
import time
from collections import deque
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # so "threatfeed" imports from the project root

import arena  # noqa: E402
from rcon import Rcon, RconAuthError, RconError  # noqa: E402
from threatfeed.sample import SampleSource  # noqa: E402
from threatfeed.sentinel import SentinelSource, SourceError  # noqa: E402

TARGET = {"lat": 36.67, "lon": -78.39}  # the lab in Azure East US, same as the web map
TICK = 0.5          # seconds between march steps
SPAWN_EVERY = 4     # ticks between reading new events (every 2 seconds)
MAX_MOBS = 120      # hold new mobs back above this, so the server stays smooth
SPAWN_BATCH = 5     # most mobs summoned per spawn tick; Sentinel delivers in batches, this spreads them out


def read_env():
    env = {}
    path = HERE / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip()
    return env


def connect(host, port, password, wait=300):
    """The server takes a few minutes to start the first time; keep trying.

    Until it's ready, Docker accepts the connection and closes it at once, so a
    closed connection means "not yet". Only a wrong password stops the retries.
    """
    deadline = time.time() + wait
    while True:
        try:
            return Rcon(host, port, password)
        except (OSError, RconError) as err:
            if isinstance(err, RconAuthError) or time.time() > deadline:
                raise
            print("  waiting for the Minecraft server to accept RCON...", flush=True)
            time.sleep(5)


# Minecraft's replies when it rejects a command.
ERROR_RE = re.compile(r"Unknown or incomplete command|Incorrect argument|Expected |Invalid |<--\[HERE\]|"
                      r"Unknown (block|entity|item|effect|particle)|Can't find element")


class Checked:
    """Wraps the server: prints each kind of rejected command once, so mistakes are visible."""

    def __init__(self, server):
        self.server = server
        self.reported = set()

    def run(self, command):
        reply = self.server.run(command)
        kind = command.split(" ", 2)[:2]
        if ERROR_RE.search(reply) and str(kind) not in self.reported:
            self.reported.add(str(kind))
            print(f"  !! Minecraft rejected: {command[:160]}\n     reply: {reply[:300]}", flush=True)
        return reply

    def close(self):
        self.server.close()


class DryRun:
    def run(self, command):
        print(command)
        return "Test passed, count: 0" if command.startswith("execute if") else ""

    def close(self):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", choices=["sample", "sentinel"], default="sample",
                        help="sample (default): simulated botnets. sentinel: real honeypot attacks, via az login")
    parser.add_argument("--rate", type=int, default=30, help="sample attacks per minute (default 30)")
    parser.add_argument("--history", type=int, default=30,
                        help="sentinel only: replay the last N minutes at start (default 30)")
    parser.add_argument("--dry-run", action="store_true", help="print commands instead of sending them")
    args = parser.parse_args()

    env = read_env()
    if args.dry_run:
        server = DryRun()
    else:
        password = os.environ.get("RCON_PASSWORD") or env.get("RCON_PASSWORD")
        if not password:
            sys.exit("No RCON_PASSWORD. Run ./start first; it creates minecraft/.env.")
        print("==> Connecting to Minecraft on 127.0.0.1:25575")
        server = Checked(connect("127.0.0.1", int(env.get("RCON_PORT", 25575)), password))

    pending = deque(maxlen=500)  # events waiting for a mob; the oldest are dropped if it fills up
    if args.source == "sentinel":
        print("==> Connecting to Sentinel (az login)")
        try:
            source = SentinelSource()
            pending.extend(source.history(minutes=args.history))
        except SourceError as err:
            sys.exit(f"Couldn't read Sentinel: {err}")
        print(f"==> Replaying {len(pending)} bursts from the last {args.history} minutes, then live. "
              "Events reach Sentinel 2-5 minutes after they happen.")
    else:
        source = SampleSource(rate_per_minute=args.rate)
        print(f"==> Playing sample attacks ({args.rate}/min).")

    print("==> Building the castle")
    for cmd in arena.build_commands():
        server.run(cmd)

    rng = random.Random()
    print("==> Join 127.0.0.1 in Minecraft 1.21.4. Ctrl+C stops.")
    tick = 0
    try:
        while True:
            if tick % SPAWN_EVERY == 0:
                try:
                    pending.extend(source.tick(seconds=TICK * SPAWN_EVERY))
                except SourceError as err:
                    print(f"  (couldn't check Sentinel: {err}; trying again)", flush=True)
                reply = server.run(arena.count_command())
                found = re.search(r"count: (\d+)", reply)
                active = int(found.group(1)) if found else 0
                for _ in range(SPAWN_BATCH):
                    if not pending or active >= MAX_MOBS:
                        break
                    event = pending.popleft()
                    for cmd in arena.spawn_commands(event, TARGET, rng):
                        server.run(cmd)
                    active += 1
                    mark = "  " if event.blocked else "!!"
                    print(f"  {mark} {event.attack:<20} {event.source_ip:<16} {event.city}, {event.country}",
                          flush=True)
            if tick % 60 == 0:  # every 30 s, so players who join later can see in the dark too
                server.run("effect give @a night_vision infinite 0 true")
            for cmd in arena.move_commands():
                server.run(cmd)
            tick += 1
            if args.dry_run and tick >= 8:
                break
            time.sleep(TICK)
    except KeyboardInterrupt:
        print("\n==> Stopped. The server keeps running; ./stop shuts it down.")
    finally:
        server.close()


if __name__ == "__main__":
    main()
