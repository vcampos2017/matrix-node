"""The Matrix node's card library: which screens it rotates through, and for how long.

The order lives in secrets.py as one line, each card with its seconds:

    "cards": "clock:20, news, tide:8, clock:20, news, greenhouse:6, roll:8, clock:20, news, sun:6",

    clock        the moon clock (time, date, moon, moonrise/set and sunrise/set taking turns)
    news         what's new on the network: weather alerts (scrolling), a lightning strike,
                 rain now or rain coming. Each news card gets the seconds given here.
    tide         the next high or low tide, rising or falling (from Chatty: CHATTY_TIDE_STATION)
    greenhouse   temperature and soil moisture from the greenhouse node, then its CO2
                 (when it has a CO2 sensor)
    roll         roll call: a green or red dot for every node on the network
    sun          today's sunrise and sunset and the day's length (needs latitude/longitude)

A card with nothing to show right now (no news, no tide data yet...) is skipped. A
Tornado Warning always takes over the whole panel, whatever the line says. Left out,
DEFAULT below is used (the line above, with the clock at "news_every" seconds if that
older setting is there). A card without seconds gets its usual time. Names it doesn't
know are ignored.

Also here: WiFi signal bars from the signal strength (RSSI). Pure Python, tested on a
computer.
"""

DEFAULT = "clock, news, tide:8, clock, news, greenhouse:6, roll:8, clock, news, sun:6"
SECONDS = {"clock": 20, "news": 5, "tide": 8, "greenhouse": 6, "roll": 8, "sun": 6}


def parse(text=None, clock_seconds=None):
    """'clock:20, tide' -> [('clock', 20), ('tide', 8)]. Falls back to DEFAULT."""
    out = _parse(text if text else DEFAULT, clock_seconds)
    return out or _parse(DEFAULT, clock_seconds)


def _parse(text, clock_seconds):
    out = []
    for item in str(text).replace(";", ",").split(","):
        name, _, secs = item.strip().lower().partition(":")
        name = name.strip()
        if name not in SECONDS:
            if name:
                print("Unknown card in 'cards':", name)
            continue
        try:
            seconds = float(secs) if secs.strip() else None
        except ValueError:
            seconds = None
        if seconds is None:
            seconds = clock_seconds if (name == "clock" and clock_seconds) else SECONDS[name]
        out.append((name, max(2.0, min(seconds, 3600.0))))
    return out


class Deck:
    """Steps through the line of cards, skipping the ones with nothing to show."""

    def __init__(self, entries):
        self.entries = entries or parse()
        self.i = -1

    def next(self, make):
        """make(name, seconds) -> something to show, or None to skip it.
        Returns (name, seconds, thing). The clock is always there to fall back on."""
        for _ in range(len(self.entries)):
            self.i = (self.i + 1) % len(self.entries)
            name, seconds = self.entries[self.i]
            thing = make(name, seconds)
            if thing is not None:
                return name, seconds, thing
        return "clock", SECONDS["clock"], True


def bars(rssi):
    """WiFi signal (dBm) -> 0..4 bars, like a phone. None = not connected."""
    if rssi is None or rssi >= 0:          # the WiFi chip says 0 when it isn't joined
        return None
    for limit, n in ((-55, 4), (-67, 3), (-75, 2), (-85, 1)):
        if rssi >= limit:
            return n
    return 0


def sun_card(rise_hm, set_hm, day_seconds, seconds=6):
    """Sunrise, sunset and the day's length: ['7:01A', '5:24P', '10h23']."""
    if not rise_hm or not set_hm:
        return None
    lines = [_fit(rise_hm), _fit(set_hm)]
    colors = [0xFFC000, 0xFF5000, 0x808080]
    if day_seconds:
        mins = int(day_seconds // 60)
        lines.append(str(mins // 60) + "h" + "{:02d}".format(mins % 60))
    return {"icon": "sun", "color": 0xFFC000, "lines": lines, "colors": colors,
            "scroll": None, "seconds": seconds}


def _fit(hm):
    """(15, 5) -> '3:05P', in five characters at most."""
    h, m = hm
    text = str(h % 12 or 12) + ":" + "{:02d}".format(m) + ("A" if h < 12 else "P")
    return text if len(text) <= 5 else text[:-1]
