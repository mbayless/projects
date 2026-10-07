"""PHI / PII detectors.

Each detector finds one kind of sensitive value in text and returns matches with a start/end
offset, the matched value, a type, a category (HIPAA identifier, PII, financial, health), and a
confidence. Confidence rises when a known format checksum passes (SSN, credit card, NPI) or when
nearby words give context ("DOB:", "MRN:", "patient").

Nothing here calls the network. It is deterministic regex plus a few checksums, so a human can
see exactly why each value was flagged and confirm or reject it in the app.
"""
import re

# ---------------------------------------------------------------- helpers
def luhn_ok(number):
    digits = [int(c) for c in re.sub(r"\D", "", number)]
    if len(digits) < 12:
        return False
    s, alt = 0, False
    for d in reversed(digits):
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        s += d
        alt = not alt
    return s % 10 == 0


def npi_ok(number):
    """NPI is 10 digits, Luhn-valid after prefixing 80840."""
    n = re.sub(r"\D", "", number)
    if len(n) != 10:
        return False
    return luhn_ok("80840" + n)


# ---------------------------------------------------------------- the 18 HIPAA Safe Harbor identifiers + common PII
# name, category, regex, base confidence, optional validator, context words that raise confidence
CONTEXT = {
    "mrn": ["mrn", "medical record", "record number", "chart", "patient id"],
    "dob": ["dob", "date of birth", "birth", "born"],
    "member": ["member", "subscriber", "policy", "plan id", "group number"],
    "acct": ["account", "acct", "routing"],
    "health": ["patient", "diagnosis", "icd", "cpt", "provider", "npi", "insurance", "specimen", "admission", "discharge"],
}


def _dt(name, category, pattern, conf, validator=None, context=None, flags=re.I):
    return dict(name=name, category=category, re=re.compile(pattern, flags), conf=conf,
                validator=validator, context=context or [])


DETECTORS = [
    # --- strong, format-checked identifiers
    _dt("US Social Security Number", "HIPAA identifier",
        r"\b(?!000|666|9\d\d)\d{3}[-\s](?!00)\d{2}[-\s](?!0000)\d{4}\b", 0.9),
    _dt("Credit/Debit card", "Financial",
        r"\b(?:\d[ -]?){13,19}\b", 0.6, validator=lambda m: luhn_ok(m)),
    _dt("NPI (provider ID)", "Health",
        r"\b\d{10}\b", 0.5, validator=npi_ok, context=["npi", "provider", "rendering", "billing"]),
    _dt("Email address", "PII",
        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b", 0.95),
    _dt("US phone number", "PII",
        r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)", 0.75),
    _dt("Fax number", "HIPAA identifier",
        r"\b(?:Fax)\s*(?:No\.?|#|:)?\s*((?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})\b", 0.8),
    _dt("Street address", "HIPAA identifier",
        r"\b\d{1,6}\s+(?:[A-Z][a-zA-Z]+\s){1,4}"
        r"(?:Street|St|Avenue|Ave|Boulevard|Blvd|Road|Rd|Drive|Dr|Lane|Ln|Court|Ct|Way|Place|Pl|Terrace|Ter|Circle|Cir|Highway|Hwy)\b\.?", 0.7),
    _dt("IP address", "HIPAA identifier",
        r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b", 0.8),
    _dt("Date", "HIPAA identifier",
        r"\b(?:\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}|\d{4}[/\-]\d{1,2}[/\-]\d{1,2}|"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})\b", 0.55,
        context=CONTEXT["dob"]),
    _dt("US ZIP code", "HIPAA identifier", r"\b\d{5}(?:-\d{4})?\b", 0.4,
        context=["zip", "postal", "address", "city", "state"]),
    _dt("Medical record number (MRN)", "Health",
        r"\b(?:MRN|Medical Record(?: Number)?|Record No\.?|Chart)\s*[:#]?\s*([A-Z0-9\-]{5,12})\b", 0.85),
    _dt("Member/Policy ID", "Health",
        r"\b(?:Member|Subscriber|Policy|Plan)\s*(?:ID|No\.?|Number|#)?\s*[:#]?\s*([A-Z0-9\-]{6,15})\b", 0.7),
    _dt("Account/Routing number", "Financial",
        r"\b(?:Account|Acct|Routing)\s*(?:No\.?|Number|#)?\s*[:#]?\s*(\d{6,17})\b", 0.7),
    _dt("ICD-10 diagnosis code", "Health",
        r"\b[A-TV-Z][0-9][0-9A-Z](?:\.[0-9A-Z]{1,4})?\b", 0.45, context=CONTEXT["health"]),
    _dt("Driver's license / state ID", "HIPAA identifier",
        r"\b(?:DL|Driver'?s? Licen[cs]e|License)\s*(?:No\.?|#|:)?\s*([A-Z0-9]{6,13})\b", 0.7),
    _dt("Vehicle VIN", "HIPAA identifier", r"\b[A-HJ-NPR-Z0-9]{17}\b", 0.6, context=["vin", "vehicle"]),
    _dt("Passport number", "HIPAA identifier",
        r"\b(?:Passport)\s*(?:No\.?|#|:)?\s*([A-Z0-9]{6,9})\b", 0.75),
    _dt("URL / web address", "HIPAA identifier", r"\bhttps?://[^\s<>\"')]+", 0.6),
    _dt("Device/serial number", "HIPAA identifier",
        r"\b(?:Serial|Device|S/N)\s*(?:No\.?|#|:)?\s*([A-Z0-9\-]{5,})\b", 0.6),
    _dt("Age over 89", "HIPAA identifier",
        r"\b(?:age\s*[:#]?\s*|aged?\s+)(9\d|1[0-9]\d)\b", 0.6, context=["age", "years old", "yo"]),
]

