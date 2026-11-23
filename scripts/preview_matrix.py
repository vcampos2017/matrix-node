#!/usr/bin/env python3
"""Draw what the Matrix node's 64x32 panel would show, as PNGs (needs Pillow).

    python3 scripts/preview_matrix.py [out_dir] [fonts_dir]

fonts_dir: a folder with the board's BDF fonts (6x10.bdf, helvR10.bdf, helvB12.bdf, as
on the CIRCUITPY drive's fonts folder) for a closer look; without them each letter is a
box. (The board's card text is its built-in terminal font; 6x10 stands in for it here.)

Runs the real screen code (CIRCUITPY) on the stand-ins in
sim, then paints each lit pixel as a round LED. Fonts are only close to
the real BDF ones and the moon is a drawn disc (the board uses its own moon pictures).
"""
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "CIRCUITPY"))
sys.path.insert(0, os.path.join(ROOT, "sim"))

from PIL import Image, ImageDraw  # noqa: E402

import fake_circuitpython as fake  # noqa: E402

fake.install({})
import chatty_bits  # noqa: E402
import chatty_cards as cards  # noqa: E402
import chatty_trend as trend  # noqa: E402
import chatty_clock as clock  # noqa: E402
import chatty_news as news  # noqa: E402
import chatty_screen  # noqa: E402
import chatty_tide as tide  # noqa: E402
from chatty_panels import ClockBits, Fx, Roll  # noqa: E402

DOT = 10


FONTS_DIR = None


