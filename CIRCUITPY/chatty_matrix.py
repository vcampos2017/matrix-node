"""The Matrix node: Chatty's moon clock and news panel on an Adafruit Matrix Portal M4.

Home screen: the Moon Phase Clock (time, date, the moon's picture and how much of it
is lit, and when it next rises or sets, taking turns with sunrise / sunset), now
worked out on the board itself, with WiFi bars in the moon's corner.
It rotates through a library of cards, each for its own number of seconds (the
"cards" line in secrets.py, see chatty_cards.py): the clock, the network's news
(weather alerts, lightning, rain now or coming), the tide, the greenhouse, a roll call
of the nodes, sunrise and sunset. A Tornado Warning from Chatty beats all of them:
the whole panel turns into a blinking TAKE COVER sign until the warning ends. A new
lightning strike flashes the panel with a bolt, a rain gauge tip sends out a ripple,
and while it rains soft blue drops fall over the moon.

It joins the node network like the Pi nodes: a heartbeat on
chatty/nodes/<node_name>/status every minute (last will: offline) and the moon on
chatty/nodes/<node_name>/data, both retained (with its WiFi signal, "rssi"). It
only listens to the others and never sends anyone a command. It makes no web
requests (no room for the web library next to MQTT): Chatty posts the tides
(chatty/tides) and the time (chatty/clock) for it.

Buttons: UP = next card now. DOWN = back to the clock (and no cards for 2 minutes).

Settings, in secrets.py (or settings.toml with the same names in capitals):
    ssid, password         WiFi (secrets.py only, never in the repo)
    timezone               e.g. "America/New_York" or "-07:00" (chatty_clock.py has the list)
    latitude, longitude    for moonrise / moonset (optional; stays on the board)
    mqtt_hosts             Chatty's home address(es), comma-separated
    node_name              default "matrix"
    twelve_hour            default True
    night_start, night_end default 22 and 7: text dims at night
    cards                  the card library's order and seconds (chatty_cards.py)
    news_every             (older setting) seconds of clock when "cards" isn't set

Based on MOON PHASE CLOCK for Adafruit Matrix Portal: displays current time, lunar
phase and time of next moonrise or moonset.
Written by Phil 'PaintYourDragon' Burgess for Adafruit Industries.
MIT license, all text above must be included in any redistribution.
BDF fonts from the X.Org project. (The original's startup splash images are not
part of this project and are not used.)
"""
# pylint: disable=import-error,broad-except,too-many-instance-attributes
import gc
import time

import board
from digitalio import DigitalInOut, Pull

try:
    # The MQTT library first, while the memory is still in one piece (it's big, and the
    # board can't always find room for it after the web library has been in and out).
    import adafruit_minimqtt.adafruit_minimqtt  # noqa: F401
except ImportError:
    pass

import chatty_cards as cardsmod
import chatty_clock as clock
import chatty_moon as moonmath
import chatty_news as newsmod
from chatty_bits import setting, flag, now_ms
from chatty_library import Library
from chatty_net import Net, Link, free
from chatty_panels import ClockBits, Roll, Fx
from chatty_screen import Screen, make_display, which_way_up, load_fonts

print("Free memory with the code loaded:", free())

FRAME_MS = 40              # about 25 frames a second
HEARTBEAT_S = 60
MQTT_EVERY_MS = 1000       # how often to check for messages
MQTT_EVERY_SCROLLING_MS = 4000
SYNC_EVERY_S = 6 * 3600
SYNC_RETRY_S = 1800
NIGHT_LEVEL = 0.25
QUIET_AFTER_DOWN_S = 120
RSSI_EVERY_MS = 30000
CLOCK_REDRAW_MS = 5000


class Buttons:
    def __init__(self):
        self.pins = {}
        for name in ("BUTTON_UP", "BUTTON_DOWN"):
            try:
                pin = DigitalInOut(getattr(board, name))
                pin.switch_to_input(pull=Pull.UP)
                self.pins[name] = [pin, True]
            except Exception:
                pass

    def pressed(self):
        """Names of buttons pressed since the last call."""
        out = []
        for name, entry in self.pins.items():
            up = entry[0].value
            if entry[1] and not up:
                out.append(name)
            entry[1] = up
        return out


