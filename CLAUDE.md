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
  WiFi bars), `chatty_net.py` WiFi + MQTT, `chatty_news.py` / `chatty_cards.py` /
  `chatty_tide.py` / `chatty_moon.py` / `chatty_clock.py` / `chatty_hub.py` pure Python
  (tested on a computer), `chatty_art.py` icons, `chatty_bits.py` helpers. Keep each file
  under about 15 KB (the board compiles each one in RAM).
- Card library (2026-11-18): `cards` in secrets.py = order + seconds (clock, news, tide,
  greenhouse, roll, sun); empty cards are skipped; a Tornado Warning beats everything. No web
  requests on the board (2026-11-18: adafruit_requests + HTTPS left too little RAM for MQTT):
  Chatty fetches NOAA tides (chatty-node `node_feed.py`, CHATTY_TIDE_STATION in her env)
  and posts retained `chatty/tides`, plus `chatty/clock` every minute for when the ESP32's
  time server doesn't answer. Startup prints free memory.
- Tests: `python3 tests/test_matrix_node.py` (stand-ins in `sim/`, no packages). Pictures:
  `python3 scripts/preview_matrix.py out [fonts_dir]` (needs Pillow).
- Memory (2026-11-19): with the card library the board had only ~9 KB free before WiFi
  (3.8 KB after), so MQTT couldn't connect. Trimmed: panel at 4 bit planes, bitmap_label
  (one bitmap per line, not a tile per letter), rgbmatrix direct, one 6x10 font object,
  "rotation" in secrets.py skips the accelerometer (its library is unloaded after use),
  failed MQTT tries close their socket. Startup prints free memory at each stage.
- Precompiled (2026-11-19, Vincent OK'd): `CIRCUITPY_MPY/` = code.py + chatty_*.mpy built
  with Adafruit's mpy-cross 10.3.2 (`bash scripts/build_mpy.sh <mpy-cross>`); Vincent copies
  that folder, not the .py files (a .py on the board wins over the .mpy). Rebuild after any
  .py change: a test compares `CIRCUITPY_MPY/sources.txt` with the sources.
- Text (2026-11-19): fonts + adafruit_display_text took ~48 KB on the board, so
  `chatty_text.py` replaced them: digits for the clock from helvB12/helvR10.bdf (only
  DIGITS), card/roll text in terminalio.FONT (in flash, no RAM), moonrise arrows drawn.
  Label keeps display_text's API (.text/.x/.y/.color/.bounding_box; y = middle of line).
