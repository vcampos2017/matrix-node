"""Weather trends from Chatty (chatty/trends, her trends.py): the air pressure and which
way it's going, and the greenhouse cooling or warming.

    {"pressure_hpa": 1012.4, "pressure_3h": -3.6, "temp_f": 41.2, "temp_2h": -4.8,
     "advisories": ["pressure"], "ts": ...}

Two cards: "1012 / MB / DROP" with an arrow, and (only when the greenhouse moved 5+
degrees in 2 hours, or Chatty has a frost or cold-snap heads-up) "41F / -5F / FROST" (or "2 HRS").
A heads-up from Chatty also joins the news round. Pure Python, tested on a computer.
"""

STALE = 1800        # seconds: an older trends message is old news

ORANGE = 0xFF6000
RED = 0xFF2000
GREEN = 0x00D040
CYAN = 0x00C0FF
WHITE = 0xC0C0C0


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fresh(body, utc):
    """The trends message if it's recent enough (or there is no clock to tell yet)."""
    if not isinstance(body, dict):
        return None
    ts = _num(body.get("ts"))
    if utc and ts and utc - ts > STALE:
        return None
    return body


def _signed(n, unit):
    n = int(n + 0.5) if n >= 0 else -int(-n + 0.5)
    return ("+" if n > 0 else "") + str(n) + unit


def pressure_card(body, seconds=6):
    p, p3 = _num(body.get("pressure_hpa")), _num(body.get("pressure_3h"))
    if p is None:
        return None
    word, icon, color = "", "level", GREEN
    if p3 is not None:
        if p3 <= -6:
            word, icon, color = "FAST!", "down", RED
        elif p3 <= -3:
            word, icon, color = "DROP", "down", ORANGE
        elif p3 <= -1:
            word, icon, color = "LOWER", "down", WHITE
        elif p3 >= 3:
            word, icon, color = "RISE", "up", CYAN
        elif p3 >= 1:
            word, icon = "UP", "up"
        else:
            word = "STEDY"
    lines = [str(int(p + 0.5)), "MB"] + ([word] if word else [])
    return {"icon": icon, "color": color, "lines": lines, "colors": [WHITE, WHITE, color],
            "scroll": None, "seconds": seconds}


def temp_card(body, seconds=6):
    t, t2 = _num(body.get("temp_f")), _num(body.get("temp_2h"))
    told = body.get("advisories") or ()
    if t is None or t2 is None:
        return None
    frost, cold = "frost" in told, "cold" in told
    if not (frost or cold or abs(t2) >= 5):
        return None
    color = CYAN if t2 < 0 else ORANGE
    lines = [str(int(t + 0.5)) + "F", _signed(t2, "F")]
    if frost:
        lines.append("FROST")
    elif cold:
        lines.append("COLD!")
    else:
        lines.append("2 HRS")
    return {"icon": "down" if t2 < 0 else "up", "color": color, "lines": lines,
            "colors": [WHITE, color, WHITE if frost else color], "scroll": None,
            "seconds": seconds}


def cards(body, seconds=6):
    """Both cards that have something to show (pressure first)."""
    out = []
    if body:
        for make in (pressure_card, temp_card):
            card = make(body, seconds)
            if card:
                out.append(card)
    return out


def news(body):
    """Cards for the news round: only while Chatty has a heads-up out."""
    if not body or not body.get("advisories"):
        return []
    told = body["advisories"]
    out = []
    if "pressure" in told:
        out.append(pressure_card(body, 5))
    if "frost" in told or "cold" in told:
        out.append(temp_card(body, 5))
    return [c for c in out if c]
