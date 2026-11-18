"""More for the Matrix node's panel: the roll call card, quick effects, and the clock's
sunrise picture and WiFi bars.

Roll: a dot for every node on the network with its short name, green when it's
online, red when it went quiet, amber when it said a proper goodbye (a reboot or a
shutdown) and hasn't come back yet.

Fx: a short animation over whatever is showing. "ripple": blue rings spread out
when the rain gauge tips. "bolt": a yellow zigzag with the white flash when the
lightning node hears a strike. Kept separate from chatty_screen.py so each file
stays small enough for the board to compile.
"""
# pylint: disable=import-error
import displayio

import chatty_art as art
from chatty_bits import dim

DOT = {"on": 0x00C040, "rest": 0xC08000, "quiet": 0xFF0000}
ROW = 10
MAX_ROWS = 6


def _grid(w, h, colors=3):
    bmp = displayio.Bitmap(w, h, colors)
    pal = displayio.Palette(colors)
    pal[0] = 0
    pal.make_transparent(0)
    grid = displayio.TileGrid(bmp, pixel_shader=pal)
    grid.hidden = True
    return bmp, pal, grid


class ClockBits:
    """The sunrise / sunset picture (in the moon arrow's place when it's the sun's turn)
    and 4 WiFi bars (7 x 4 pixels) in the moon picture's free corner."""

    def __init__(self, screen):
        self.mini_bmp, self.mini_pal, self.mini = _grid(art.MINI_W, art.MINI_H)
        self.bars_bmp, self.bars_pal, self.bars = _grid(7, 4)
        self.mini_name, self.bars_now = None, -2
        screen.moon.append(self.mini)
        screen.moon.append(self.bars)
        screen.bits = self

    def sun(self, rising, x, y, level):
        """Show the picture; returns the color for the time next to it."""
        name = "sunup" if rising else "sundn"
        if name != self.mini_name:
            self.mini_bmp.fill(0)
            for px, py, v in art.pixels(name):
                self.mini_bmp[px, py] = v
            self.mini_name = name
        color = 0xFFC000 if rising else 0xFF5000
        self.mini_pal[1] = dim(color, level)
        self.mini_pal[2] = dim(0x806040, level)
        self.mini.x, self.mini.y = x, y
        self.mini.hidden = False
        return color

    def wifi(self, bars, moon_y, level):
        """bars 0..4, -1 = no WiFi, None = hide. Top right of the moon picture when it's
        at the top of the panel, bottom right when it's at the bottom."""
        if bars is None:
            self.bars.hidden = True
            return
        self.bars.x = 32 - 7                      # the moon picture is 32 wide, at x 0
        self.bars.y = moon_y if moon_y == 0 else moon_y + 28
        self.bars_pal[1] = dim(0x00A040 if bars > 1 else 0xC08000, max(level, 0.4))
        self.bars_pal[2] = 0x400000 if bars < 0 else 0x101010
        if bars != self.bars_now:
            self.bars_bmp.fill(0)
            for i in range(4):
                for y in range(3 - i, 4):
                    self.bars_bmp[i * 2, y] = 1 if i < bars else 2
            self.bars_now = bars
        self.bars.hidden = False


