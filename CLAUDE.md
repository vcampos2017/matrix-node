# Matrix node: notes for coding sessions

- Owner: Vincent (GitHub vcampos2017). Part of the Chatty node network (main repo
  vcampos2017/chatty-node: read its CLAUDE.md for the MQTT topics and the network's rules).
- Hardware: Adafruit Matrix Portal M4 (SAMD51 + ESP32 WiFi co-processor, LIS3DH, UP/DOWN
  buttons) driving a 64x32 HUB75 panel that stands on its side (32 wide x 64 tall).
- Install: Vincent copies the files in `CIRCUITPY/` to the board's CIRCUITPY drive over USB
  (Mu editor / Finder on a Mac, or a Windows PC). Give plain copy steps. Libraries must come
  from the Adafruit bundle that matches the board's CircuitPython major version.
- Started from Adafruit's Moon Phase Clock (Phil Burgess, MIT): keep that notice; never ship
  its startup splash images. The board keeps its own `fonts/` and `moon/` folders.
- Privacy: no WiFi names, real addresses, location or time zone of the owner in code, docs,
  tests, commits or PRs. Settings live in `secrets.py` on the board only (placeholders in
  `secrets_example.py`).
- Read-only node: it listens to Chatty's news and posts its own heartbeat
  (`chatty/nodes/matrix/status`, last will offline) and moon data; it never sends commands.
- RAM is small (192 KB): keep modules split (CircuitPython compiles each file in RAM), avoid
  big strings and lists, use `time.monotonic_ns()` (floats lose precision after days).
- Files: `chatty_matrix.py` app, `chatty_library.py` (mixin: the card rotation, tides),
  `chatty_screen.py` display, `chatty_panels.py` (roll call, bolt/ripple, sunrise picture,
  WiFi bars), `chatty_net.py` WiFi + MQTT + `get_json`, `chatty_news.py` / `chatty_cards.py` /
  `chatty_tide.py` / `chatty_moon.py` / `chatty_clock.py` / `chatty_hub.py` pure Python
  (tested on a computer), `chatty_art.py` icons, `chatty_bits.py` helpers. Keep each file
  under about 15 KB (the board compiles each one in RAM).
- Card library (2026-11-18): `cards` in secrets.py = order + seconds (clock, news, tide,
  greenhouse, roll, sun); empty cards are skipped; a Tornado Warning beats everything. Tides
  from NOAA CO-OPS (free, no key; `tide_station`, the board fetches every 6 h). The station
  number lives only in secrets.py.
- Tests: `python3 tests/test_matrix_node.py` (stand-ins in `sim/`, no packages). Pictures:
  `python3 scripts/preview_matrix.py out [fonts_dir]` (needs Pillow).