class App(Library):
    def __init__(self, display=None, net=None):
        self.name = str(setting("node_name", "matrix"))
        self.zone = str(setting("timezone", "UTC"))
        if not clock.known(self.zone):
            print("Unknown timezone", self.zone, "- using UTC")
        self.twelve = flag(setting("twelve_hour", True))
        try:
            self.lat = float(setting("latitude"))
            self.lon = float(setting("longitude"))
        except (TypeError, ValueError):
            self.lat = self.lon = None
            print("No latitude/longitude in secrets.py: no moonrise/moonset times")
        self.night = (int(setting("night_start", 22)), int(setting("night_end", 7)))
        self.deck = cardsmod.Deck(cardsmod.parse(setting("cards"), setting("news_every")))
        self.tide_units = "english"
        self.tides = []                 # from Chatty's chatty/tides
        self.rotation = which_way_up(setting("rotation")) if display is None else 0
        self.display = display or make_display()
        try:
            self.display.rotation = self.rotation
        except Exception:
            pass
        print("Free memory with the panel:", free())
        self.screen = Screen(self.display, self.rotation, load_fonts())
        ClockBits(self.screen)
        self.roll = Roll(self.screen)
        self.fx = Fx(self.screen)
        print("Free memory with the fonts and pictures:", free())
        self.news = newsmod.News(self.name)
        self.net = net or Net(setting("ssid"), setting("password"))
        self.link = Link(self.net, self.name, self._message)

        self.buttons = Buttons()
        # time
        self.utc_base, self.utc_at = None, 0
        self.clock_from = None          # "wifi" (its time server) or "chatty" (chatty/clock)
        self.next_sync = 0
        # schedule
        t = now_ms()
        self.mode = "clock"
        self.mode_since = t
        self.until = t + 20000         # when the current card's time is up
        self.entry = "clock"           # the library card showing (news can be several)
        if self.deck.entries[0][0] == "clock":     # it starts on the clock: that's card 1
            self.deck.i = 0
            self.until = t + int(self.deck.entries[0][1] * 1000)
        self.queue = []
        self.card, self.scroll_w = None, 0
        self.flash_left = 0
        self.rssi, self.next_rssi = None, t
        self.sun_turn = False
        self.next_wifi = self.next_mqtt = t
        self.wifi_gap = 15000
        self.mqtt_gap = 5000
        self.next_loop = t
        self.next_beat = t
        self.next_clock = 0
        self.next_gc = t
        self.frame_no = 0
        self.rise_cache = {}
        self.sun_cache = {}
        self.moon = None

    # -- time

    def utc(self):
        if self.utc_base is None:
            return None
        return self.utc_base + (now_ms() - self.utc_at) // 1000

    def local_hm(self, utc):
        p = clock.parts(utc + clock.offset(self.zone, utc))
        return p[3], p[4]

    def sync(self):
        t = self.net.utc_now()
        if t:
            self.utc_base, self.utc_at, self.clock_from = t, now_ms(), "wifi"
            self.next_sync = now_ms() + SYNC_EVERY_S * 1000
            print("Clock set (UTC):", clock.parts(t)[:6])
            self.next_clock = 0
            return True
        self.next_sync = now_ms() + SYNC_RETRY_S * 1000
        if self.clock_from == "wifi":
            self.clock_from = None          # old now: Chatty's clock may correct it
        return False

    def moon_now(self, utc):
        phase, lit = moonmath.illumination(utc)
        out = {"phase": phase, "lit": lit, "name": moonmath.name(phase)}
        if self.lat is not None:
            days = []
            midnight = clock.local_midnight(self.zone, utc)
            for start in (midnight, midnight + 86400):
                if start not in self.rise_cache:
                    if len(self.rise_cache) > 3:
                        self.rise_cache = {}
                    self.rise_cache[start] = moonmath.rise_set(start, self.lat, self.lon)
                days.append(self.rise_cache[start])
            when, kind = moonmath.next_event(utc, days)
            if when:
                out["next"], out["next_ts"] = kind, when
                out["next_local"] = self.local_hm(when)
        return out

    def is_night(self, utc):
        if utc is None:
            return False
        hour = self.local_hm(utc)[0]
        start, end = self.night
        return hour >= start or hour < end if start > end else start <= hour < end

    # -- network news

    def heartbeat(self):
        utc = self.utc()
        body = {"state": "online", "every": HEARTBEAT_S, "title": "Matrix clock",
                "via": "lan", "screen": self.entry if self.mode != "tornado" else "tornado"}
        if utc:
            body["ts"] = utc
        if self.rssi is not None:
            body["rssi"] = self.rssi
        if not self.link.publish(self.link.status_topic(), body):
            return
        data = {"rotation": self.rotation, "screen": body["screen"]}
        if self.rssi is not None:
            data["wifi"] = {"rssi": self.rssi, "bars": cardsmod.bars(self.rssi)}
        if utc:
            data["ts"] = utc
            moon = self.moon or self.moon_now(utc)
            data["moon"] = {"phase": round(moon["phase"], 3), "lit": round(moon["lit"] * 100, 1),
                            "name": moon["name"]}
            if moon.get("next"):
                data["moon"]["next"] = moon["next"]
                data["moon"]["next_ts"] = moon["next_ts"]
        self.link.publish("chatty/nodes/" + self.name + "/data", data)

    # -- one frame

    def network(self, t):
        if not self.net.connected():
            self.link.client = None
            if t >= self.next_wifi:
                if self.net.connect():
                    self.wifi_gap = 15000
                    self.next_mqtt = t
                else:
                    self.wifi_gap = min(self.wifi_gap * 2, 300000)
                self.next_wifi = now_ms() + self.wifi_gap
            return
        if t >= self.next_sync:
            self.sync()
        if t >= self.next_rssi:
            self.rssi = self.net.rssi()
            self.next_rssi = t + RSSI_EVERY_MS
        if not self.link.client:
            if t >= self.next_mqtt:
                if self.link.connect():
                    self.mqtt_gap = 5000
                    self.next_beat = 0
                else:
                    self.mqtt_gap = min(self.mqtt_gap * 2, 120000)
                self.next_mqtt = now_ms() + self.mqtt_gap
            return
        if t >= self.next_loop:
            self.link.loop()
            gap = MQTT_EVERY_SCROLLING_MS if self.scroll_w else MQTT_EVERY_MS
            self.next_loop = now_ms() + gap
        if t >= self.next_beat:
            self.heartbeat()
            self.next_beat = now_ms() + HEARTBEAT_S * 1000

    def step(self):
        t = now_ms()
        self.frame_no += 1
        for name in self.buttons.pressed():
            if self.mode == "tornado":
                continue
            if name == "BUTTON_UP":
                self._advance()
            elif name == "BUTTON_DOWN":
                self.queue = []
                self._clock(QUIET_AFTER_DOWN_S)
        self.network(t)
        t = now_ms()
        utc = self.utc()
        mono = t // 1000
        self.screen.level = NIGHT_LEVEL if self.is_night(utc) else 1.0

        tornado = self.news.tornado(utc, mono)
        if tornado:
            self.screen.tornado(True, (t // 500) % 2 == 0)
            self.fx.stop()
            self.flash_left = 0
            if self.mode != "tornado":
                self.mode, self.mode_since = "tornado", t
                self.queue = []
                text = "Tornado warning"
                ends = tornado.get("expires_ts")
                if ends and utc:
                    h, m = self.local_hm(int(ends))
                    text += " until " + clock.hh_mm(h, m, True) + ("AM" if h < 12 else "PM")
                text += " - take shelter now"
                card = {"icon": "warn", "color": newsmod.RED, "scroll": text.upper(),
                        "lines": ["TAKE", "COVER"] if self.screen.portrait else ["TAKE COVER"],
                        "seconds": 0}
                self.card = card
                self.scroll_w = self.screen.show_card(card, urgent=True)
            elif not self.screen.step_scroll(self.scroll_w):
                self.screen.scroll.x = self.screen.w
        elif self.mode == "tornado":
            self.screen.tornado(False, False)
            self._clock(cardsmod.SECONDS["clock"])

        if self.flash_left > 0:
            self.screen.flash_on(self.flash_left in (8, 7, 4, 3))
            self.flash_left -= 1
        self.fx.step()

        if self.mode == "card":
            if self.scroll_w:
                if not self.screen.step_scroll(self.scroll_w):
                    self.scroll_w = 0
                    self._next_card()
            elif t >= self.until:
                self._next_card()
        elif self.mode == "roll":
            if t >= self.until:
                self._advance()
        elif self.mode == "clock":
            if t >= self.next_clock:
                self.draw_clock(utc)
                self.next_clock = t + CLOCK_REDRAW_MS
            self.screen.rain(self.news.raining(mono), self.frame_no % 3 == 0)
            if t >= self.until:
                self._advance()
        if self.mode != "clock":
            self.screen.rain(False, False)
        if t >= self.next_gc:
            gc.collect()
            self.next_gc = t + 2000

    def hello(self, word):
        """A status card while starting up."""
        self.screen.show_card({"icon": "heart", "color": 0xFF4080,
                               "lines": ["HI!", word], "scroll": None, "seconds": 0})

    def run(self):
        print("Free memory at start:", free())
        self.hello("WIFI")
        try:
            self.net.setup()
        except Exception as ex:
            print("WiFi chip:", repr(ex))
        print("Free memory with the WiFi chip:", free())
        if self.net.connect():
            self.hello("TIME")
            self.sync()
        self.next_clock = 0
        self.until = now_ms() + int(self.deck.entries[max(self.deck.i, 0)][1] * 1000)
        while True:
            start = now_ms()
            try:
                self.step()
            except MemoryError:
                gc.collect()
            except Exception as ex:
                print("Oops:", repr(ex))
                time.sleep(1)
            spare = FRAME_MS - (now_ms() - start)
            if spare > 0:
                time.sleep(spare / 1000)


def main():
    App().run()