# A short list of common first names to flag person names near health context (small on purpose; the
# human validator is the real check). Users can extend it in the app.
# Prefix is case-insensitive; the captured name stays case-sensitive so "Patient age" doesn't match.
NAME_HINTS = re.compile(
    r"\b(?i:Mr|Mrs|Ms|Dr|Patient|Name|Member|DOB for)\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b")


def _context_boost(text, start, end, words):
    if not words:
        return 0.0
    window = text[max(0, start - 40):start].lower() + " " + text[end:end + 15].lower()
    return 0.15 if any(w in window for w in words) else 0.0


def scan_text(text, source="", enabled=None):
    """Return a list of findings for a block of text.

    Each finding: source, type, category, value, start, end, confidence, context (surrounding snippet).
    """
    findings = []
    seen = set()  # (start, end) to avoid duplicate overlaps across detectors
    for d in DETECTORS:
        if enabled is not None and d["name"] not in enabled:
            continue
        for m in d["re"].finditer(text):
            value = m.group(len(m.groups())) if m.groups() else m.group(0)
            span = m.span(len(m.groups())) if m.groups() else m.span(0)
            if d["validator"] and not d["validator"](value):
                continue
            conf = d["conf"] + _context_boost(text, span[0], span[1], d["context"])
            # A format-checked value is high confidence regardless of context.
            if d["validator"]:
                conf = max(conf, 0.9)
            conf = round(min(conf, 0.99), 2)
            key = (span[0], span[1], d["name"])
            if key in seen:
                continue
            seen.add(key)
            ctx = text[max(0, span[0] - 25):span[0]] + "[" + value + "]" + text[span[1]:span[1] + 25]
            findings.append(dict(source=source, type=d["name"], category=d["category"], value=value,
                                 start=span[0], end=span[1], confidence=conf,
                                 context=re.sub(r"\s+", " ", ctx).strip()))
    # names near context
    for m in NAME_HINTS.finditer(text):
        value, span = m.group(1), m.span(1)
        key = (span[0], span[1], "Person name")
        if key in seen:
            continue
        seen.add(key)
        ctx = text[max(0, span[0] - 25):span[0]] + "[" + value + "]" + text[span[1]:span[1] + 25]
        findings.append(dict(source=source, type="Person name", category="HIPAA identifier", value=value,
                             start=span[0], end=span[1], confidence=0.6,
                             context=re.sub(r"\s+", " ", ctx).strip()))
    # keep the highest-confidence finding when two detectors claim the exact same span
    best = {}
    for f in findings:
        k = (f["start"], f["end"])
        if k not in best or f["confidence"] > best[k]["confidence"]:
            best[k] = f
    return sorted(best.values(), key=lambda f: f["start"])


ALL_TYPES = [d["name"] for d in DETECTORS] + ["Person name"]
CATEGORIES = sorted({d["category"] for d in DETECTORS})

# The 18 HIPAA Safe Harbor identifiers and the exact detector(s) covering each, so coverage is auditable.
HIPAA_18 = [
    ("1. Names", ["Person name"]),
    ("2. Geographic subdivisions (address, ZIP)", ["Street address", "US ZIP code"]),
    ("3. Dates related to an individual", ["Date"]),
    ("4. Telephone numbers", ["US phone number"]),
    ("5. Fax numbers", ["Fax number"]),
    ("6. Email addresses", ["Email address"]),
    ("7. Social Security numbers", ["US Social Security Number"]),
    ("8. Medical record numbers", ["Medical record number (MRN)"]),
    ("9. Health plan beneficiary numbers", ["Member/Policy ID"]),
    ("10. Account numbers", ["Account/Routing number"]),
    ("11. Certificate / license numbers", ["Driver's license / state ID", "Passport number"]),
    ("12. Vehicle identifiers (VIN)", ["Vehicle VIN"]),
    ("13. Device identifiers / serial numbers", ["Device/serial number"]),
    ("14. Web URLs", ["URL / web address"]),
    ("15. IP addresses", ["IP address"]),
    ("16. Biometric identifiers", []),   # not detectable from text — review source manually
    ("17. Full-face photographs", []),   # not applicable to text — review images manually
    ("18. Any other unique identifier", ["NPI (provider ID)", "ICD-10 diagnosis code", "Age over 89"]),
]


def redact(text, findings, mode="type"):
    """Return text with each finding replaced. mode: 'type' -> [US phone number], 'mask' -> ****, 'remove'."""
    for f in sorted(findings, key=lambda f: f["start"], reverse=True):
        if mode == "type":
            rep = f"[{f['type']}]"
        elif mode == "mask":
            rep = "*" * len(f["value"])
        else:
            rep = ""
        text = text[:f["start"]] + rep + text[f["end"]:]
    return text
