"""Tides for the Matrix node: the next high or low tide, and whether it's rising or falling.

The predictions come from NOAA's free CO-OPS tides API (no key, no account):
https://api.tidesandcurrents.noaa.gov . The board asks for three days of high and low
tides for one station every 6 hours, so it keeps working through a day or two without
internet. Only the station number is sent; the board's location never is.

Settings (secrets.py):
    tide_station   the NOAA station number (find one at tidesandcurrents.noaa.gov, the
                   7 digits in the station page's address). No station = no tide card.
    tide_units     "english" (feet, default) or "metric" (meters)

Pure Python, no hardware: tested on a computer.
"""
import math

import chatty_clock as clock

API = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
FETCH_EVERY = 6 * 3600
RETRY_AFTER = 15 * 60
MAX_EVENTS = 16


def clean_station(text):
    """Digits and letters only (it goes in a web address)."""
    out = "".join(ch for ch in str(text or "") if ch.isalpha() or ch.isdigit())
    return out[:12] or None


def url(station, utc, units="english"):
    """The web address for 72 hours of high/low predictions, starting yesterday (UTC)."""
    y, m, d = clock.parts(utc - 86400)[:3]
    return (API + "?product=predictions&application=chatty_matrix_node"
            + "&begin_date=" + "{:04d}{:02d}{:02d}".format(y, m, d) + "&range=72"
            + "&datum=MLLW&station=" + station + "&time_zone=gmt"
            + "&units=" + ("metric" if units == "metric" else "english")
            + "&interval=hilo&format=json")


def parse(body):
    """NOAA's answer -> [(utc, height, 'H' or 'L'), ...] oldest first ([] if it's an error)."""
    if not isinstance(body, dict) or not isinstance(body.get("predictions"), list):
        return []
    out = []
    for item in body["predictions"]:
        try:
            t = str(item["t"])                     # "2026-11-18 03:12" (UTC)
            date, hm = t.split(" ")
            y, mo, d = [int(x) for x in date.split("-")]
            hh, mm = [int(x) for x in hm.split(":")[:2]]
            kind = str(item.get("type", "")).upper()[:1]
            if kind not in ("H", "L"):
                continue
            out.append((clock.epoch(y, mo, d, hh, mm), float(item["v"]), kind))
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
    out.sort()
    return out[:MAX_EVENTS]


def now(events, utc):
    """{'next': (utc, height, kind), 'rising': bool, 'height': estimate now or None},
    or None when there is no tide ahead in the list."""
    before = None
    for event in events:
        if event[0] > utc:
            info = {"next": event, "rising": event[2] == "H", "height": None}
            if before:
                # tides follow a cosine curve between a high and a low, near enough
                span = event[0] - before[0]
                if span > 0:
                    frac = (utc - before[0]) / span
                    info["height"] = before[1] + (event[1] - before[1]) * (1 - math.cos(math.pi * frac)) / 2
            return info
        before = event
    return None


def height_text(value, units="english"):
    """1.94 -> "1.9'" (feet) or "0.6m" (meters): five characters at most."""
    text = "{:.1f}".format(value)
    if text == "-0.0":
        text = "0.0"
    return (text + ("m" if units == "metric" else "'"))[:5]


def card(events, utc, local_hm, units="english", seconds=8):
    """A tide card for the panel, or None."""
    info = now(events, utc) if utc else None
    if not info:
        return None
    when, height, kind = info["next"]
    h, m = local_hm(when)
    rising = info["rising"]
    return {"icon": "tideup" if rising else "tidedn", "color": 0x00C0FF if rising else 0x2060FF,
            "lines": ["HIGH" if kind == "H" else "LOW", clock.fit_time(h, m),
                      height_text(height, units)],
            "scroll": None, "seconds": seconds}
