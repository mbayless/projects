"""Sentinel source: real honeypot attacks, read from Microsoft Sentinel with KQL.

The honeypot (sentinel-terraform/terraform/modules/honeypot) sends every Cowrie
event to the workspace's Syslog table: facility local0, process "cowrie", and the
message is Cowrie's JSON. This source queries that table, groups events into
one-minute bursts per attacker, and adds a location with KQL's built-in
geo_info_from_ip_address().

Uses your az login session (standard library only; no Azure SDK needed).
Events reach Sentinel 2-5 minutes after they happen, so "live" runs a few minutes behind.
"""
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone

from .events import ThreatEvent

RESOURCE_GROUP = os.environ.get("SENTINEL_RG", "rg-sentinel-lab")
WORKSPACE = os.environ.get("SENTINEL_WORKSPACE", "law-sentinel-lab")
HONEYPOT_VM = os.environ.get("HONEYPOT_VM", "vm-honeypot")
POLL_SECONDS = 30   # Log Analytics doesn't change faster than this; don't query more often
# Some IPs have no known location (anycast, new ranges). Keep them, out in the mid-Atlantic.
UNKNOWN_SPOT = (0.0, -30.0)

# {since}: only rows ingested after this time. {minutes}: how far back to look at all.
QUERY = """
let since = datetime({since});
Syslog
| where TimeGenerated > ago({minutes}m)
| where Facility == "local0" and ProcessName == "cowrie"
| extend ingested = ingestion_time()
| where ingested > since
| extend e = parse_json(SyslogMessage)
| extend eventid = tostring(e.eventid), ip = tostring(e.src_ip), cmd = tostring(e.input)
| where eventid in ("cowrie.login.failed", "cowrie.login.success", "cowrie.command.input",
                    "cowrie.session.file_download")
| extend attack = case(
    eventid startswith "cowrie.login", "ssh_bruteforce",
    eventid == "cowrie.session.file_download" or cmd matches regex @"(wget|curl|tftp|ftpget)\\s", "malware_download",
    "shell_recon")
| extend failed = toint(eventid == "cowrie.login.failed")
| extend stamp = format_datetime(TimeGenerated, "yyyy-MM-dd HH:mm:ss")
| extend line = case(
    eventid startswith "cowrie.login",
        strcat(stamp, " cowrie login ", iff(failed == 1, "failed", "succeeded"),
               " [", tostring(e.username), "/", tostring(e.password), "] src=", ip),
    eventid == "cowrie.session.file_download",
        strcat(stamp, " cowrie download ", tostring(e.url), " src=", ip),
    strcat(stamp, " cowrie CMD: ", cmd, " src=", ip))
| summarize tries = count(), all_failed = min(failed), evidence = make_list(line, 4),
            ingested = max(ingested) by ip, attack, burst = bin(TimeGenerated, 1m)
| extend geo = geo_info_from_ip_address(ip)
| extend country = tostring(geo.country), city = tostring(geo.city),
         lat = todouble(geo.latitude), lon = todouble(geo.longitude)
| project burst, ip, attack, tries, all_failed, evidence, ingested, country, city, lat, lon
| order by burst asc
"""


class SourceError(Exception):
    """Something the person can fix: not signed in, no workspace, no permission."""


def _az(*args, timeout=60):
    if not shutil.which("az"):
        raise SourceError("The Azure CLI isn't installed. On a Mac: brew install azure-cli")
    p = subprocess.run(["az", *args], capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        # The Azure CLI prints a harmless Python warning on some installs; keep the real error.
        err = "\n".join(l for l in p.stderr.splitlines() if "SyntaxWarning" not in l and l.strip())
        if "az login" in err:
            raise SourceError("Not signed in to Azure. Run: az login")
        raise SourceError(err[-600:] or f"az {args[0]} failed")
    return p.stdout.strip()


def _parse_time(text):
    # Log Analytics returns e.g. 2026-11-01T19:58:00Z or with 7 decimal places.
    text = text.rstrip("Z")
    if "." in text:
        head, frac = text.split(".", 1)
        text = f"{head}.{frac[:6]}"
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


class SentinelSource:
    """Live honeypot attacks from Sentinel. Same interface as SampleSource."""

    name = "Sentinel (live)"

    def __init__(self):
        self.workspace_id = _az("monitor", "log-analytics", "workspace", "show", "-g", RESOURCE_GROUP,
                                "-n", WORKSPACE, "--query", "customerId", "-o", "tsv")
        if not self.workspace_id:
            raise SourceError(f"Workspace {WORKSPACE} not found in {RESOURCE_GROUP}.")
        self.since = "1970-01-01T00:00:00Z"
        self.last_poll = 0.0

    def query(self, kql):
        """Run KQL against the workspace. Returns a list of dicts, one per row."""
        out = _az("rest", "--method", "post",
                  "--url", f"https://api.loganalytics.io/v1/workspaces/{self.workspace_id}/query",
                  "--resource", "https://api.loganalytics.io",
                  "--body", json.dumps({"query": kql}), "-o", "json")
        table = json.loads(out)["tables"][0]
        names = [c["name"] for c in table["columns"]]
        return [dict(zip(names, row)) for row in table["rows"]]

    def _fetch(self, minutes):
        rows = self.query(QUERY.format(since=self.since, minutes=minutes))
        self.last_poll = time.time()
        events = []
        for r in rows:
            evidence = r["evidence"]
            if isinstance(evidence, str):  # dynamic columns can come back as JSON text
                evidence = json.loads(evidence)
            located = r["lat"] is not None and r["lon"] is not None
            lat, lon = (r["lat"], r["lon"]) if located else UNKNOWN_SPOT
            events.append(ThreatEvent(
                time=_parse_time(r["burst"]), attack=r["attack"], source_ip=r["ip"],
                country=r["country"] or "Unknown location", city=r["city"] or r["country"] or "Unknown location",
                lat=lat, lon=lon, target="honeypot ssh :22", count=r["tries"],
                blocked=r["all_failed"] == 1, evidence=evidence,
            ))
            self.since = max(self.since, r["ingested"])
        return events

    def history(self, minutes=15):
        """Everything from the last few minutes, so the map isn't empty when it opens."""
        return self._fetch(minutes)

    def tick(self, seconds=None):
        """New events since the last poll. Polls at most every POLL_SECONDS; returns [] in between."""
        if time.time() - self.last_poll < POLL_SECONDS:
            return []
        return self._fetch(60)


# --- The honeypot VM ---------------------------------------------------------

def honeypot_status():
    """('VM running' / 'VM deallocated' / ..., public IP) or (None, None) if there's no honeypot."""
    try:
        power = _az("vm", "get-instance-view", "-g", RESOURCE_GROUP, "-n", HONEYPOT_VM, "--query",
                    "instanceView.statuses[?starts_with(code, 'PowerState/')].displayStatus | [0]", "-o", "tsv")
        ip = _az("network", "public-ip", "show", "-g", RESOURCE_GROUP, "-n", "pip-honeypot",
                 "--query", "ipAddress", "-o", "tsv")
        return power, ip
    except SourceError:
        return None, None


def start_honeypot():
    """Start the VM after its nightly shutdown. Returns at once; it takes a minute or two."""
    _az("vm", "start", "-g", RESOURCE_GROUP, "-n", HONEYPOT_VM, "--no-wait")
