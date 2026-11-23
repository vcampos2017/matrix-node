"""The moon picture in shades of red, for the red night glow (chatty_bits.RED).

The moon pictures are BMP files that displayio shows straight from flash in their own
colors, which can't be tinted. At night this reads the same file once, row by row,
into a small 16-shade bitmap (32x32 at 4 bits = 512 bytes, plus one row buffer), so
the moon keeps its craters but glows red. Loaded only at night; daytime is unchanged.
Works for 24/32-bit color BMPs and 1/4/8-bit ones with a palette. Pure Python.
"""
import struct

SHADES = 16
MAX_PIXELS = 64 * 64


def read(f, make):
    """make(w, h) -> something with [x, y] = shade (0..15). Returns it."""
    head = f.read(54)
    if head[:2] != b"BM":
        raise ValueError("not a BMP")
    start, hsize, w, h, _, bpp, comp = struct.unpack_from("<IIiiHHI", head, 10)
    if w <= 0 or w * abs(h) > MAX_PIXELS or comp not in (0, 3) or bpp not in (1, 4, 8, 24, 32):
        raise ValueError("moon BMP not supported")
    shade = None
    if bpp <= 8:                         # the palette, as shades
        n = struct.unpack_from("<I", head, 46)[0] or (1 << bpp)
        f.seek(14 + hsize)
        raw = f.read(4 * n)
        shade = bytearray(n)
        for i in range(n):
            b, g, r = raw[4 * i], raw[4 * i + 1], raw[4 * i + 2]
            shade[i] = ((77 * r + 150 * g + 29 * b) >> 8) >> 4
    rows = abs(h)
    out = make(w, rows)
    row = bytearray(((w * bpp + 31) // 32) * 4)
    step = bpp // 8
    for r_ in range(rows):
        f.seek(start + r_ * len(row))
        f.readinto(row)
        y = rows - 1 - r_ if h > 0 else r_       # most BMPs are stored bottom-up
        for x in range(w):
            if step >= 3:
                i = x * step
                v = ((77 * row[i + 2] + 150 * row[i + 1] + 29 * row[i]) >> 8) >> 4
            else:
                if bpp == 8:
                    v = row[x]
                elif bpp == 4:
                    v = row[x >> 1] >> 4 if not x & 1 else row[x >> 1] & 15
                else:
                    v = (row[x >> 3] >> (7 - (x & 7))) & 1
                v = shade[v] if v < len(shade) else 0
            out[x, y] = v
    return out


def tile(path, displayio, dim):
    """A TileGrid of the moon in red (dim() gives red while the glow is on)."""
    with open(path, "rb") as f:
        bmp = read(f, lambda w, h: displayio.Bitmap(w, h, SHADES))
    pal = displayio.Palette(SHADES)
    for i in range(SHADES):
        pal[i] = dim(i * 17 * 0x010101, 0.6)
    return displayio.TileGrid(bmp, pixel_shader=pal)
