"""Explainable link assessment: a 0-100 score from what the sandbox observed.

Every point comes from one named observation, and each reason shown to the
user says which one. There is no hidden model. The limits are stated plainly:
the sandbox makes one anonymous visit, a page can behave differently for other
visitors (cloaking), and a low score never proves a link is safe.

    from protection.verdict import assess
    assess(sandbox_result) -> {"score", "level", "label", "reasons", "note"}
"""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import parse_qsl, urlsplit

from pipeline.classify import hostname, registrable_domain

# Points per observation. Shown on the portal's "How scoring works" page.
RULES = {
    "known_threat": (60, "A site on the redirect path is listed by URLhaus as distributing malware."),
    "clipboard_write": (40, "The page tried to put text on the clipboard (fake-CAPTCHA \"paste this command\" scams)."),
    "download_executable": (35, "The page tried to download a program or app installer."),
    "credential_form_cross_site": (30, "A password or card form sends what you type to a different site."),
    "lookalike_domain": (30, "The address imitates a well-known brand it does not belong to."),
    "download": (20, "The page tried to download a file without being asked."),
    "punycode": (20, "The address uses encoded international characters, which can imitate another name."),
    "password_insecure": (20, "The page asks for a password over an unencrypted (http) connection."),
    "card_form": (15, "The page asks for payment card details."),
    "notification_prompt": (15, "The page asked for permission to send notifications (a common scam tactic)."),
    "ip_host": (15, "The link points to a bare IP address instead of a site name."),
    "password_form": (10, "The page asks for a password."),
    "dialogs": (10, "The page opened pop-up dialog boxes."),
    "scam_wording": (10, "The page uses wording common in scams (one strong phrase, or two weaker ones)."),
    "insecure_page": (10, "The page is not encrypted (http)."),
    "cross_site_redirects": (5, "The link bounces through other sites before it lands."),
    "trackers": (5, "The page loads recognised trackers."),
    "third_parties": (5, "The page contacts several other companies' servers."),
    "offshore": (5, "Third-party servers are located outside Australia."),
    "ad_click": (5, "This is a paid ad link: the ad network records the click."),
    "click_ids": (5, "The address carries click-tracking IDs that identify this visit to the advertiser."),
    "device_prompt": (5, "The page asked for your location, camera or microphone."),
    "fingerprinting": (5, "The page read canvas or graphics details that can fingerprint a device."),
    "popups": (5, "The page tried to open new windows."),
}
LEVELS = ((60, "danger", "Dangerous"), (25, "caution", "Be careful"), (0, "low", "Low risk"))
NOTE = ("One anonymous visit by the sandbox. Pages can show different content to other visitors, "
        "so a low score is not proof that a link is safe.")

# Brand words and the registrable domains that really belong to them. A host
# that contains one of these words (or a digit-for-letter imitation of it) on
# any other registrable domain is a lookalike.
BRANDS = {
    "paypal": {"paypal.com", "paypal.me", "paypalobjects.com"},
    "apple": {"apple.com", "icloud.com"}, "icloud": {"icloud.com", "apple.com"},
    "microsoft": {"microsoft.com", "live.com", "office.com", "microsoftonline.com", "outlook.com"},
    "outlook": {"outlook.com", "live.com", "office.com", "microsoft.com"},
    "office365": {"office.com", "microsoft.com", "microsoftonline.com"},
    "google": {"google.com", "youtube.com", "gmail.com", "googleapis.com", "gstatic.com", "googleadservices.com",
               "googlesyndication.com", "googletagmanager.com", "google-analytics.com", "googleusercontent.com",
               "googlevideo.com", "googlegroups.com"},
    "gmail": {"gmail.com", "google.com"}, "youtube": {"youtube.com", "youtu.be", "youtube-nocookie.com"},
    "facebook": {"facebook.com", "fb.com", "facebook.net"}, "instagram": {"instagram.com", "cdninstagram.com"},
    "whatsapp": {"whatsapp.com", "whatsapp.net"}, "netflix": {"netflix.com"},
    "amazon": {"amazon.com", "amazon.co.uk", "amazonaws.com", "amazon.dev"}, "ebay": {"ebay.com"},
    "linkedin": {"linkedin.com"}, "dhl": {"dhl.com", "dhl.com.au"}, "fedex": {"fedex.com"},
    "auspost": {"auspost.com.au"}, "mygov": {"my.gov.au"}, "ato": {"ato.gov.au"},
    "medicare": {"servicesaustralia.gov.au", "my.gov.au"}, "centrelink": {"servicesaustralia.gov.au", "my.gov.au"},
    "linkt": {"linkt.com.au"}, "commbank": {"commbank.com.au"}, "netbank": {"commbank.com.au"},
    "westpac": {"westpac.com.au"}, "anz": {"anz.com", "anz.com.au"}, "nab": {"nab.com.au"},
    "telstra": {"telstra.com", "telstra.com.au"}, "optus": {"optus.com.au"},
    "binance": {"binance.com"}, "coinbase": {"coinbase.com"},
    "steam": {"steampowered.com", "steamcommunity.com"},
}
# Matched inside longer names too ("paypalsecure"); the others only as a whole
# word, because they are also ordinary words ("outlook", "medicare", "steam").
SUBSTRING_BRANDS = {"paypal", "microsoft", "google", "amazon", "netflix", "facebook", "instagram", "whatsapp",
                    "linkedin", "coinbase", "binance", "commbank", "westpac", "auspost", "icloud"}
