"""Stand-ins for CircuitPython and its libraries, so the Matrix node's code can run on
a computer: tests feed it MQTT messages and look at what would be on the panel, and
scripts/preview_matrix.py draws that to a PNG. Not copied to the board.

install(...) puts the fakes in sys.modules. A tiny MQTT "broker" (FakeBroker) keeps
retained messages and what the node published.
"""
import sys
import time
import types

# ---------------------------------------------------------------- displayio


class Group(list):
    def __init__(self, *a, x=0, y=0, scale=1, **k):
        super().__init__()
        self.hidden = False
        self.x, self.y = x, y
        self.scale = scale

    def __bool__(self):     # a Group is always "something", even when empty
        return True


class Bitmap:
    def __init__(self, w, h, colors):
        self.width, self.height = w, h
        self.px = [0] * (w * h)

    def __setitem__(self, xy, v):
        x, y = xy
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise IndexError("pixel out of range %r" % (xy,))
        self.px[y * self.width + x] = v

    def __getitem__(self, xy):
        x, y = xy
        return self.px[y * self.width + x]

    def fill(self, v):
        self.px = [v] * (self.width * self.height)


class Palette(list):
    def __init__(self, n):
        super().__init__([0] * n)
        self.transparent = set()

    def make_transparent(self, i):
        self.transparent.add(i)


class ColorConverter:
    pass


class OnDiskBitmap:
    """A pretend moon picture: a 32x32 disc, lit on the side the phase says."""
    def __init__(self, path):
        if not isinstance(path, str):
            path = getattr(path, "name", "")
        self.path = path
        self.width = self.height = 32
        self.pixel_shader = ColorConverter()


class TileGrid:
    def __init__(self, bitmap, pixel_shader=None, **k):
        self.bitmap, self.pixel_shader = bitmap, pixel_shader
        self.x = self.y = 0
        self.hidden = False


# ---------------------------------------------------------------- labels and fonts


class FakeFont:
    def __init__(self, path, w=6, h=10):
        self.path, self.w, self.h = path, w, h

    def load_glyphs(self, glyphs):
        pass


