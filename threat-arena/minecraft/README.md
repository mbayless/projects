# Threat Arena in Minecraft

Walk among the attackers. Every bot attack burst becomes a named mob that appears in the real direction of the attacker and marches on your castle (the lab). Blocked attacks vanish at the wall in a puff of smoke. Attacks that got through glow red, reach the beacon, ring a bell, and are announced in chat.

```
 threat feed ──▶ bridge.py ──RCON──▶ Minecraft server (Docker) ◀── you, in Minecraft Java 1.21.4
 (sample data)   turns events         127.0.0.1:25575                127.0.0.1:25565
                 into commands
```

## What you'll see

| In the game | What it means |
|---|---|
| Castle with a beacon at the centre | Your lab in Azure East US |
| 🧟 Zombie | SSH brute force |
| 🧙 Witch | Password spraying |
| 💀 Skeleton | Vulnerability scanning |
| 💥 Creeper | Exploit attempt |
| 🦇 Phantom (flying) | AI crawler / scraper |
| 🪓 Vindicator | Credential stuffing |
| Name above each mob | Attacker IP, attack type, number of attempts in the burst |
| Glowing outline, red name | **Got through.** Reaches the beacon, rings a bell, and posts a red chat message |
| Direction a mob comes from | The real compass direction of the attacker from Virginia, along the shortest path over the globe. Red post = north, yellow = east, blue = south, green = west |
| Scoreboard on the right | Bursts per attack type, and how many got through |

Asia often appears from the north: the shortest route from Virginia to China goes over the pole.

## What you need

| | Why | Get it |
|---|---|---|
| Docker Desktop | Runs the Minecraft server, so you don't need a matching Java | https://www.docker.com/products/docker-desktop/ |
| Python 3 | Runs the bridge (standard library only, nothing to install) | `brew install python` |
| Minecraft **Java Edition** | To see the arena. Bedrock (console, phone, Windows store) can't join | https://www.minecraft.net |
| About 2 GB free RAM and 1 GB disk | The server and its download | |

## Step by step

### 1. Start Docker Desktop

Open it and wait until it says it's running.

### 2. Start the arena

```bash
cd projects/threat-arena/minecraft
./start
```

The first time, it:
1. Asks you to accept the [Minecraft EULA](https://aka.ms/MinecraftEULA). The server software needs this; answering no stops without creating anything.
2. Creates `.env` with a random RCON password. Git ignores this file.
3. Downloads and starts the server (a few minutes the first time, seconds after that).
4. Builds the castle and starts sending attacks. Each one is printed as it arrives; `!!` marks the ones that got through.

`./start --rate 60` doubles the attacks per minute. Ctrl+C stops the attacks; the server keeps running.

### 3. Join in Minecraft

1. In the Minecraft Launcher, go to **Installations > New installation**, choose version **release 1.21.4**, and save. The server runs 1.21.4, and your game must match.
2. Play that installation, then go to **Multiplayer > Direct Connection**, enter `127.0.0.1`, and join. Use the number, not `localhost`: on a Mac, `localhost` can try IPv6 first, and the server only listens on IPv4.
3. You start on the castle's south wall in creative mode. Hostile mobs ignore creative players, so you can fly among them (double-tap space) and read their names.

### 4. Stop

```bash
./stop            # stop the server; the world is kept for next time
./stop --reset    # stop it and delete the world, for a fresh start
```

## See it without Minecraft

```bash
python3 bridge.py --dry-run
```

This prints the commands the bridge would send (castle, mobs, march steps) without a server. It's the quickest way to understand or change what it does.

## How it works

| File | What it does |
|---|---|
| `start`, `stop` | Start and stop everything |
| `docker-compose.yml` | The server: Minecraft Java 1.21.4 on a flat world, creative mode, no natural mobs, RCON on. Both ports only listen on this Mac |
| `bridge.py` | Every 2 seconds, reads new events from the threat feed and summons their mobs. Every half second, moves every mob one step towards the castle and removes the ones that arrived. Caps the arena at 120 mobs |
| `arena.py` | The commands: castle, scoreboard, one `summon` per event, the march step. Change the look here |
| `rcon.py` | A small RCON client (the server's remote command interface) |

The mob for each attack type comes from `minecraft_mob` in `../threatfeed/catalog.py`, the same catalogue the web map uses.

## Add on to it

- **Change a mob:** edit `minecraft_mob` for that attack in `../threatfeed/catalog.py`.
- **Change the castle or the effects:** edit `build_commands()` or `move_commands()` in `arena.py`, then check with `python3 bridge.py --dry-run`.
- **Use real attacks:** when the honeypot and Sentinel sources exist (steps 2 and 3 in the main README), the bridge will read them the same way it reads sample data.
- **Upgrading Minecraft:** `arena.py` is written for 1.21.4. Version 1.21.5 changed how mob names are written in commands, so test with `--dry-run` and a real server before changing `VERSION` in `docker-compose.yml`.

## Safety

- Ports `25565` (game) and `25575` (RCON) only accept connections from this Mac.
- To let others on your network join, remove `127.0.0.1:` from the `25565` line only. **Never expose `25575`**: RCON runs any command on the server.
- Mobs are invulnerable, silent, can't move on their own, and can't damage blocks.
