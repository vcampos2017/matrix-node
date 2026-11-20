"""Text on the panel without the big text libraries (adafruit_display_text and
adafruit_bitmap_font took about 40 KB of the board's memory, more than MQTT had left).

Font: only the letters a label needs, read once from a BDF file, or the board's built-in
terminal font (it lives in flash, so it costs no memory). Label: one small 2-color bitmap
per line of text, placed like adafruit_display_text's Label (y is the middle of the line),
with the same .text / .x / .y / .color / .hidden / .bounding_box.
"""
# pylint: disable=import-error
import displayio

try:
    import bitmaptools
except ImportError:
    bitmaptools = None

METRICS = "M j'"            # the letters adafruit_display_text measures a line with


class Font:
    """{letter: (bitmap, tile_index, width, height, dx, dy, shift)} plus ascent/descent."""

    def __init__(self, glyphs):
        self.glyphs = glyphs
        self.ascent = self.descent = 0
        for ch in METRICS:
            g = self.glyph(ch)
            if g:
                self.ascent = max(self.ascent, g[3] + g[5])
                self.descent = max(self.descent, -g[5])
        if not self.ascent:
            self.ascent = max([g[3] + g[5] for g in glyphs.values()] or [8])

    def glyph(self, ch):
        return self.glyphs.get(ch)


class BuiltinFont(Font):
    """The board's terminal font (terminalio.FONT): every letter, no memory used."""

    def __init__(self, font):
        self.font = font
        Font.__init__(self, {})

    def glyph(self, ch):
        try:
            g = self.font.get_glyph(ord(ch))
        except Exception:       # pylint: disable=broad-except
            return None
        if g is None:
            return None
        return (g.bitmap, g.tile_index, g.width, g.height, g.dx, g.dy, g.shift_x)


def load_bdf(path, letters):
    """Just these letters from a BDF font file (each as its own 1-bit bitmap)."""
    want = set(ord(c) for c in letters + METRICS)
    glyphs = {}
    code = adv = box = rows = None
    with open(path, "r") as fh:
        for line in fh:
            if rows is not None:
                if line.startswith("ENDCHAR"):
                    w, h, dx, dy = box
                    bmp = displayio.Bitmap(max(w, 1), max(h, 1), 2)
                    nbits = (w + 7) // 8 * 8
                    for r, bits in enumerate(rows[:h]):
                        for c in range(w):
                            if bits >> (nbits - 1 - c) & 1:
                                bmp[c, r] = 1
                    glyphs[chr(code)] = (bmp, 0, w, h, dx, dy, adv)
                    code = rows = None
                    if len(glyphs) == len(want):
                        break
                else:
                    rows.append(int(line.strip() or "0", 16))
            elif line.startswith("ENCODING"):
                code, adv = int(line.split()[1]), None
                if code not in want:
                    code = None
            elif code is None:
                continue
            elif line.startswith("DWIDTH"):
                adv = int(line.split()[1])
            elif line.startswith("BBX"):
                box = [int(v) for v in line.split()[1:5]]
            elif line.startswith("BITMAP"):
                rows = []
                if adv is None:
                    adv = box[0]
    return Font(glyphs)


def arrows():
    """The moonrise / moonset arrows (an arrow on a bar), drawn here: 5 x 8."""
    up = ("..#..", ".###.", "#.#.#", "..#..", "..#..", "..#..", "..#..", "#####")
    glyphs = {}
    for ch, rows in (("↥", up), ("↧", tuple(reversed(up)))):
        bmp = displayio.Bitmap(5, 8, 2)
        for y, row in enumerate(rows):
            for x, v in enumerate(row):
                if v == "#":
                    bmp[x, y] = 1
        glyphs[ch] = (bmp, 0, 5, 8, 0, 0, 6)
    font = Font(glyphs)
    font.ascent = 8
    return font


class Label(displayio.Group):
    def __init__(self, font, color=0xFFFFFF, text="", x=0, y=0, background_color=None,
                 padding_left=0, padding_right=0, **_):
        super().__init__(x=x, y=y)
        self.font = font
        self.pal = displayio.Palette(2)
        self.pal[0] = background_color or 0
        if background_color is None:
            self.pal.make_transparent(0)
        self.pal[1] = color
        self.pad = (padding_left, padding_right)
        self.width = 0
        self._text = None
        self.text = text

    @property
    def color(self):
        return self.pal[1]

    @color.setter
    def color(self, value):
        self.pal[1] = value

    @property
    def bounding_box(self):
        f = self.font
        return (0, -(f.ascent - f.ascent // 2), self.width, f.ascent + f.descent)

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, text):
        text = str(text)
        if text == self._text:
            return
        self._text = text
        f = self.font
        parts = [f.glyph(ch) or f.glyph(" ") for ch in text]
        w = self.pad[0] + self.pad[1] + sum(g[6] for g in parts if g)
        h = max(f.ascent + f.descent, 1)
        while len(self):
            self.pop()
        self.width = w
        if w <= 0:
            return
        bmp = displayio.Bitmap(w, h, 2)
        x = self.pad[0]
        for g in parts:
            if g:
                _blit(bmp, g, x + g[4], f.ascent - g[3] - g[5])
                x += g[6]
        tile = displayio.TileGrid(bmp, pixel_shader=self.pal)
        tile.y = -(f.ascent - f.ascent // 2)
        self.append(tile)


def _blit(dest, g, x, y):
    src, index, w, h = g[0], g[1], g[2], g[3]
    x1 = index * w
    # clip to the label's bitmap
    left, top = max(0, -x), max(0, -y)
    right, bottom = min(w, dest.width - x), min(h, dest.height - y)
    if right <= left or bottom <= top:
        return
    if bitmaptools:
        bitmaptools.blit(dest, src, x + left, y + top, x1=x1 + left, y1=top,
                         x2=x1 + right, y2=bottom, skip_source_index=0)
        return
    for yy in range(top, bottom):
        for xx in range(left, right):
            if src[x1 + xx, yy]:
                dest[x + xx, y + yy] = 1
