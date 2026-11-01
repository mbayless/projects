from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ThreatEvent:
    """One burst of activity from one attacker, e.g. 40 SSH logins in a minute."""

    time: datetime          # when it was seen (UTC)
    attack: str             # key into catalog.ATTACKS, e.g. "ssh_bruteforce"
    source_ip: str
    country: str
    city: str
    lat: float
    lon: float
    target: str             # what was hit, e.g. "honeypot ssh :22"
    count: int = 1          # attempts in this burst
    blocked: bool = True    # did the defence stop it?
    evidence: list[str] = field(default_factory=list)  # raw log lines, as the source wrote them