_HOMOGLYPHS = (("rn", "m"), ("vv", "w"), ("0", "o"), ("1", "l"), ("3", "e"), ("4", "a"), ("5", "s"), ("7", "t"))

# Phrases scam pages use. "Strong" ones count alone; "weak" ones also appear on
# ordinary sites (the 50-site study found "gift card" on 6 retailers, "act now"
# on a government home page), so at least two of them are needed.
STRONG_PHRASES = (
    "verify your account", "confirm your identity", "account has been suspended", "account will be suspended",
    "account has been locked", "update your payment", "unpaid toll", "toll notice", "parcel could not be delivered",
    "redelivery fee", "your device is infected", "virus detected", "call support now", "you have won",
    "claim your prize", "verify you are human", "press win + r", "press windows + r", "press win+r",
)
WEAK_PHRASES = (
    "unusual activity", "suspicious activity", "payment details", "within 24 hours", "final notice", "act now",
    "gift card", "ctrl + v", "ctrl+v", "only available today",
)
SCAM_PHRASES = STRONG_PHRASES + WEAK_PHRASES
EXECUTABLE = re.compile(r"\.(apk|exe|msi|scr|bat|cmd|com|ps1|vbs|js|jar|dmg|pkg|appimage|deb|lnk|hta)$", re.I)
TRACKING_PARAMS = {
    "gclid", "gclsrc", "dclid", "gbraid", "wbraid", "fbclid", "msclkid", "ttclid",
    "twclid", "li_fat_id", "mc_eid", "_hsenc", "_hsmi", "yclid", "igshid", "epik", "s_cid",
}


def is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


def lookalike(host: str) -> str | None:
    """The brand a host imitates, if any."""
    host = hostname(host)
    if not host or is_ip(host):
        return None
    site = registrable_domain(host)
    first, _, suffix = site.partition(".")
    words = set(re.split(r"[.\-_]", host))
    normalised = first
    for fake, real in _HOMOGLYPHS:
        normalised = normalised.replace(fake, real)
    for brand, owned in BRANDS.items():
        # The brand's own sites, and its country sites (google.co.uk, amazon.de).
        if site in owned or (first == brand and len(suffix.rsplit(".", 1)[-1]) == 2):
            continue
        if brand in words or normalised == brand or (brand in SUBSTRING_BRANDS and brand in normalised):
            return brand
    return None


