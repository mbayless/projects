"""Threat feed: turns attack logs into simple events any visual layer can draw.

Every source (sample data today, Sentinel and the honeypot later) produces
ThreatEvent objects. Every visual layer (the web map today, Minecraft later)
reads them. Add a source or a layer without touching the other side.
"""
from .catalog import ATTACKS, Attack
from .events import ThreatEvent

__all__ = ["ATTACKS", "Attack", "ThreatEvent"]