class Label:
    def __init__(self, font, color=0xFFFFFF, text="", x=0, y=0, **k):
        self.font, self.color, self.text, self.x, self.y = font, color, text, x, y
        self.hidden = False
        self.background_color = k.get("background_color")

    @property
    def bounding_box(self):
        return (0, -self.font.h // 2, self.font.w * len(self.text), self.font.h)


class BuiltinFont:
    """Like terminalio.FONT: one sheet of 6 x 12 tiles. With a BDF file (the board's
    6x10.bdf) the letters are real; without one each letter is a small box."""

    W, H = 6, 12

    def __init__(self, bdf=None):
        self.bitmap = Bitmap(self.W * 96, self.H, 2)
        drawn = set()
        if bdf:
            try:
                import chatty_text
                font = chatty_text.load_bdf(bdf, "".join(chr(c) for c in range(32, 127)))
                for ch, g in font.glyphs.items():
                    i, src = ord(ch) - 32, g[0]
                    if not 0 <= i < 96:
                        continue
                    top = 9 - g[3] - g[5]
                    for y in range(g[3]):
                        for x in range(g[2]):
                            if src[x, y] and 0 <= x + g[4] < self.W and 0 <= top + y < self.H:
                                self.bitmap[i * self.W + x + g[4], top + y] = 1
                    drawn.add(i)
            except OSError:
                pass
        for i in range(1, 96):
            if i in drawn:
                continue
            for y in range(3, 10):
                for x in range(1, 5):
                    self.bitmap[i * self.W + x, y] = 1

    def get_bounding_box(self):
        return (self.W, self.H)

    def get_glyph(self, code):
        i = code - 32 if 32 <= code < 128 else ord("?") - 32
        return types.SimpleNamespace(bitmap=self.bitmap, tile_index=i, width=self.W,
                                     height=self.H, dx=0, dy=0, shift_x=self.W, shift_y=0)


def load_font(path):
    if "helvB12" in path:
        return FakeFont(path, 8, 12)
    if "helvR10" in path:
        return FakeFont(path, 5, 10)
    return FakeFont(path, 6, 10)


# ---------------------------------------------------------------- MQTT


class FakeBroker:
    def __init__(self):
        self.retained = {}
        self.published = []
        self.reachable = {"192.168.1.50"}
        self.clients = []

    def post(self, topic, body, retain=True):
        import json
        text = body if isinstance(body, str) else json.dumps(body)
        if retain:
            self.retained[topic] = text
        for c in self.clients:
            c.inbox.append((topic, text))

    def last(self, topic):
        import json
        for t, text, _ in reversed(self.published):
            if t == topic:
                return json.loads(text)
        return None


BROKER = FakeBroker()


def _matches(pattern, topic):
    p, t = pattern.split("/"), topic.split("/")
    if len(p) != len(t):
        return False
    return all(a == "+" or a == b for a, b in zip(p, t))


class MQTT:
    def __init__(self, broker=None, port=1883, client_id="", **kw):
        self.broker, self.kw = broker, kw
        self.on_message = None
        self.subs, self.inbox, self.will = [], [], None

    def will_set(self, topic, payload, retain=False, qos=0):
        self.will = (topic, payload, retain)

    def connect(self):
        if self.broker not in BROKER.reachable:
            raise OSError("no answer from " + str(self.broker))
        BROKER.clients.append(self)

    def subscribe(self, topic, qos=0):
        self.subs.append(topic)
        for t, text in list(BROKER.retained.items()):
            if _matches(topic, t):
                self.inbox.append((t, text))

    def loop(self, timeout=0):
        while self.inbox:
            topic, text = self.inbox.pop(0)
            if any(_matches(s, topic) for s in self.subs) and self.on_message:
                self.on_message(self, topic, text)

    def publish(self, topic, msg, retain=False, qos=0):
        BROKER.published.append((topic, msg, retain))
        if retain:
            BROKER.retained[topic] = msg

    def disconnect(self):
        if self in BROKER.clients:
            BROKER.clients.remove(self)


# ---------------------------------------------------------------- the rest


class FakeESP:
    def __init__(self, utc):
        self.utc = utc
        self.is_connected = False
        self.rssi = -62

    def connect_AP(self, ssid, password, *a, **k):
        self.is_connected = True

    def get_time(self):
        return int(self.utc())

    def reset(self):
        pass


class FakeDisplay:
    def __init__(self):
        self.rotation = 0
        self.root_group = None
        self.width, self.height = 64, 32


class _Pin:
    value = True

    def __init__(self, *a):
        pass

    def switch_to_input(self, pull=None):
        pass


def install(secrets=None, clock_offset=0.0):
    """Put the fakes in sys.modules. clock_offset shifts time.monotonic_ns (tests use it
    to jump ahead)."""
    mods = {}

    def mod(name, **attrs):
        m = types.ModuleType(name)
        m.__dict__.update(attrs)
        mods[name] = m
        return m

    mod("displayio", Group=Group, Bitmap=Bitmap, Palette=Palette, TileGrid=TileGrid,
        OnDiskBitmap=OnDiskBitmap, ColorConverter=ColorConverter)
    mod("board", **{n: n for n in ("SCK", "MOSI", "MISO", "ESP_CS", "ESP_BUSY", "ESP_RESET",
                                    "SCL", "SDA", "BUTTON_UP", "BUTTON_DOWN", "NEOPIXEL")})
    mod("busio", SPI=lambda *a: None, I2C=lambda *a: None)
    mod("digitalio", DigitalInOut=_Pin, Pull=types.SimpleNamespace(UP=1, DOWN=2))
    nvm = bytearray(256)
    mod("microcontroller", nvm=nvm, cpu=types.SimpleNamespace(uid=b"\x01\x02\x03\x04"))
    mod("terminalio", FONT=BuiltinFont())
    mod("adafruit_bitmap_font")
    mod("adafruit_bitmap_font.bitmap_font", load_font=load_font)
    mods["adafruit_bitmap_font"].bitmap_font = mods["adafruit_bitmap_font.bitmap_font"]
    mod("adafruit_display_text")
    mod("adafruit_display_text.label", Label=Label)
    mod("adafruit_display_text.bitmap_label", Label=Label)
    mods["adafruit_display_text"].label = mods["adafruit_display_text.label"]
    mods["adafruit_display_text"].bitmap_label = mods["adafruit_display_text.bitmap_label"]
    mod("adafruit_minimqtt")
    mod("adafruit_minimqtt.adafruit_minimqtt", MQTT=MQTT)
    mods["adafruit_minimqtt"].adafruit_minimqtt = mods["adafruit_minimqtt.adafruit_minimqtt"]
    mod("adafruit_connection_manager", get_radio_socketpool=lambda esp: object(),
        get_radio_ssl_context=lambda esp: object())
    sys.modules.update(mods)
    sm = sys.modules
    sm.pop("secrets", None)
    if secrets is not None:
        sm["secrets"] = types.ModuleType("secrets")
        sm["secrets"].secrets = dict(secrets)
    for name in ("chatty_bits", "chatty_net", "chatty_screen", "chatty_panels", "chatty_matrix"):
        sm.pop(name, None)
    return mods
