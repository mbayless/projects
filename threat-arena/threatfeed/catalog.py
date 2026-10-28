"""What each attack type is, in plain English, and how every visual layer draws it.

To add an attack type: add an Attack here, then teach a source to produce it
(see sample.py). Every layer picks it up from this table.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Attack:
    name: str
    emoji: str
    color: tuple[int, int, int]  # RGB used by the map
    severity: str                # Low, Medium, High
    mitre_id: str
    mitre_name: str
    what: str                    # what is happening
    why_bot: str                 # how automation / AI makes it work
    look_for: tuple[str, ...]    # signals in the logs
    defend: tuple[str, ...]      # what stops it
    minecraft_mob: str           # used by the Minecraft layer (step 4)

    @property
    def mitre_url(self):
        return f"https://attack.mitre.org/techniques/{self.mitre_id.replace('.', '/')}/"


ATTACKS = {
    "ssh_bruteforce": Attack(
        name="SSH brute force",
        emoji="🧟",
        color=(230, 57, 70),
        severity="Medium",
        mitre_id="T1110.001",
        mitre_name="Brute Force: Password Guessing",
        what="A bot tries username and password pairs against SSH, one after another, hoping one works.",
        why_bot="Botnets of hacked servers and routers share the work, so thousands of guesses an hour "
                "come from many IPs and no single one trips a lockout.",
        look_for=("Many failed logins from one IP in minutes",
                  "Common usernames: root, admin, ubuntu, test",
                  "The same password list tried in the same order across IPs"),
        defend=("Turn off password login; use SSH keys only",
                "Don't expose port 22 to the internet; use Azure Bastion or a VPN",
                "Block repeat offenders automatically (fail2ban, NSG rules)"),
        minecraft_mob="zombie",
    ),
    "password_spray": Attack(
        name="Password spraying",
        emoji="🌧️",
        color=(255, 159, 28),
        severity="High",
        mitre_id="T1110.003",
        mitre_name="Brute Force: Password Spraying",
        what="A bot tries one or two common passwords (Spring2026!, Welcome1) against many accounts, "
             "staying under each account's lockout limit.",
        why_bot="Automation rotates through residential proxies and spaces attempts out, so it looks like "
                "scattered, normal failures. AI tools build likely passwords from your company name and season.",
        look_for=("One password failing across many different accounts",
                  "Failures spread evenly over time and many IPs",
                  "Legacy protocols (IMAP, SMTP AUTH) that skip MFA"),
        defend=("Require MFA for every account",
                "Block legacy authentication",
                "Ban common passwords (Entra ID Password Protection)"),
        minecraft_mob="witch",
    ),
    "vuln_scan": Attack(
        name="Vulnerability scanning",
        emoji="💀",
        color=(76, 201, 240),
        severity="Low",
        mitre_id="T1595.002",
        mitre_name="Active Scanning: Vulnerability Scanning",
        what="A bot requests hundreds of known-weak paths (/.env, /wp-admin, /phpmyadmin) to find "
             "something it can break into.",
        why_bot="Scanners sweep the whole internet in hours. Anything new and public is usually probed "
                "within minutes of going online.",
        look_for=("Many 404s from one IP in seconds",
                  "Requests for files that don't exist on your site (.env, .git/config)",
                  "Scanner user agents, or none at all"),
        defend=("Put a WAF in front of web apps",
                "Never deploy secrets or .git folders to a web root",
                "Rate-limit and block IPs that hit many 404s"),
        minecraft_mob="skeleton",
    ),
    "exploit_attempt": Attack(
        name="Exploit attempt",
        emoji="💥",
        color=(157, 78, 221),
        severity="High",
        mitre_id="T1190",
        mitre_name="Exploit Public-Facing Application",
        what="A bot sends a payload aimed at a specific known bug (Log4Shell, path traversal, command "
             "injection) to run its own code on your server.",
        why_bot="Exploit code for new bugs is weaponised and mass-fired within days. AI agents can now "
                "chain a scan, a matching exploit and a retry with a variation without a human.",
        look_for=("Payload strings like ${jndi:ldap://, ../../, ;wget, |sh",
                  "Requests that follow a scan from the same IP",
                  "Unusual outbound connections from the server afterwards"),
        defend=("Patch internet-facing software first and fast",
                "WAF rules for known exploit patterns",
                "Alert on outbound connections from web servers"),
        minecraft_mob="creeper",
    ),
    "ai_crawler": Attack(
        name="AI crawler / scraper",
        emoji="🦇",
        color=(6, 214, 160),
        severity="Low",
        mitre_id="T1593",
        mitre_name="Search Open Websites/Domains",
        what="A bot downloads your pages in bulk, to train an AI model, copy content, or gather "
             "details for targeted phishing.",
        why_bot="Some crawlers identify themselves (GPTBot, ClaudeBot, CCBot); others fake a browser and "
                "rotate IPs to dodge limits and robots.txt.",
        look_for=("High request rate for real pages, not errors",
                  "AI crawler user agents, or browsers that never load images or CSS",
                  "Visits that walk the whole site map in order"),
        defend=("Set robots.txt rules for AI crawlers",
                "Rate-limit by IP and by session",
                "Bot management on your CDN or WAF"),
        minecraft_mob="phantom",
    ),
    "credential_stuffing": Attack(
        name="Credential stuffing",
        emoji="🗝️",
        color=(255, 209, 102),
        severity="High",
        mitre_id="T1110.004",
        mitre_name="Brute Force: Credential Stuffing",
        what="A bot replays username and password pairs leaked from other sites against your login page, "
             "betting people reuse passwords.",
        why_bot="Breach lists hold billions of pairs. Tools solve CAPTCHAs with AI and spread logins over "
                "proxies so each IP looks like one normal user.",
        look_for=("Many different usernames from one IP, each tried once",
                  "Real usernames with mostly-wrong passwords and a few successes",
                  "Logins with no prior page visit"),
        defend=("MFA, and check new passwords against breach lists",
                "Bot detection and CAPTCHA on login",
                "Alert on a spike in failed logins across accounts"),
        minecraft_mob="vindicator",
    ),
}
