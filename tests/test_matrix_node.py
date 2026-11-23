"""Tests for the Matrix node (CIRCUITPY): clock, moon, news cards, finding
Chatty, and the whole app running on stand-ins for CircuitPython."""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "CIRCUITPY"))
sys.path.insert(0, os.path.join(ROOT, "sim"))

import chatty_clock as clock  # noqa: E402
import chatty_hub as hub  # noqa: E402
import chatty_moon as moon  # noqa: E402
import chatty_news as news  # noqa: E402
import chatty_art as art  # noqa: E402
import fake_circuitpython as fake  # noqa: E402


# ------------------------------------------------------------------ clock

def test_days_round_trip():
    for y, m, d in ((1970, 1, 1), (2000, 2, 29), (2026, 11, 17), (2099, 12, 31)):
        assert clock.civil_from_days(clock.days_from_civil(y, m, d)) == (y, m, d)
    assert clock.epoch(2000, 1, 1, 12) == moon.J2000


def test_weekday_and_sundays():
    assert clock.weekday(2026, 11, 17) == 1          # a Tuesday
    assert clock.nth_sunday(2026, 3, 2) == 8
    assert clock.nth_sunday(2026, 11, 1) == 1
    assert clock.nth_sunday(2026, 3, -1) == 29
    assert clock.nth_sunday(2026, 10, -1) == 25


def test_us_daylight_saving():
    zone = "America/New_York"
    before = clock.epoch(2026, 3, 8, 6, 59)          # 1:59 EST
    after = clock.epoch(2026, 3, 8, 7, 0)            # 3:00 EDT
    assert clock.offset(zone, before) == -5 * 3600
    assert clock.offset(zone, after) == -4 * 3600
    assert clock.offset(zone, clock.epoch(2026, 11, 1, 5, 59)) == -4 * 3600
    assert clock.offset(zone, clock.epoch(2026, 11, 1, 6, 0)) == -5 * 3600
    assert clock.offset("America/Phoenix", after) == -7 * 3600


def test_eu_daylight_saving_and_fixed():
    assert clock.offset("Europe/Berlin", clock.epoch(2026, 7, 1)) == 2 * 3600
    assert clock.offset("Europe/Berlin", clock.epoch(2026, 12, 1)) == 3600
    assert clock.offset("-07:00", 0) == -7 * 3600
    assert clock.offset("+05:30", 0) == 5 * 3600 + 1800
    assert clock.offset("Mars/Olympus", 0) == 0
    assert not clock.known("Mars/Olympus") and clock.known("UTC") and clock.known("-3")


def test_local_midnight_and_text():
    zone = "America/New_York"
    utc = clock.epoch(2026, 11, 17, 21, 30)          # 4:30 PM EST
    mid = clock.local_midnight(zone, utc)
    assert mid == clock.epoch(2026, 11, 17, 5)
    assert clock.hh_mm(15, 5) == "3:05" and clock.hh_mm(0, 0) == "12:00"
    assert clock.hh_mm(15, 5, twelve=False) == "15:05"
    assert clock.short_hour(15) == "3P" and clock.short_hour(0) == "12A"


def test_parse_iso():
    assert clock.parse_iso_utc("2026-02-17T05:12:34Z") == clock.epoch(2026, 2, 17, 5, 12, 34)
    assert clock.parse_iso_utc("2026-02-17T05:12:34+00:00") == clock.epoch(2026, 2, 17, 5, 12, 34)
    assert clock.parse_iso_utc("2026-02-17T00:12:34-05:00") == clock.epoch(2026, 2, 17, 5, 12, 34)
    assert clock.parse_iso_utc("garbage") is None


# ------------------------------------------------------------------ moon

def test_phase_at_known_new_and_full_moons():
    # full moon 2024-01-25 17:54 UTC, new moon 2024-01-11 11:57 UTC, full 2025-10-07 03:47
    p, lit = moon.illumination(clock.epoch(2024, 1, 25, 17, 54))
    assert abs(p - 0.5) < 0.03 and lit > 0.99
    p, lit = moon.illumination(clock.epoch(2024, 1, 11, 11, 57))
    assert min(p, 1 - p) < 0.03 and lit < 0.01
    p, lit = moon.illumination(clock.epoch(2025, 10, 7, 3, 47))
    assert abs(p - 0.5) < 0.03 and lit > 0.99
    assert moon.name(0.0) == "New moon" and moon.name(0.5) == "Full moon"
    assert moon.name(0.26) == "First quarter" and moon.name(0.99) == "New moon"


def test_moonrise_follows_the_phase():
    """Full moon rises around sunset, new moon around sunrise, about 50 min later a day."""
    lat, lon = 40.0, -100.0                          # a made-up spot
    def local_hours(day, when):
        start = clock.epoch(2024, 1, day) - int(lon / 15 * 3600)   # local mean midnight
        rise, sets = moon.rise_set(start, lat, lon)
        return (rise - start) / 3600 if rise else None, (sets - start) / 3600 if sets else None
    rise_full, _ = local_hours(25, None)
    assert 15.5 < rise_full < 19.5
    rise_new, _ = local_hours(11, None)
    assert 5.5 < rise_new < 9.5
    gaps = []
    for day in range(20, 24):
        a, _ = local_hours(day, None)
        b, _ = local_hours(day + 1, None)
        if a and b:
            gaps.append((b - a) * 60)
    assert gaps and all(20 < g < 90 for g in gaps)