def paint(screen):
    w, h = screen.w, screen.h
    canvas = Image.new("RGB", (w, h), (0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.fontmode = "1"

    def color(c):
        return ((c >> 16) & 255, (c >> 8) & 255, c & 255)

    def walk(group, ox, oy):
        if getattr(group, "hidden", False):
            return
        for item in group:
            if getattr(item, "hidden", False):
                continue
            if isinstance(item, fake.Group):
                walk(item, ox + item.x, oy + item.y)
            elif isinstance(item, fake.TileGrid):
                bmp = item.bitmap
                if isinstance(bmp, fake.OnDiskBitmap):
                    moon(draw, ox + item.x, oy + item.y, int(bmp.path[-6:-4]) / 100)
                    continue
                pal = item.pixel_shader
                for y in range(bmp.height):
                    for x in range(bmp.width):
                        v = bmp[x, y]
                        if v in pal.transparent:
                            continue
                        canvas.putpixel((ox + item.x + x, oy + item.y + y), color(pal[v])) \
                            if 0 <= ox + item.x + x < w and 0 <= oy + item.y + y < h else None

    walk(screen.root, 0, 0)
    big = Image.new("RGB", (w * DOT + 20, h * DOT + 20), (18, 18, 20))
    d = ImageDraw.Draw(big)
    for y in range(h):
        for x in range(w):
            r, g, b = canvas.getpixel((x, y))
            fill = (r, g, b) if r + g + b > 30 else (28, 28, 30)
            d.ellipse((10 + x * DOT + 1, 10 + y * DOT + 1, 10 + x * DOT + DOT - 2,
                       10 + y * DOT + DOT - 2), fill=fill)
    return big


def moon(draw, x0, y0, phase):
    k = math.cos(2 * math.pi * phase)
    for y in range(32):
        for x in range(32):
            nx, ny = (x - 15.5) / 14, (y - 15.5) / 14
            if nx * nx + ny * ny > 1:
                continue
            edge = math.sqrt(max(0, 1 - ny * ny))
            lit = nx > k * edge if phase < 0.5 else nx < -k * edge
            fill = (200, 200, 170) if lit else (25, 25, 35)
            if chatty_bits.RED[0]:                  # the red night glow tints the moon too
                c = chatty_bits.dim((fill[0] << 16) | (fill[1] << 8) | fill[2], 0.6)
                fill = (c >> 16, 0, 0)
            draw.point((x0 + x, y0 + y), fill=fill)


def main(out):
    os.makedirs(out, exist_ok=True)
    if FONTS_DIR:
        sys.modules["terminalio"].FONT = fake.BuiltinFont(os.path.join(FONTS_DIR, "6x10.bdf"))
        fonts = chatty_screen.load_fonts(FONTS_DIR)
    else:
        fonts = chatty_screen.load_fonts()
    now = clock.epoch(2026, 11, 17, 21, 5)
    hm = lambda utc: clock.parts(utc - 5 * 3600)[3:5]  # noqa: E731
    n = news.News()
    n.message("chatty/forecast/rain", json.dumps({"rain_expected": True, "chance": 70,
                                                  "starts_ts": now + 3 * 3600, "kind": "storms",
                                                  "ts": now}), now, 1)
    n.message("chatty/nodes/greenhouse/data", json.dumps(
        {"metrics": {"air_temperature_f": 68.4, "soil_moisture_band": "okay",
                     "soil_moisture_percent": 44, "soil_voltage": 1.3}}), now, 1)
    n.message("chatty/nodes/lightning/data", json.dumps(
        {"last_strike": {"ts": now - 240, "distance_mi": 6}}), now, 1)
    for name, state in (("rain", "online"), ("greenhouse", "online"), ("chatty", "online"),
                        ("wordclock", "offline"), ("lightning", "online")):
        n.message("chatty/nodes/%s/status" % name, json.dumps(
            {"state": state, "clean": name == "wordclock"}), now, 1)
    n.message("chatty/nodes/rain/status", json.dumps({"state": "offline"}), now, 1)
    tides = tide.from_chatty({"events": [[now - 9900, 0.31, "L"], [now + 17220, 1.86, "H"]]})[0]
    n.message("chatty/alerts/active", json.dumps({"alerts": [
        {"event": "Severe Thunderstorm Warning", "kind": "urgent", "expires_ts": now + 2400}],
        "ts": now}), now, 1)
    shots = []
    for rotation in (90, 0):
        tag = "portrait" if rotation == 90 else "landscape"
        s = chatty_screen.Screen(fake.FakeDisplay(), rotation, fonts)
        ClockBits(s)
        roll, fx = Roll(s), Fx(s)
        local = clock.parts(now - 5 * 3600)
        moon_info = {"phase": 0.27, "lit": 0.55, "next": "set", "next_local": (0, 41)}
        s.show_clock(local, moon_info, True, wifi=3)
        shots.append(("clock-" + tag, paint(s)))
        s.show_clock(local, moon_info, True, sun={"next": "rise", "next_local": (6, 58)}, wifi=3)
        shots.append(("clock-sun-" + tag, paint(s)))
        s.rain(True, True)
        for _ in range(20):
            s.rain(True, True)
        shots.append(("rain-" + tag, paint(s)))
        s.rain(False, False)
        library = n.cards(now, 2, hm) + [tide.card(tides, now, hm), n.greenhouse_card(2),
                                         cards.sun_card((6, 58), (17, 24), 37560)]
        for card in library:
            width = s.show_card(card)
            if width:
                for _ in range(s.w + 20):
                    s.step_scroll(width)
            shots.append(("card-" + card["icon"] + "-" + tag, paint(s)))
        trends = {"pressure_hpa": 1008.6, "pressure_3h": -4.2, "temp_f": 41.2, "temp_2h": -6.1,
                  "advisories": ["pressure", "frost"]}
        for i, card in enumerate(trend.cards(trends)):
            s.show_card(card)
            shots.append(("trend-" + ("pressure", "greenhouse")[i] + "-" + tag, paint(s)))
        roll.show(n.roll(2))
        shots.append(("card-roll-" + tag, paint(s)))
        s.show_card(n.cards(now, 2, hm)[1])
        for kind, frames in (("ripple", 5), ("bolt", 2)):
            fx.start(kind)
            for _ in range(frames):
                fx.step()
            shots.append(("fx-" + kind + "-" + tag, paint(s)))
            fx.stop()
        card = {"icon": "warn", "color": news.RED, "lines": ["TAKE", "COVER"] if rotation else
                ["TAKE COVER"], "scroll": "TORNADO WARNING UNTIL 3:45PM - TAKE SHELTER NOW",
                "seconds": 0}
        width = s.show_card(card, urgent=True)
        s.tornado(True, True)
        for _ in range(s.w + 4):
            s.step_scroll(width)
        shots.append(("tornado-" + tag, paint(s)))
        s.tornado(False, False)
        chatty_bits.RED[0] = True                    # night: the red glow
        s.level = 0.25
        s.show_clock(local, moon_info, True, wifi=3)
        shots.append(("night-red-clock-" + tag, paint(s)))
        s.show_card(n.greenhouse_card(2))
        shots.append(("night-red-greenhouse-" + tag, paint(s)))
        s.show_card(trend.cards(trends)[0])
        shots.append(("night-red-trend-" + tag, paint(s)))
        chatty_bits.RED[0] = False
        s.level = 1.0
    for name, img in shots:
        img.save(os.path.join(out, name + ".png"))
    # one sheet of the portrait ones (the way the panel stands)
    tall = [img for name, img in shots if name.endswith("portrait")]
    sheet = Image.new("RGB", (sum(i.width for i in tall) + 10 * len(tall), tall[0].height),
                      (255, 255, 255))
    x = 0
    for img in tall:
        sheet.paste(img, (x, 0))
        x += img.width + 10
    sheet.save(os.path.join(out, "matrix-sheet.png"))
    print("Wrote", len(shots) + 1, "pictures to", out)


if __name__ == "__main__":
    if len(sys.argv) > 2:
        FONTS_DIR = sys.argv[2]
    main(sys.argv[1] if len(sys.argv) > 1 else "matrix_preview")
