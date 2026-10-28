"""Turns threat events into Minecraft commands: the castle, the mobs, the scoreboard.

The world is a flat night-time plain. Your lab is a castle at 0,0 with a beacon.
Each attack burst is a named mob that appears in the real direction of the
attacker (north = -z, east = +x) and walks to the castle. Blocked ones vanish
at the wall in a puff of smoke; ones that got through glow, reach the beacon,
and are announced in chat.

Written for Minecraft Java 1.21.4 (the version docker-compose.yml pins).
"""
import json
import math
import random

from threatfeed import ATTACKS

GROUND = -60        # standing height on a default superflat world
WALL = 7            # castle walls run from -7 to 7
SPAWN_RADIUS = 40   # where mobs appear
STEP = 0.4          # blocks a mob moves per bridge tick
FLYERS = {"phantom"}

ARENA = "tag=arena"
WALL_BOX = f"x=-{WALL + 2},y={GROUND - 4},z=-{WALL + 2},dx={2 * WALL + 4},dy=24,dz={2 * WALL + 4}"
CORE_BOX = f"x=-1.5,y={GROUND - 4},z=-1.5,dx=3,dy=24,dz=3"


def build_commands():
    """Set the rules and build the castle. Safe to run again: it rebuilds the same thing."""
    cmds = [
        # A calm, fixed night with no natural mobs, no fire and no block damage.
        "gamerule doMobSpawning false", "gamerule doDaylightCycle false", "gamerule doWeatherCycle false",
        "gamerule mobGriefing false", "gamerule doFireTick false", "gamerule announceAdvancements false",
        "gamerule logAdminCommands false", "gamerule sendCommandFeedback false",
        "time set midnight", "weather clear",
        f"kill @e[{ARENA}]",
        # Castle: four stone-brick walls (open roof, so the beacon beam shows), a gate on each
        # side, a stone floor, and a beacon for the lab.
        f"fill -{WALL} {GROUND} -{WALL} {WALL} {GROUND + 5} -{WALL} stone_bricks",
        f"fill -{WALL} {GROUND} {WALL} {WALL} {GROUND + 5} {WALL} stone_bricks",
        f"fill -{WALL} {GROUND} -{WALL} -{WALL} {GROUND + 5} {WALL} stone_bricks",
        f"fill {WALL} {GROUND} -{WALL} {WALL} {GROUND + 5} {WALL} stone_bricks",
        f"fill -{WALL - 1} {GROUND - 1} -{WALL - 1} {WALL - 1} {GROUND - 1} {WALL - 1} polished_andesite",
        f"fill -1 {GROUND} -{WALL} 1 {GROUND + 2} -{WALL} air",
        f"fill -1 {GROUND} {WALL} 1 {GROUND + 2} {WALL} air",
        f"fill -{WALL} {GROUND} -1 -{WALL} {GROUND + 2} 1 air",
        f"fill {WALL} {GROUND} -1 {WALL} {GROUND + 2} 1 air",
        f"fill -1 {GROUND - 1} -1 1 {GROUND - 1} 1 iron_block",
        f"setblock 0 {GROUND} 0 beacon",
    ]
    for x in (-WALL, WALL):
        for z in (-WALL, WALL):
            cmds.append(f"setblock {x} {GROUND + 6} {z} lantern")
    # A ring of sea lanterns where the attackers appear, and a coloured post at each compass point.
    for deg in range(0, 360, 10):
        x, z = _ring(deg, SPAWN_RADIUS + 3)
        cmds.append(f"setblock {x} {GROUND - 1} {z} sea_lantern")
    for deg, block in ((0, "red_wool"), (90, "yellow_wool"), (180, "blue_wool"), (270, "lime_wool")):
        x, z = _ring(deg, SPAWN_RADIUS + 5)
        cmds.append(f"fill {x} {GROUND} {z} {x} {GROUND + 3} {z} {block}")
    cmds += [
        f"setworldspawn 0 {GROUND + 6} {WALL}",
        "effect give @a night_vision infinite 0 true",
        # Scoreboard on the right of the screen: bursts per attack type.
        "scoreboard objectives remove arena",
        'scoreboard objectives add arena dummy {"text":"Threat Arena","color":"gold","bold":true}',
        "scoreboard objectives setdisplay sidebar arena",
    ]
    cmds += [f"scoreboard players set {score_name(k)} arena 0" for k in ATTACKS]
    cmds.append("scoreboard players set got_through arena 0")
    return cmds


def _ring(deg, radius):
    rad = math.radians(deg)
    return round(radius * math.sin(rad)), round(-radius * math.cos(rad))


def score_name(attack_key):
    """Scoreboard line for an attack type, e.g. zombie:ssh_bruteforce."""
    return f"{ATTACKS[attack_key].minecraft_mob}:{attack_key}"


def bearing(lat1, lon1, lat2, lon2):
    """Compass direction (degrees, 0 = north) from point 1 to point 2 on the globe."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return math.degrees(math.atan2(y, x)) % 360


def spawn_commands(event, target, rng=random):
    """Summon one mob for one burst, in the real direction of the attacker."""
    a = ATTACKS[event.attack]
    deg = bearing(target["lat"], target["lon"], event.lat, event.lon) + rng.uniform(-6, 6)
    radius = SPAWN_RADIUS + rng.uniform(-3, 3)
    x = round(radius * math.sin(math.radians(deg)), 1)
    z = round(-radius * math.cos(math.radians(deg)), 1)
    y = GROUND + (8 if a.minecraft_mob in FLYERS else 0)
    status = "blocked" if event.blocked else "through"
    name = json.dumps({"text": f"{event.source_ip} {a.name} x{event.count}",
                       "color": "white" if event.blocked else "red"})
    nbt = (f"NoAI:1b,Silent:1b,Invulnerable:1b,PersistenceRequired:1b,CustomNameVisible:1b,"
           f"CustomName:'{name}',Glowing:{0 if event.blocked else 1}b,Tags:[\"arena\",\"{status}\"]")
    cmds = [f"summon {a.minecraft_mob} {x} {y} {z} {{{nbt}}}",
            f"scoreboard players add {score_name(event.attack)} arena 1"]
    if not event.blocked:
        cmds += ["scoreboard players add got_through arena 1",
                 "tellraw @a " + json.dumps([{"text": "[!] ", "color": "red", "bold": True},
                                             {"text": f"{a.name} from {event.source_ip} ({event.city}, "
                                                      f"{event.country}) got through", "color": "red"}])]
    return cmds


def move_commands():
    """One step of the march: every arena mob turns to the castle and moves forward."""
    return [
        f"execute as @e[{ARENA}] at @s facing 0 ~ 0 run tp @s ^ ^ ^{STEP} ~ ~",
        # Blocked: stopped at the wall.
        f"execute as @e[{ARENA},tag=blocked,{WALL_BOX}] at @s run particle poof ~ ~1 ~ 0.3 0.5 0.3 0.02 20 force",
        f"kill @e[{ARENA},tag=blocked,{WALL_BOX}]",
        # Got through: reached the beacon.
        f"execute as @e[{ARENA},tag=through,{CORE_BOX}] at @s run particle flame ~ ~1 ~ 0.3 0.8 0.3 0.05 40 force",
        f"execute if entity @e[{ARENA},tag=through,{CORE_BOX}] run playsound block.bell.use master @a 0 {GROUND} 0 2",
        f"kill @e[{ARENA},tag=through,{CORE_BOX}]",
    ]


def count_command():
    return f"execute if entity @e[{ARENA}]"