def test_rise_and_set_alternate_and_next_event():
    lat, lon = 40.0, -100.0
    start = clock.epoch(2026, 11, 17, 7)
    today = moon.rise_set(start, lat, lon)
    tomorrow = moon.rise_set(start + 86400, lat, lon)
    for when in today + tomorrow:
        if when is not None:
            assert start <= when <= start + 2 * 86400
            assert abs(moon.altitude(when, lat, lon) - moon.RISE_ALT) < 0.01
    when, kind = moon.next_event(start, [today, tomorrow])
    assert kind in ("rise", "set") and when >= start
    assert moon.next_event(start, [(None, None)]) == (None, None)


def test_precision_trick_matches_plain_math():
    # the split angle must equal the plain formula (computers have big floats)
    di, df = moon._days(clock.epoch(2026, 11, 17, 21, 0))
    plain = (218.316 + 13.176396 * (di + df)) % 360
    assert abs(moon._angle(218.316, 13.176396, di, df) / moon.RAD - plain) < 1e-6


# ------------------------------------------------------------------ finding Chatty

def test_hosts_order_and_tailscale_skipped():
    note = hub.note_from(json.dumps({"lan": ["192.168.1.120"], "tailscale": "100.64.0.10",
                                     "known": {"HomeWiFi": "192.168.1.110",
                                               "ExtenderWiFi": "192.168.1.120"}}))
    hosts = hub.to_try("192.168.1.110", note, "192.168.1.50, 100.64.0.10")
    assert hosts == ["192.168.1.110", "192.168.1.120", "192.168.1.50", "chatty-node"]
    assert hub.note_from("not json") is None and hub.note_from("[1]") is None


def test_pack_unpack():
    note = {"lan": ["192.168.1.120"], "known": ["192.168.1.110"]}
    data = hub.pack("192.168.1.120", note)
    assert len(data) <= hub.MAX_SAVE
    assert hub.unpack(data + bytes(20)) == ("192.168.1.120", note)
    assert hub.unpack(bytes(64)) == (None, None)
    big = {"lan": ["1" * 40] * 3, "known": ["2" * 40] * 4}
    assert len(hub.pack("x", big)) <= hub.MAX_SAVE


# ------------------------------------------------------------------ news

NOW = clock.epoch(2026, 11, 17, 21, 0)


def hm(utc):
    p = clock.parts(utc - 5 * 3600)
    return p[3], p[4]


def test_tornado_warning_and_old_news():
    n = news.News()
    body = {"alerts": [{"event": "Tornado Warning", "kind": "urgent", "expires_ts": NOW + 1800},
                       {"event": "Flood Watch", "kind": "info", "expires_ts": None}], "ts": NOW - 60}
    n.message("chatty/alerts/active", json.dumps(body), NOW, 1000)
    assert n.tornado(NOW, 1000)["event"] == "Tornado Warning"
    cards = n.cards(NOW, 1000, hm)
    assert [c["scroll"] for c in cards if c["scroll"]] == ["FLOOD WATCH"]
    assert n.tornado(NOW + 1801, 1000) is None                  # expired
    assert n.tornado(NOW, 1000 + news.ALERTS_STALE + 1) is None  # no word from Chatty
    old = dict(body, ts=NOW - 3 * 3600)                          # an old retained list
    n.message("chatty/alerts/active", json.dumps(old), NOW, 2000)
    assert n.tornado(NOW, 2000) is None
    n.message("chatty/alerts/active", json.dumps({"alerts": [], "ts": NOW}), NOW, 2000)
    assert n.tornado(NOW, 2000) is None and n.cards(NOW, 2000, hm) == []


def test_alert_card_with_end_time():
    n = news.News()
    body = {"alerts": [{"event": "Severe Thunderstorm Warning", "kind": "urgent",
                        "expires_ts": clock.epoch(2026, 11, 18, 3, 45)}], "ts": NOW}
    n.message("chatty/alerts/active", json.dumps(body), NOW, 10)
    card = n.cards(NOW, 10, hm)[0]
    assert card["scroll"] == "SEVERE THUNDERSTORM WARNING TIL 10:45PM"
    assert card["color"] == news.ORANGE


def test_rain_now_and_rain_coming():
    n = news.News()
    n.message("chatty/forecast/rain", json.dumps({"rain_expected": True, "starts_ts": NOW + 3600,
                                                  "chance": 70, "kind": "rain", "ts": NOW}), NOW, 10)
    card = n.cards(NOW, 10, hm)[0]
    assert card["icon"] == "cloud" and card["lines"] == ["RAIN", "70%", "5P"]
    n.message("chatty/nodes/rain/data", json.dumps({"rate_mm_hr": 0, "tip_count": 5}), NOW, 20)
    assert not n.raining(20)
    n.message("chatty/nodes/rain/data", json.dumps({"rate_mm_hr": 0, "tip_count": 6,
                                                    "rain_in": 0.124}), NOW, 30)
    assert n.raining(30) and not n.raining(30 + news.RAIN_QUIET + 1)
    card = n.cards(NOW, 31, hm)[0]
    assert card["icon"] == "drop" and card["lines"] == ["RAIN", "NOW", '0.12"']


