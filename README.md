# matrix-node

Chatty's Matrix node: an Adafruit Matrix Portal M4 + 64x32 RGB LED panel.

A moon clock that is also a node on Chatty's network.

- **A library of cards** it rotates through, each for its own number of seconds, set by
  one line in `secrets.py` (`"cards": "clock:20, news, tide:8, ..."`, see `chatty_cards.py`).
  A card with nothing to show right now is skipped.
  - `clock`: time, date, the moon's picture and how much is lit (Phil Burgess's Moon Phase
    Clock layout), with the moonrise/moonset line taking turns with sunrise/sunset (a little
    sun picture). WiFi bars sit in the moon picture's corner. The moon and sun are worked
    out on the board (`chatty_moon.py`): no web service, and the location never leaves it.
  - `news`: weather alerts (scrolling), a lightning strike (miles, minutes ago), rain now
    (and the total) or rain coming (chance and hour).
  - `tide`: the next high or low tide, its time and height, with a rising or falling arrow,
    from NOAA's free tides service. Chatty fetches them on her Pi (`CHATTY_TIDE_STATION`
    in her settings, chatty-node `node_feed.py`) and posts them on `chatty/tides`: the
    board makes no web requests, the web library doesn't fit next to MQTT. Its clock
    comes from the WiFi chip's time server, or from Chatty's `chatty/clock`.
  - `greenhouse`: temperature, dry / ok / wet, and the soil moisture percent.
  - `roll`: roll call, a dot per node: green online, red quiet, amber said a proper
    goodbye (reboot or shutdown) and isn't back yet.
  - `sun`: today's sunrise, sunset and how long the day is.
- **Tornado Warning:** beats every card. The whole panel turns into a blinking red TAKE
  COVER sign with the end time scrolling, at full brightness, until Chatty's alert list
  drops it. Buttons, flashes and ripples wait.
- **Lightning** flashes the panel with a yellow bolt; a **rain gauge tip** sends blue
  ripples across it; while it **rains**, blue drops fall over the moon.
- **Night** (22:00 to 7:00): the text dims.
- **Buttons:** UP = next card now, DOWN = back to the clock for 2 minutes.
- **On the network:** heartbeat `chatty/nodes/matrix/status` every minute with its WiFi
  signal (`rssi`, dBm; last will "offline"), and on `chatty/nodes/matrix/data` the moon,
  the WiFi (`rssi`, `bars`) and the next tide, both retained. Read-only: it never sends
  anyone a command.

Finding Chatty: the board can't use Tailscale or `chatty-node.local`, so it tries the
address that worked last time, her home addresses from her `chatty/hub` note (kept in the
board's small memory), then `mqtt_hosts` from secrets.py, then `chatty-node`.

## Files (copy everything in `CIRCUITPY/` to the drive)

| file | what |
| --- | --- |
| `code.py` | starts it |
| `chatty_matrix.py` | the app: buttons, network, heartbeat, tornado |
| `chatty_library.py` | the card library at work: next card, building each, tides |
| `chatty_cards.py` | the card line from secrets.py, WiFi bars, the sun card (tested) |
| `chatty_screen.py` | the clock layout, cards, tornado frame, flash, rain |
| `chatty_panels.py` | roll call, the bolt and ripple, sunrise picture, WiFi bars |
| `chatty_tide.py` | Chatty's tide news -> the tide card (tested) |
| `chatty_net.py` | WiFi (ESP32) and MQTT, old or new Adafruit libraries |
| `chatty_news.py` | MQTT news -> cards (tested on a computer) |
| `chatty_moon.py` | moon phase, moonrise, moonset, sunrise, sunset (tested) |
| `chatty_clock.py` | time zones and daylight saving (tested) |
| `chatty_hub.py` | finding Chatty's board (tested) |
| `chatty_art.py` | the 9x9 card pictures |
| `chatty_bits.py` | settings, a millisecond clock, dimming |
| `secrets_example.py` | the settings to add to your secrets.py |

The board keeps its own `fonts/` and `moon/` folders from the Moon Phase Clock. The
original's startup splash images are not used. Libraries from the Adafruit bundle that
matches the board's CircuitPython: `adafruit_minimqtt`, `adafruit_connection_manager`,
`adafruit_ticks`, `adafruit_esp32spi`, `adafruit_requests`, `adafruit_display_text`,
`adafruit_bitmap_font`, `adafruit_lis3dh`, `adafruit_matrixportal`, `adafruit_portalbase`,
`adafruit_bus_device`, `neopixel`.

## On a computer

    python3 tests/test_matrix_node.py                         # runs it on stand-ins (no packages)
    python3 scripts/preview_matrix.py out [fonts_dir]         # pictures of the panel

`sim/fake_circuitpython.py` holds the stand-ins (not for the board).

Moon Phase Clock by Phil 'PaintYourDragon' Burgess for Adafruit Industries, MIT license.

## Putting it on the board

1. Back up the CIRCUITPY drive (copy it all to a folder on the computer).
2. Check `boot_out.txt` for the CircuitPython version and get the matching library bundle
   from https://circuitpython.org/libraries (the libraries above go in `lib`).
3. Copy every file in `CIRCUITPY/` to the top of the drive (it replaces `code.py`), except
   `secrets_example.py`. Keep the `fonts` and `moon` folders that are already there.
4. Add `timezone` and `mqtt_hosts` (Chatty's home address) to `secrets.py`, like
   `secrets_example.py`. Latitude and longitude are optional (moonrise / moonset, sunrise /
   sunset). `cards` is optional too.

Check it from Chatty's Pi: `mosquitto_sub -h localhost -t 'chatty/nodes/matrix/#' -v`
