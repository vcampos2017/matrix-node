"""Tides for the Matrix node: the next high or low tide, and whether it's rising or falling.

The predictions come from NOAA's free CO-OPS tides service, fetched by Chatty on her Pi
(chatty-node src/node_feed.py; the station is CHATTY_TIDE_STATION in her settings) and
posted retained on MQTT as chatty/tides: three days of high and low tides, so the card
keeps working through a day or two without news. The board itself does no web requests:
the web library doesn't fit in its memory next to MQTT.

Pure Python, no hardware: tested on a computer.
"""
import math

import chatty_clock as clock

MAX_EVENTS = 16


def from_chatty(body):
    """Chatty's chatty/tides message -> ([(utc, height, 'H' or 'L'), ...], units)."""
    if not isinstance(body, dict) or not isinstance(body.get("events"), list):
        return [], "english"
    out = []
    for item in body["events"][:MAX_EVENTS]:
        try:
            kind = str(item[2]).upper()[:1]
            if kind in ("H", "L"):
                out.append((int(item[0]), float(item[1]), kind))
        except (IndexError, ValueError, TypeError):
            continue
    out.sort()
    return out, ("metric" if body.get("units") == "metric" else "english")


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
