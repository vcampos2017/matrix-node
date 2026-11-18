"""The Matrix node's card library at work: which card comes next, building each one,
the moon clock's turns between moonrise and sunrise, Chatty's clock and tides, and what
news from the network does to the screen (a strike's bolt, a rain gauge tip's ripple).

A mixin for chatty_matrix.App, kept in its own file so each one stays small enough
for the board to compile. The order and seconds come from chatty_cards.py.
"""
# pylint: disable=import-error,no-member
import json

import chatty_cards as cardsmod
import chatty_clock as clock
import chatty_moon as moonmath
import chatty_tide as tide
from chatty_bits import now_ms


class Library:
    def sun_now(self, utc):
        """{"next": "rise" | "set", "next_local", "rise", "set" (local (h, m) of today's,
        or tomorrow's after sunset), "day": seconds of daylight}, or None."""
        if self.lat is None or utc is None:
            return None
        midnight = clock.local_midnight(self.zone, utc)
        days = []
        for start in (midnight, midnight + 86400):
            if start not in self.sun_cache:
                if len(self.sun_cache) > 3:
                    self.sun_cache = {}
                self.sun_cache[start] = moonmath.sun_rise_set(start, self.lat, self.lon)
            days.append(self.sun_cache[start])
        when, kind = moonmath.next_event(utc, days)
        if not when:
            return None                   # far north in winter or summer: no sunrise
        rise, sets = days[0]
        if sets is not None and utc >= sets:
            rise, sets = days[1]
        out = {"next": kind, "next_local": self.local_hm(when), "rise": None, "set": None,
               "day": (sets - rise) if (rise and sets and sets > rise) else None}
        if rise:
            out["rise"] = self.local_hm(rise)
        if sets:
            out["set"] = self.local_hm(sets)
        return out


    def _message(self, topic, text):
        if topic in ("chatty/clock", "chatty/tides"):
            self._chatty_feed(topic, text)
            return
        utc = self.utc()
        for event in self.news.message(topic, text, utc, now_ms() // 1000):
            if self.mode == "tornado":
                continue                       # nothing gets in the way of TAKE COVER
            if event[0] == "strike":
                self.flash_left = 8
                self.fx.start("bolt")
                bolt = [c for c in self.news.cards(utc, now_ms() // 1000, self.local_hm)
                        if c["icon"] == "bolt"][:1]
                if bolt:
                    bolt[0]["seconds"] = max(5, bolt[0]["seconds"])
                    self.queue = bolt
                    self._next_card()
            elif event[0] == "tip":
                self.fx.start("ripple")

    def _chatty_feed(self, topic, text):
        """Chatty's time (every minute) and tides (retained): the board can't fetch them."""
        try:
            body = json.loads(text)
        except (ValueError, TypeError):
            return
        if topic == "chatty/clock":
            try:
                ts = int(body.get("ts"))
            except (TypeError, ValueError, AttributeError):
                return
            # Chatty's clock unless the WiFi chip's time server set it in the last 6 hours
            if ts > 1700000000 and (self.utc_base is None or self.clock_from != "wifi"):
                if self.utc_base is None:
                    print("Clock set from Chatty (UTC):", clock.parts(ts)[:6])
                    self.next_clock = 0
                self.utc_base, self.utc_at, self.clock_from = ts, now_ms(), "chatty"
            return
        events, units = tide.from_chatty(body)
        if events:
            self.tides, self.tide_units = events, units
            print("Got", len(events), "tides from Chatty")

    # -- the card library

    def _make(self, name, seconds):
        """What a library card would show now, or None to skip it."""
        utc, mono = self.utc(), now_ms() // 1000
        if name == "clock":
            return True
        if name == "news":
            cards = self.news.cards(utc, mono, self.local_hm)
            for card in cards:
                if not card.get("scroll"):
                    card["seconds"] = seconds
            return cards or None
        if name == "tide":
            if not self.tides or not utc:
                return None
            return tide.card(self.tides, utc, self.local_hm, self.tide_units, seconds)
        if name == "greenhouse":
            card = self.news.greenhouse_card(mono)
            if card:
                card["seconds"] = seconds
            return card
        if name == "roll":
            return self.news.roll(mono) or None
        if name == "sun":
            sun = self.sun_now(utc)
            return cardsmod.sun_card(sun["rise"], sun["set"], sun["day"], seconds) if sun else None
        return None

    def _advance(self):
        """On to the next card: the rest of a news round first, then the library."""
        if self.queue:
            self._next_card()
            return
        name, seconds, thing = self.deck.next(self._make)
        self.entry = name
        t = now_ms()
        if name == "news":
            self.queue = thing
            self._next_card()
        elif name == "roll":
            self.mode, self.mode_since, self.until = "roll", t, t + int(seconds * 1000)
            self.card, self.scroll_w = None, 0
            self.roll.show(thing)
        elif name == "clock":
            self._clock(seconds)
        else:
            self.queue = [thing]
            self._next_card()

    def _clock(self, seconds):
        t = now_ms()
        self.mode, self.mode_since, self.until = "clock", t, t + int(seconds * 1000)
        self.card, self.scroll_w = None, 0
        self.next_clock = 0

    def _next_card(self):
        if not self.queue:
            self._advance()
            return
        self.card = self.queue.pop(0)
        t = now_ms()
        self.mode, self.mode_since = "card", t
        self.until = t + int(self.card.get("seconds", 5) * 1000)
        self.scroll_w = self.screen.show_card(self.card)


    def draw_clock(self, utc):
        """The moon clock. The moonrise line and the sunrise line take turns."""
        wifi = cardsmod.bars(self.rssi)
        if wifi is None and self.net.esp is not None and not self.net.connected():
            wifi = -1                     # red bars only when the WiFi is really down
        if not utc:
            self.screen.show_clock(None, None, self.twelve, wifi=wifi)
            return
        self.moon = self.moon_now(utc)
        local = clock.parts(utc + clock.offset(self.zone, utc))
        self.sun_turn = not self.sun_turn
        sun = self.sun_now(utc) if self.sun_turn else None
        self.screen.show_clock(local, self.moon, self.twelve, sun=sun, wifi=wifi)