def test_lightning_flash_only_for_new_strikes():
    n = news.News()
    old = {"last_strike": {"ts": NOW - 7200, "distance_mi": 9}}
    assert n.message("chatty/nodes/lightning/data", json.dumps(old), NOW, 10) == []
    fresh = {"last_strike": {"ts": NOW - 20, "distance_km": 9.7}}
    events = n.message("chatty/nodes/lightning/data", json.dumps(fresh), NOW, 11)
    assert events and events[0][0] == "strike" and round(events[0][1]) == 6
    assert n.message("chatty/nodes/lightning/data", json.dumps(fresh), NOW, 12) == []
    card = [c for c in n.cards(NOW, 12, hm) if c["icon"] == "bolt"][0]
    assert card["lines"][0] == "6mi"
    # no clock yet: the first strike seen can't be told apart from an old one
    m = news.News()
    assert m.message("chatty/nodes/lightning/data", json.dumps(fresh), None, 5) == []


def test_greenhouse_card_and_roll_call():
    n = news.News("matrix")
    assert n.greenhouse_card(10) is None
    n.message("chatty/nodes/greenhouse/data",
              json.dumps({"metrics": {"air_temperature_f": 71.6, "soil_moisture_band": "Dry"}}),
              NOW, 10)
    plant = n.greenhouse_card(10)
    assert plant["lines"] == ["PLANT", "72F", "DRY"] and plant["color"] == news.ORANGE
    n.message("chatty/nodes/greenhouse/data", json.dumps(
        {"metrics": {"air_temperature_f": 64, "soil_moisture_band": "okay",
                     "soil_moisture_percent": 41.6, "soil_voltage": 1.4}}), NOW, 20)
    assert n.greenhouse_card(20)["lines"] == ["64F", "OK", "42%"]
    n.message("chatty/nodes/greenhouse/data", json.dumps(
        {"metrics": {"air_temperature_f": 64, "soil_moisture_percent": 100,
                     "soil_voltage": 0.0}}), NOW, 30)
    assert n.greenhouse_card(30)["lines"] == ["PLANT", "64F"]      # unplugged probe
    assert n.greenhouse_card(30 + news.READING_STALE + 1) is None
    for name, body in (("rain", {"state": "online"}), ("greenhouse", {"state": "online"}),
                       ("lightning", {"state": "offline"}), ("matrix", {"state": "online"}),
                       ("wordclock", {"state": "offline", "clean": True, "reason": "reboot"})):
        body["every"] = 60
        n.message("chatty/nodes/%s/status" % name, json.dumps(body), NOW, 10)
    assert n.roll(10) == [("ZAP", "quiet"), ("CLOK", "rest"), ("GRN", "on"), ("RAIN", "on")]
    assert n.online(10) == (2, 4) and n.online(10 + 400) == (0, 4)   # everyone went silent
    assert [s for _, s in n.roll(10 + 400)] == ["quiet", "quiet", "quiet", "rest"]
    assert all(c["icon"] not in ("leaf", "nodes") for c in n.cards(NOW, 10, hm))


def test_co2_card():
    n = news.News("matrix")
    n.message("chatty/nodes/greenhouse/data",
              json.dumps({"metrics": {"air_temperature_f": 70, "soil_moisture_band": "wet"}}), NOW, 10)
    assert n.co2_card(10) is None                                  # no CO2 sensor: no card
    n.message("chatty/nodes/greenhouse/data", json.dumps(
        {"metrics": {"soil_moisture_band": "wet", "co2_ppm": 641.6, "co2_band": "normal"}}), NOW, 20)
    card = n.co2_card(20)
    assert card["lines"] == ["CO2", "642", "PPM"] and card["color"] == news.GREEN
    n.message("chatty/nodes/greenhouse/data", json.dumps({"metrics": {"co2_ppm": 1800}}), NOW, 30)
    card = n.co2_card(30)
    assert card["lines"] == ["CO2", "1800", "HIGH"] and card["color"] == news.ORANGE
    assert n.co2_card(30 + news.READING_STALE + 1) is None


def test_app_shows_co2_after_the_greenhouse():
    real = time.monotonic_ns
    clk = Clock()
    try:
        app = make_app(clk, {"ssid": "HomeWiFi", "password": "x", "timezone": "America/Denver",
                             "mqtt_hosts": "192.168.1.50", "cards": "clock:4, greenhouse:3"})
        fake.BROKER.post("chatty/nodes/greenhouse/data",
                         {"metrics": {"air_temperature_f": 70, "soil_moisture_band": "wet",
                                      "co2_ppm": 640, "co2_band": "normal"}})
        run(app, clk, 2)
        shown = []
        for _ in range(12 * 25):
            app.step()
            clk.advance(1 / 25)
            if app.mode == "card" and (not shown or shown[-1] != app.card["lines"]):
                shown.append(app.card["lines"])
        assert shown[0][0] != "CO2" and shown[1] == ["CO2", "640", "PPM"], shown
    finally:
        time.monotonic_ns = real


def test_rain_gauge_tip_event():
    n = news.News()
    assert n.message("chatty/nodes/rain/data", json.dumps({"tip_count": 4}), NOW, 1) == []
    assert n.message("chatty/nodes/rain/data", json.dumps({"tip_count": 4}), NOW, 2) == []
    assert n.message("chatty/nodes/rain/data", json.dumps({"tip_count": 5}), NOW, 3) == [("tip", 5)]
    assert n.message("chatty/nodes/rain/data", json.dumps({"tip_count": 0}), NOW, 4) == []


# ------------------------------------------------------------------ the card library

import chatty_cards as cards  # noqa: E402
import chatty_tide as tide  # noqa: E402


def test_cards_line():
    assert cards.parse("clock:30, tide, roll:4.5, bogus, news:7") == [
        ("clock", 30.0), ("tide", 8), ("roll", 4.5), ("news", 7.0)]
    default = cards.parse(None)
    assert [n for n, _ in default].count("clock") == 3 and ("sun", 6) in default
    assert cards.parse("", clock_seconds=45)[0] == ("clock", 45)
    assert cards.parse("clock:12", clock_seconds=45) == [("clock", 12.0)]
    assert cards.parse("nothing, here") == default
    assert cards.parse("clock:0.1, tide:99999") == [("clock", 2.0), ("tide", 3600.0)]


def test_deck_skips_empty_cards_and_wraps():
    deck = cards.Deck(cards.parse("clock:10, tide:8, roll:5"))
    have = {"clock": True, "roll": ["x"]}
    picks = [deck.next(lambda n, s: have.get(n))[:2] for _ in range(5)]
    assert picks == [("clock", 10), ("roll", 5), ("clock", 10), ("roll", 5), ("clock", 10)]
    empty = cards.Deck(cards.parse("tide, sun"))
    assert empty.next(lambda n, s: None)[0] == "clock"


def test_wifi_bars():
    assert [cards.bars(x) for x in (-40, -55, -60, -70, -80, -90, 0, None)] == \
        [4, 4, 3, 2, 1, 0, None, None]


def test_sun_card():
    card = cards.sun_card((7, 1), (17, 24), 10 * 3600 + 23 * 60)
    assert card["lines"] == ["7:01A", "5:24P", "10h23"] and card["icon"] == "sun"
    assert cards.sun_card((10, 45), (23, 59), 0)["lines"] == ["10:45", "11:59"]
    assert cards.sun_card(None, (17, 0), 0) is None


def test_sunrise_and_sunset():
    lat, lon = 40.0, -100.0                          # a made-up spot
    for date, day_hours in (((2026, 6, 21), 15.0), ((2026, 12, 21), 9.3), ((2026, 3, 20), 12.1)):
        start = clock.epoch(*date, 6)                # around local midnight
        rise, sets = moon.sun_rise_set(start, lat, lon)
        assert rise and sets and abs((sets - rise) / 3600 - day_hours) < 0.2, date
        assert abs(moon.sun_altitude(rise, lat, lon) - moon.SUN_RISE_ALT) < 0.01
        noon = (rise + sets) // 2                    # sun highest about 18:40 UTC at 100 W
        assert abs(clock.parts(noon)[3] * 60 + clock.parts(noon)[4] - (18 * 60 + 40)) < 20


def _noaa(*rows):
    """Chatty's chatty/tides message (node_feed.py) for these NOAA-style rows."""
    events = []
    for t, v, k in rows:
        date, hm_ = t.split(" ")
        y, mo, d = [int(x) for x in date.split("-")]
        hh, mm = [int(x) for x in hm_.split(":")]
        events.append([clock.epoch(y, mo, d, hh, mm), float(v), k])
    return {"station": "1234567", "units": "english", "events": events, "ts": NOW}


TIDES = _noaa(("2026-11-17 14:06", "1.712", "H"), ("2026-11-17 20:48", "0.402", "L"),
              ("2026-11-18 03:30", "1.905", "H"), ("2026-11-18 10:12", "-0.150", "L"))


def test_tide_parse_and_now():
    events, units = tide.from_chatty(TIDES)
    assert events[0] == (clock.epoch(2026, 11, 17, 14, 6), 1.712, "H") and len(events) == 4
    assert units == "english" and tide.from_chatty(dict(TIDES, units="metric"))[1] == "metric"
    assert tide.from_chatty({"oops": 1}) == ([], "english") and tide.from_chatty(None)[0] == []
    assert tide.from_chatty({"events": [["x", 1, "H"], [1, 2], [5, "1.5", "low"]]})[0] == \
        [(5, 1.5, "L")]
    info = tide.now(events, NOW)                      # 21:00 UTC: just after the 20:48 low
    assert info["rising"] and info["next"][2] == "H"
    assert 0.40 < info["height"] < 0.45
    mid = clock.epoch(2026, 11, 18, 0, 9)             # halfway from the low to the high
    assert abs(tide.now(events, mid)["height"] - (0.402 + 1.905) / 2) < 0.01
    assert not tide.now(events, clock.epoch(2026, 11, 18, 4))["rising"]
    assert tide.now(events, clock.epoch(2026, 11, 19)) is None   # ran out: fetch again


def test_tide_card():
    card = tide.card(tide.from_chatty(TIDES)[0], NOW, hm)
    assert card["icon"] == "tideup" and card["lines"] == ["HIGH", "10:30", "1.9'"]
    card = tide.card(tide.from_chatty(TIDES)[0], clock.epoch(2026, 11, 18, 4), hm, "metric")
    assert card["icon"] == "tidedn" and card["lines"] == ["LOW", "5:12A", "-0.1m"]
    assert tide.card([], NOW, hm) is None and tide.card(tide.from_chatty(TIDES)[0], None, hm) is None
    assert tide.height_text(-0.04) == "0.0'" and len(tide.height_text(-12.34)) <= 5


def test_soil_band():
    assert news.soil_band({"soil_moisture_band": "okay"}) == "ok"
    assert news.soil_band({"soil_moisture_percent": 20, "soil_voltage": 1.2}) == "dry"
    assert news.soil_band({"soil_moisture_percent": 100, "soil_voltage": 0.0}) is None
    assert news.soil_band({}) is None


def test_cards_fit_the_panel():
    n = news.News()
    n.message("chatty/forecast/rain", json.dumps({"rain_expected": True, "starts_ts": NOW + 9000,
                                                  "chance": 100, "kind": "storms", "ts": NOW}),
              NOW, 1)
    for c in n.cards(NOW, 1, hm):
        assert all(len(x) <= 5 for x in c["lines"])
        assert c["icon"] in art.ICONS


def test_icons_are_square():
    for name, rows in art.ICONS.items():
        assert len(rows) == art.SIZE and all(len(r) == art.SIZE for r in rows), name
        assert set("".join(rows)) <= set(".#+"), name
    for name, rows in art.MINI.items():
        assert len(rows) == art.MINI_H and all(len(r) == art.MINI_W for r in rows), name
    for name in ("tideup", "tidedn", "sun", "sunup", "sundn", "up", "down", "level"):
        assert art.pixels(name), name


# ------------------------------------------------------------------ the whole app

class Clock:
    def __init__(self):
        self.ns = 10 ** 12

    def __call__(self):
        return self.ns

    def advance(self, seconds):
        self.ns += int(seconds * 1e9)


def make_app(clk, secrets=None):
    fake.BROKER.__init__()
    fake.install(secrets or {"ssid": "HomeWiFi", "password": "x", "timezone": "America/Denver",
                             "latitude": 40.0, "longitude": -100.0,
                             "mqtt_hosts": "10.0.0.9, 192.168.1.50"})
    time.monotonic_ns = clk
    import chatty_matrix
    import chatty_net
    net = chatty_net.Net("HomeWiFi", "x")
    start = NOW
    net.esp = fake.FakeESP(lambda: start + (clk.ns - 10 ** 12) // 10 ** 9)
    app = chatty_matrix.App(display=fake.FakeDisplay(), net=net)
    return app


def run(app, clk, seconds, fps=25):
    for _ in range(int(seconds * fps)):
        app.step()
        clk.advance(1 / fps)


def test_app_joins_the_network_and_shows_the_moon():
    real = time.monotonic_ns
    clk = Clock()
    try:
        app = make_app(clk)
        fake.BROKER.post("chatty/nodes/rain/status", {"state": "online", "every": 60})
        run(app, clk, 2)
        assert app.utc() is not None and app.link.host == "192.168.1.50"
        status = fake.BROKER.last("chatty/nodes/matrix/status")
        assert status["state"] == "online" and status["title"] == "Matrix clock"
        assert app.link.client.will[0] == "chatty/nodes/matrix/status"
        data = fake.BROKER.last("chatty/nodes/matrix/data")
        assert data["moon"]["name"] and 0 <= data["moon"]["lit"] <= 100
        assert app.mode == "clock" and app.screen.time.text != "--:--"
        assert app.screen.moon_tile[0].bitmap.path.startswith("moon/moon")
        # the address that worked is remembered for next time
        import microcontroller
        assert hub.unpack(microcontroller.nvm)[0] == "192.168.1.50"
    finally:
        time.monotonic_ns = real


def test_app_tornado_takes_over_and_lets_go():
    real = time.monotonic_ns
    clk = Clock()
    try:
        app = make_app(clk)
        run(app, clk, 2)
        utc = app.utc()
        fake.BROKER.post("chatty/alerts/active", {"alerts": [{"event": "Tornado Warning",
                                                              "kind": "urgent",
                                                              "expires_ts": utc + 900}],
                                                  "ts": utc})
        run(app, clk, 2)
        assert app.mode == "tornado" and not app.screen.frame.hidden
        assert "TORNADO WARNING UNTIL" in app.screen.scroll.text
        assert app.screen.moon.hidden
        run(app, clk, 30)                       # buttons-free, cards don't push it away
        assert app.mode == "tornado"
        fake.BROKER.post("chatty/alerts/active", {"alerts": [], "ts": app.utc()})
        run(app, clk, 2)
        assert app.mode == "clock" and app.screen.frame.hidden and not app.screen.moon.hidden
    finally:
        time.monotonic_ns = real


def test_red_night_glow_and_tornado_beats_it():
    import chatty_bits
    real = time.monotonic_ns
    clk = Clock()
    try:
        app = make_app(clk)
        chatty_bits = sys.modules["chatty_bits"]   # the copy the app uses
        app.night = (0, 24)                     # night all day, for the test
        run(app, clk, 7)
        assert chatty_bits.RED[0]
        for item in (app.screen.time, app.screen.pct):
            assert item.color & 0xFFFF == 0 and item.color >> 16 > 0, hex(item.color)
        utc = app.utc()
        fake.BROKER.post("chatty/alerts/active", {"alerts": [{"event": "Tornado Warning",
                                                              "kind": "urgent",
                                                              "expires_ts": utc + 900}],
                                                  "ts": utc})
        run(app, clk, 2)
        assert app.mode == "tornado" and not chatty_bits.RED[0]
        assert app.screen.icon_pal[2] & 0xFFFF       # its own colors, not red
        app.red_night = False
        fake.BROKER.post("chatty/alerts/active", {"alerts": [], "ts": app.utc()})
        run(app, clk, 2)
        assert not chatty_bits.RED[0]
        assert chatty_bits.dim(0x00FF00, 0.5) == 0x007F00
    finally:
        chatty_bits.RED[0] = False
        time.monotonic_ns = real


def test_red_dim_keeps_shapes():
    import chatty_bits
    chatty_bits.RED[0] = True
    try:
        assert chatty_bits.dim(0xFFFFFF, 1) == 0xFF0000
        assert chatty_bits.dim(0x000000, 1) == 0
        assert chatty_bits.dim(0x1040A0, 1) >> 16 > 0x60          # blue doesn't vanish
        assert chatty_bits.dim(0xFFFFFF, 0.25) == 0x3F0000
    finally:
        chatty_bits.RED[0] = False


def test_app_news_round_rain_and_strike():
    real = time.monotonic_ns
    clk = Clock()
    try:
        app = make_app(clk)
        run(app, clk, 2)
        fake.BROKER.post("chatty/nodes/rain/data", {"rate_mm_hr": 1.2, "rain_in": 0.3,
                                                    "tip_count": 3})
        run(app, clk, 2)
        assert not app.screen.rain_grid.hidden and any(app.screen.rain_bmp.px)
        run(app, clk, 20)
        assert app.mode == "card" and app.card["icon"] == "drop"
        run(app, clk, 6)
        assert app.mode == "clock"
        fake.BROKER.post("chatty/nodes/lightning/data",
                         {"last_strike": {"ts": app.utc() - 5, "distance_mi": 3}})
        app.network(app.next_loop)              # read it now
        app.step()
        assert app.card["icon"] == "bolt" and not app.screen.flash.hidden
        run(app, clk, 1)
        assert app.screen.flash.hidden
    finally:
        time.monotonic_ns = real


def test_app_without_chatty_still_keeps_time():
    real = time.monotonic_ns
    clk = Clock()
    try:
        app = make_app(clk)
        fake.BROKER.reachable = set()
        run(app, clk, 3)
        assert app.link.client is None and app.utc() is not None
        assert app.screen.time.text != "--:--"
        fake.BROKER.reachable = {"192.168.1.50"}
        run(app, clk, 30)
        assert app.link.client is not None
    finally:
        time.monotonic_ns = real


def test_app_follows_chattys_note():
    real = time.monotonic_ns
    clk = Clock()
    try:
        app = make_app(clk)
        fake.BROKER.post("chatty/hub", {"lan": ["192.168.1.120"], "tailscale": "100.64.0.10",
                                        "known": {"HomeWiFi": "192.168.1.50"}})
        run(app, clk, 2)
        assert app.link.note["lan"] == ["192.168.1.120"]
        # she moved: the old address is gone, the note's new one answers
        fake.BROKER.reachable = {"192.168.1.120"}
        app.link.drop()
        run(app, clk, 10)
        assert app.link.host == "192.168.1.120"
    finally:
        time.monotonic_ns = real


def test_no_location_means_no_rise_times_but_a_moon():
    real = time.monotonic_ns
    clk = Clock()
    try:
        app = make_app(clk, {"ssid": "HomeWiFi", "password": "x", "mqtt_hosts": "192.168.1.50"})
        run(app, clk, 2)
        assert app.zone == "UTC" and "next" not in app.moon
        assert app.screen.event.y == -99 and app.screen.pct.text.endswith("%")
    finally:
        time.monotonic_ns = real


def test_portrait_cards_stay_on_the_panel():
    real = time.monotonic_ns
    clk = Clock()
    try:
        app = make_app(clk)
        from chatty_screen import Screen
        import chatty_screen
        fonts = chatty_screen.load_fonts()
        for rotation in (0, 90):
            screen = Screen(fake.FakeDisplay(), rotation, fonts)
            n = news.News()
            n.message("chatty/forecast/rain", json.dumps({"rain_expected": True, "chance": 70,
                                                          "starts_ts": NOW + 3600, "ts": NOW}),
                      NOW, 1)
            n.message("chatty/nodes/greenhouse/data",
                      json.dumps({"air_temperature_f": 70, "soil_moisture_band": "wet"}), NOW, 1)
            for card in n.cards(NOW, 1, hm):
                screen.show_card(card)
                assert 0 <= screen.icon.x and screen.icon.x + art.SIZE <= screen.w
                assert 0 <= screen.icon.y and screen.icon.y + art.SIZE <= screen.h
                for item in screen.lines:
                    if item.y != -99:
                        box = item.bounding_box
                        assert item.x >= 0 and item.x + box[2] <= screen.w, (rotation, item.text)
                        assert item.y - 5 >= 0 and item.y + 5 <= screen.h, (rotation, item.text)
            for risen in (True, False):
                info = {"phase": 0.3, "lit": 0.6, "next": "set" if risen else "rise",
                        "next_local": (21, 5)}
                screen.show_clock(clock.parts(NOW), info, True)
                for item in (screen.time, screen.date, screen.event):
                    assert item.x >= 0 and item.x + item.bounding_box[2] <= screen.w
    finally:
        time.monotonic_ns = real


def test_app_rotates_the_card_library():
    real = time.monotonic_ns
    clk = Clock()
    try:
        app = make_app(clk, {"ssid": "HomeWiFi", "password": "x", "timezone": "America/Denver",
                             "latitude": 40.0, "longitude": -100.0, "mqtt_hosts": "192.168.1.50",
                             "cards": "clock:10, tide:4, greenhouse:3, roll:5, sun:3, news"})
        fake.BROKER.post("chatty/tides", TIDES_NOW)
        fake.BROKER.post("chatty/nodes/greenhouse/data",
                         {"metrics": {"air_temperature_f": 70, "soil_moisture_band": "wet"}})
        fake.BROKER.post("chatty/nodes/rain/status", {"state": "online", "every": 60})
        fake.BROKER.post("chatty/nodes/lightning/status", {"state": "offline"})
        run(app, clk, 2)
        assert len(app.tides) == 6 and app.mode == "clock"
        seen = []
        for _ in range(30 * 25):
            app.step()
            clk.advance(1 / 25)
            label = app.mode if app.mode != "card" else app.card["icon"]
            if not seen or seen[-1][0] != label:
                seen.append([label, 0])
            seen[-1][1] += 1
        names = [x[0] for x in seen]
        assert names[:6] == ["clock", "tideup", "leaf", "roll", "sun", "clock"], names
        frames = dict((x[0], x[1]) for x in seen[1:5])
        assert abs(frames["tideup"] - 100) <= 2 and abs(frames["leaf"] - 75) <= 2
        assert abs(frames["roll"] - 125) <= 2                     # 5 seconds at 25 a second
        # roll call: quiet lightning on top, red
        labels = [l.text for l in app.roll.labels if l.y != -99]
        assert labels == ["ZAP", "RAIN"]
        # the heartbeat carries the WiFi signal and the tide
        app.heartbeat()
        assert fake.BROKER.last("chatty/nodes/matrix/status")["rssi"] == -62
        data = fake.BROKER.last("chatty/nodes/matrix/data")
        assert data["wifi"] == {"rssi": -62, "bars": 3}
    finally:
        time.monotonic_ns = real


def test_app_clock_and_tides_from_chatty():
    real = time.monotonic_ns
    clk = Clock()
    try:
        app = make_app(clk, {"ssid": "HomeWiFi", "password": "x", "mqtt_hosts": "192.168.1.50",
                             "cards": "clock:60, tide:5"})
        app.net.esp.get_time = lambda: 0         # the WiFi chip's time server never answers
        run(app, clk, 3)
        assert app.utc() is None and app.link.client is not None
        assert app.screen.time.text == "--:--"
        fake.BROKER.post("chatty/clock", {"ts": NOW + 5}, retain=False)
        run(app, clk, 6)                         # the next clock redraw shows it
        assert app.clock_from == "chatty" and abs(app.utc() - (NOW + 11)) <= 1
        assert app.screen.time.text != "--:--"
        assert "chatty/clock" not in fake.BROKER.retained
        app.buttons.pressed = lambda: ["BUTTON_UP"]
        app.step()
        app.buttons.pressed = lambda: []
        assert app.mode == "clock"               # no tides yet: the tide card is skipped
        fake.BROKER.post("chatty/tides", TIDES_NOW)
        run(app, clk, 2)
        app.buttons.pressed = lambda: ["BUTTON_UP"]
        app.step()
        app.buttons.pressed = lambda: []
        assert app.mode == "card" and app.card["icon"] in ("tideup", "tidedn")
        app.buttons.pressed = lambda: ["BUTTON_DOWN"]
        app.step()
        app.buttons.pressed = lambda: []
        assert app.mode == "clock"
        run(app, clk, 100, fps=2)
        assert app.mode == "clock"               # DOWN: two minutes of clock
        # the WiFi chip's own time wins over Chatty's once it answers
        app.net.esp.get_time = lambda: NOW + 3600
        app.next_sync = 0
        app.step()
        assert app.clock_from == "wifi"
        fake.BROKER.post("chatty/clock", {"ts": NOW + 99999}, retain=False)
        run(app, clk, 2)
        assert abs(app.utc() - (NOW + 3600)) < 10
    finally:
        time.monotonic_ns = real


def test_board_makes_no_web_requests():
    for name in os.listdir(os.path.join(ROOT, "CIRCUITPY")):
        if name.endswith(".py"):
            text = open(os.path.join(ROOT, "CIRCUITPY", name)).read()
            assert "adafruit_requests" not in text, name


TINY_BDF = """STARTFONT 2.1
FONTBOUNDINGBOX 4 6 0 -1
CHARS 2
STARTCHAR one
ENCODING 49
DWIDTH 5 0
BBX 3 5 0 0
BITMAP
40
C0
40
40
E0
ENDCHAR
STARTCHAR M
ENCODING 77
DWIDTH 5 0
BBX 4 5 0 0
BITMAP
90
F0
F0
90
90
ENDCHAR
ENDFONT
"""


def test_own_text_labels():
    import tempfile
    fake.install({})
    import chatty_text as text
    path = os.path.join(tempfile.mkdtemp(), "tiny.bdf")
    with open(path, "w") as fh:
        fh.write(TINY_BDF)
    font = text.load_bdf(path, "1")
    assert set(font.glyphs) == {"1", "M"} and font.ascent == 5
    label = text.Label(font, color=0x123456, text="11", background_color=0, padding_left=1)
    assert label.bounding_box[2] == 11 and label.color == 0x123456
    bmp = label[0].bitmap
    assert [bmp[2, y] for y in range(5)] == [1, 1, 1, 1, 1]      # the 1's stem
    assert 0 not in label.pal.transparent                           # a solid background
    label.text = "1?"                                               # unknown letter: a gap
    assert label.bounding_box[2] == 6
    arrows = text.arrows()
    assert text.Label(arrows, text="\u21a5").bounding_box[2] == 6
    term = text.Label(text.BuiltinFont(sys.modules["terminalio"].FONT), text="HI")
    assert term.bounding_box[2] == 12


def test_precompiled_files_match_the_code():
    """CIRCUITPY_MPY/ must be rebuilt (bash scripts/build_mpy.sh) after a .py change."""
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import mpy_sources
    built = open(os.path.join(ROOT, "CIRCUITPY_MPY", "sources.txt")).read()
    assert built == mpy_sources.fingerprints(), "run: bash scripts/build_mpy.sh <mpy-cross>"
    for line in built.split():
        if line.endswith(".py"):
            assert os.path.exists(os.path.join(ROOT, "CIRCUITPY_MPY", line[:-3] + ".mpy")), line


TIDES_NOW = _noaa(("2026-11-17 14:06", "1.712", "H"), ("2026-11-17 20:48", "0.402", "L"),
                  ("2026-11-18 03:30", "1.905", "H"), ("2026-11-18 10:12", "-0.150", "L"),
                  ("2026-11-18 16:40", "1.600", "H"), ("2026-11-18 23:02", "0.500", "L"))


# ------------------------------------------------------------------ weather trends

import chatty_trend as trend  # noqa: E402

TRENDS = {"pressure_hpa": 1008.6, "pressure_3h": -4.2, "temp_f": 41.2, "temp_1h": -2.6,
          "temp_2h": -6.1, "humidity_3h": 4, "advisories": ["pressure", "frost"], "ts": NOW}


def test_trend_cards():
    p, t = trend.cards(TRENDS)
    assert p["lines"] == ["1009", "MB", "DROP"] and p["icon"] == "down"
    assert t["lines"] == ["41F", "-6F", "FROST"] and t["icon"] == "down"
    for card in (p, t):
        assert all(len(x) <= 5 for x in card["lines"]) and card["icon"] in art.ICONS
    for p3, word in ((-7, "FAST!"), (-1.5, "LOWER"), (0.2, "STEDY"), (1.4, "UP"), (3.5, "RISE")):
        assert trend.pressure_card({"pressure_hpa": 1000, "pressure_3h": p3})["lines"][2] == word
    assert trend.pressure_card({"pressure_hpa": 1000})["lines"] == ["1000", "MB"]
    calm = {"pressure_hpa": 1015, "pressure_3h": 0, "temp_f": 70, "temp_2h": -2, "advisories": []}
    assert len(trend.cards(calm)) == 1 and trend.news(calm) == []      # no temperature news
    assert trend.temp_card({"temp_f": 80, "temp_2h": 7})["lines"] == ["80F", "+7F", "2 HRS"]


def test_trend_news_and_staleness():
    assert [c["lines"][2] for c in trend.news(TRENDS)] == ["DROP", "FROST"]
    assert trend.news({"pressure_hpa": 1000, "pressure_3h": -4, "advisories": ["pressure"]})
    assert trend.fresh(TRENDS, NOW + 60) is TRENDS
    assert trend.fresh(TRENDS, NOW + trend.STALE + 1) is None
    assert trend.fresh(TRENDS, None) is TRENDS                     # no clock yet: trust it
    assert trend.cards(None) == [] and trend.news(None) == []


def test_app_shows_trends():
    real = time.monotonic_ns
    clk = Clock()
    try:
        app = make_app(clk, {"ssid": "HomeWiFi", "password": "x", "timezone": "America/Denver",
                             "mqtt_hosts": "192.168.1.50", "cards": "clock:4, trend:3"})
        body = dict(TRENDS)
        body["ts"] = int(time.time())
        fake.BROKER.post("chatty/trends", body)
        run(app, clk, 2)
        shown = []
        for _ in range(12 * 25):
            app.step()
            clk.advance(1 / 25)
            if app.mode == "card" and (not shown or shown[-1] != app.card["lines"]):
                shown.append(app.card["lines"])
        assert ["1009", "MB", "DROP"] in shown and ["41F", "-6F", "FROST"] in shown, shown
    finally:
        time.monotonic_ns = real


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok  ", name)
            except Exception as ex:  # noqa: BLE001
                failed += 1
                import traceback
                traceback.print_exc()
                print("FAIL", name, repr(ex))
    sys.exit(1 if failed else 0)