class Roll:
    def __init__(self, screen):
        self.screen = screen
        w, h = screen.w, screen.h
        self.group = displayio.Group()
        self.dots = displayio.Bitmap(w, h, 4)
        self.pal = displayio.Palette(4)
        self.pal[0] = 0
        self.pal.make_transparent(0)
        self.group.append(displayio.TileGrid(self.dots, pixel_shader=self.pal))
        self.labels = []
        self.group.hidden = True
        screen.root.insert(1, self.group)
        screen.roll = self.group

    def show(self, nodes):
        """nodes = [(short name, 'on' | 'rest' | 'quiet'), ...] from News.roll()."""
        s = self.screen
        s.moon.hidden = True
        s.card.hidden = True
        level = s.level
        for i, key in enumerate(("on", "rest", "quiet")):
            self.pal[i + 1] = dim(DOT[key], max(level, 0.4))
        self.dots.fill(0)
        nodes = nodes[:MAX_ROWS]
        while len(self.labels) < len(nodes):
            label = s.Label(s.fonts["text"], color=0xFFFFFF, text="    ", y=-99)
            self.labels.append(label)
            self.group.append(label)
        if s.portrait:
            cols, rows = 1, len(nodes)
        else:
            cols, rows = 2, (len(nodes) + 1) // 2
        col_w = s.w // cols
        top = (s.h - rows * ROW) // 2
        for i, label in enumerate(self.labels):
            if i >= len(nodes):
                label.y = -99
                continue
            name, state = nodes[i]
            col, row = i // rows, i % rows
            x0, y0 = col * col_w + 1, top + row * ROW
            value = ("on", "rest", "quiet").index(state) + 1 if state in DOT else 3
            for dx in range(3):
                for dy in range(3):
                    self.dots[x0 + dx, y0 + 3 + dy] = value
            label.text = name[:4]
            label.x, label.y = x0 + 5, y0 + 4
            label.color = dim(0xC0C0C0 if state == "on" else DOT.get(state, 0xFF0000), level)
        self.group.hidden = False

    def hide(self):
        self.group.hidden = True


class Fx:
    FRAMES = {"ripple": 18, "bolt": 10}

    def __init__(self, screen):
        self.screen = screen
        self.bmp = displayio.Bitmap(screen.w, screen.h, 3)
        self.pal = displayio.Palette(3)
        self.pal[0] = 0
        self.pal.make_transparent(0)
        self.grid = displayio.TileGrid(self.bmp, pixel_shader=self.pal)
        self.grid.hidden = True
        screen.root.insert(len(screen.root) - 1, self.grid)     # under the white flash
        self.kind, self.frame = None, 0

    def start(self, kind):
        if self.kind == kind and self.frame < 4:
            return                                  # already started: don't stutter
        self.kind, self.frame = kind, 0

    def stop(self):
        if self.kind:
            self.kind = None
            self.bmp.fill(0)
            self.grid.hidden = True

    def step(self):
        """One frame. False once nothing is playing."""
        if not self.kind:
            return False
        if self.frame >= self.FRAMES[self.kind]:
            self.stop()
            return False
        self.bmp.fill(0)
        level = max(self.screen.level, 0.4)
        fade = 1 - self.frame / self.FRAMES[self.kind]
        if self.kind == "ripple":
            self.pal[1] = dim(0x2080FF, level * fade)
            self.pal[2] = dim(0x103070, level * fade)
            cx, cy = self.screen.w // 2, self.screen.h // 2
            r = 1 + self.frame * 2
            self._ring(cx, cy, r, 1)
            if r > 6:
                self._ring(cx, cy, r - 6, 2)
        else:
            self.pal[1] = dim(0xFFE040, level * fade)
            self.pal[2] = dim(0xFFFFFF, level * fade)
            w, h = self.screen.w, self.screen.h
            pts = [(w * 6 // 10, 0), (w * 3 // 10, h * 45 // 100), (w * 6 // 10, h * 45 // 100),
                   (w * 3 // 10, h - 1)]
            for a, b in zip(pts, pts[1:]):
                self._line(a, b, 1)
                self._line((a[0] + 1, a[1]), (b[0] + 1, b[1]), 2)
        self.grid.hidden = False
        self.frame += 1
        return True

    def _put(self, x, y, v):
        if 0 <= x < self.bmp.width and 0 <= y < self.bmp.height:
            self.bmp[x, y] = v

    def _ring(self, cx, cy, r, v):
        """A circle outline (midpoint method, integers only)."""
        x, y, err = r, 0, 1 - r
        while x >= y:
            for px, py in ((x, y), (y, x), (-y, x), (-x, y), (-x, -y), (-y, -x), (y, -x), (x, -y)):
                self._put(cx + px, cy + py, v)
            y += 1
            if err < 0:
                err += 2 * y + 1
            else:
                x -= 1
                err += 2 * (y - x) + 1

    def _line(self, a, b, v):
        (x0, y0), (x1, y1) = a, b
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err = dx + dy
        while True:
            self._put(x0, y0, v)
            if x0 == x1 and y0 == y1:
                return
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy
