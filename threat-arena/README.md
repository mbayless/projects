# Threat Arena

See bot attacks arrive on a live map, and learn what each one is, how a bot runs it, what it looks like in the logs, and how to stop it.

Logs tell you *what* happened. The arena shows you the *shape* of it: where attacks come from, how many, which kind, and which ones got through.

```
 sources                         threat feed                     visual layers
 ───────                         ───────────                     ─────────────
 sample data   (step 1) ──┐                                 ┌──▶ web map       (step 1)
 honeypot      (step 2) ──┼──▶  ThreatEvent + attack catalog ──┼──▶ Sentinel      (step 3)
 Sentinel KQL  (step 3) ──┘     (threatfeed/)                └──▶ Minecraft     (step 4)
```

Every source turns its logs into the same `ThreatEvent`. Every visual layer draws `ThreatEvent`s. So you can add a source or a layer without touching the other side.

## Quick start (2 minutes, no Azure needed)

You need Python 3.10 or newer (`python3 --version`). On a Mac without it: `brew install python`.

```bash
git clone https://github.com/mbayless/projects.git
cd projects/threat-arena
./run
```

The first run installs its packages into `.venv` (about a minute), then opens the arena in your browser. Stop it with `Ctrl+C`.

It starts on **sample data**: simulated botnets attacking a lab in Azure East US. The IPs are from documentation-only ranges (`192.0.2.x`, `198.51.100.x`, `203.0.113.x`), so no real address is ever shown as an attacker.

## What you're looking at

| Part | What it shows |
|---|---|
| Numbers across the top | Bursts of attacks, total attempts, attacker IPs, countries, and how many **got through** |
| Map | One arc per burst, from the attacker to your lab. Colour = attack type, thickness = number of attempts, bright = got through. Hover for details |
| Live feed | The newest bursts, as they arrive |
| Understand a threat | Pick an attack type: what it is, why it's a bot, what to look for in the logs, how to stop it, its MITRE ATT&CK technique, and the latest raw log lines |
| Sidebar | How busy the botnets are, time window, refresh speed, pause, and which attack types to show |

### The attack types

| | Attack | MITRE | In one line |
|---|---|---|---|
| 🧟 | SSH brute force | T1110.001 | Guessing SSH passwords, thousands an hour, from a botnet |
| 🌧️ | Password spraying | T1110.003 | One common password against many accounts, under the lockout limit |
| 💀 | Vulnerability scanning | T1595.002 | Probing for known-weak paths like `/.env` and `/wp-admin` |
| 💥 | Exploit attempt | T1190 | A payload aimed at a specific bug, such as Log4Shell |
| 🦇 | AI crawler / scraper | T1593 | Bulk-downloading your site for AI training or reconnaissance |
| 🗝️ | Credential stuffing | T1110.004 | Replaying leaked username and password pairs from other breaches |

## Roadmap: step by step

Each step works on its own, and each one is a good first contribution.

- [x] **Step 1: Sample data and the web map.** Runs anywhere, no cloud account.
- [ ] **Step 2: A real honeypot.** Terraform for a small, isolated Azure VM running [Cowrie](https://github.com/cowrie/cowrie) (a fake SSH server). Real bots find it within minutes. Its logs go to Sentinel. Includes a daily data cap, because a busy honeypot can send a lot of data.
- [ ] **Step 3: Live Sentinel source.** `threatfeed/sentinel.py` queries the Log Analytics workspace with KQL every few seconds and turns the rows into `ThreatEvent`s. The **Source** menu gets a "Sentinel (live)" option.
- [x] **Step 4: The Minecraft arena.** Each attacker becomes a named mob that marches on your castle from the attacker's real direction: 🧟 zombie = brute force, 💀 skeleton = scanning, 💥 creeper = exploit, 🦇 phantom = crawler. Runs on sample data now. See [minecraft/README.md](minecraft/README.md).
- [ ] **Ideas:** AI explanations of a single burst, replaying a saved attack log, a Sentinel workbook version, alerts when something gets through.

## Project layout

| Path | What it is |
|---|---|
| `run` | Starts the app. Creates `.venv` on the first run |
| `app.py` | The web map and panels (Streamlit + pydeck) |
| `threatfeed/events.py` | `ThreatEvent`: one burst of activity from one attacker |
| `threatfeed/catalog.py` | Every attack type: plain-English explanation, MITRE technique, signals, defences, colour, Minecraft mob |
| `threatfeed/sample.py` | The sample source: simulated botnet campaigns with realistic log lines |
| `minecraft/` | The Minecraft arena: server in Docker, and the bridge that turns events into mobs |

## Add on to it

**Add an attack type**
1. Add an `Attack` to `ATTACKS` in `threatfeed/catalog.py`. Fill in every field, especially `what`, `why_bot`, `look_for` and `defend`: they're what people learn from.
2. In `threatfeed/sample.py`, add it to `TARGETS` and `MIX`, and add a branch in `_evidence()` that writes realistic log lines.
3. Run `./run`. It appears on the map, in the legend and in "Understand a threat".

**Add a source** (a honeypot, a firewall, another SIEM)

Write a class with a `name`, a `tick(seconds)` method that returns new `ThreatEvent`s, and a `history(minutes)` method for the backfill when the page opens. `SampleSource` is the example to copy. Then add it to the **Source** menu in `app.py`.

**Add a visual layer**

Read `ThreatEvent`s and draw them however you like: a terminal view, a 3D globe, sound, Minecraft. Use `ATTACKS[event.attack]` for each event's colour, emoji, explanation and mob.

**Before you open a pull request**
- Run `./run` and check your change on the map and in "Understand a threat".
- Keep sample IPs in the documentation ranges, and never commit real attacker logs that include other people's personal data.
- Describe in the pull request what the change lets someone see or learn.

## Safety

- Sample mode makes no network connections except loading the map tiles.
- The honeypot in step 2 is meant to be attacked. Keep it in its own resource group and network, never put real credentials or data on it, and delete it when you're done.
- Only connect sources you're allowed to monitor.