def scam_phrases(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", (text or "").lower())
    return [p for p in SCAM_PHRASES if p in text][:5]


def _add(reasons: list, code: str, detail: str = "", points: int | None = None):
    base, text = RULES[code]
    reasons.append({"code": code, "points": base if points is None else points,
                    "text": text + (f" {detail}" if detail else "")})


def assess(result: dict, lab_hosts: set[str] | None = None) -> dict:
    """Score a sandbox result (protection.sandbox.preview). Hosts in lab_hosts
    are the local sample sites: their bare IP and plain http are not counted."""
    if not result.get("ok"):
        return {"score": None, "level": "unknown", "label": "Not assessed", "reasons": [],
                "note": "The sandbox could not open the link, so nothing was assessed."}
    lab = {h.lower() for h in (lab_hosts or set())}
    reasons: list[dict] = []
    requested = result.get("requested_url") or ""
    final = result.get("final_url") or requested
    chain = result.get("redirect_chain") or [requested]
    host = hostname(final)
    first_host = hostname(requested)
    in_lab = host in lab or first_host in lab
    signals = set(result.get("signals") or ())

    threats = result.get("known_threat_hosts") or []
    if threats:
        _add(reasons, "known_threat", "(" + ", ".join(threats[:3]) + ")")
    if "clipboard_write" in signals:
        _add(reasons, "clipboard_write")
    downloads = result.get("downloads") or []
    executables = [d for d in downloads if EXECUTABLE.search(d)]
    if executables:
        _add(reasons, "download_executable", "(" + ", ".join(executables[:3]) + ")")
    elif downloads:
        _add(reasons, "download", "(" + ", ".join(downloads[:3]) + ")")

    for candidate in dict.fromkeys(hostname(u) for u in [requested, *chain, final]):
        brand = lookalike(candidate)
        if brand:
            _add(reasons, "lookalike_domain", f"({candidate} mentions \"{brand}\")")
            break
    if any(label.startswith("xn--") for h in (first_host, host) for label in h.split(".")):
        _add(reasons, "punycode", f"({host or first_host})")
    if not in_lab and (is_ip(host) or is_ip(first_host)):
        _add(reasons, "ip_host")

    forms = result.get("forms") or {}
    page_site = registrable_domain(final)
    other_sites = sorted({registrable_domain(a) for a in forms.get("actions", [])
                          if a and registrable_domain(a) and registrable_domain(a) != page_site})
    secure = urlsplit(final).scheme == "https"
    if (forms.get("password") or forms.get("card")) and other_sites:
        _add(reasons, "credential_form_cross_site", "(sends to " + ", ".join(other_sites[:3]) + ")")
    elif forms.get("password") and not secure and not in_lab:
        _add(reasons, "password_insecure")
    elif forms.get("password"):
        _add(reasons, "password_form")
    if forms.get("card"):
        _add(reasons, "card_form")

    if "notification_prompt" in signals:
        _add(reasons, "notification_prompt")
    if result.get("dialogs"):
        _add(reasons, "dialogs", f"({result['dialogs']})")
    phrases = result.get("scam_phrases") or []
    weak = [p for p in phrases if p in WEAK_PHRASES]
    if len(weak) < len(phrases) or len(weak) >= 2:  # any strong phrase, or two weak ones
        _add(reasons, "scam_wording", "(\"" + "\", \"".join(phrases[:3]) + "\")")
    if not secure and not in_lab:
        _add(reasons, "insecure_page")

    sites = list(dict.fromkeys(registrable_domain(u) for u in chain if registrable_domain(u)))
    if len(sites) > 1:
        hops = len(sites) - 1
        _add(reasons, "cross_site_redirects", f"({' → '.join(sites[:5])})", points=min(15, 5 * hops))
    trackers = result.get("trackers") or []
    if trackers:
        owners = list(dict.fromkeys(t.get("owner") or t.get("domain") for t in trackers))
        _add(reasons, "trackers", f"({len(trackers)}: {', '.join(str(o) for o in owners[:5])})",
             points=5 if len(trackers) <= 5 else 10 if len(trackers) <= 15 else 15)
    third = result.get("third_parties") or []
    if len(third) >= 3:
        _add(reasons, "third_parties", f"({len(third)} other sites)")
    abroad = sorted({c for c in (result.get("third_party_countries") or {}).values() if c and c != "AU"})
    if abroad:
        _add(reasons, "offshore", "(" + ", ".join(abroad[:6]) + "; an estimate, not proof of where data is stored)")
    if result.get("ad_network"):
        _add(reasons, "ad_click", f"({result['ad_network']})")
    ids = sorted({k for u in [requested, *chain, final] for k, _ in parse_qsl(urlsplit(u).query)
                  if k.lower() in TRACKING_PARAMS})
    if ids:
        _add(reasons, "click_ids", "(" + ", ".join(ids) + ")")
    if "device_prompt" in signals:
        _add(reasons, "device_prompt")
    if "fingerprinting" in signals:
        _add(reasons, "fingerprinting")
    if result.get("popups"):
        _add(reasons, "popups", f"({result['popups']})")

    reasons.sort(key=lambda r: -r["points"])
    score = min(100, sum(r["points"] for r in reasons))
    level, label = next((lv, lb) for floor, lv, lb in LEVELS if score >= floor)
    return {"score": score, "level": level, "label": label, "reasons": reasons, "note": NOTE}
