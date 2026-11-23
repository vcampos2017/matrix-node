# Copy the lines you need into secrets.py on the CIRCUITPY drive (keep your own
# ssid and password there). secrets.py never goes into the repo.
secrets = {
    "ssid": "HomeWiFi",                 # your WiFi name
    "password": "your-wifi-password",
    "timezone": "America/New_York",     # or "-07:00"; see chatty_clock.py for the names
    "latitude": 40.0,                   # optional: moonrise / moonset (stays on the board)
    "longitude": -100.0,
    "mqtt_hosts": "192.168.1.x",        # Chatty's home address (on Chatty: hostname -I)
    # The card library: which screens it rotates through and for how many seconds each
    # (chatty_cards.py lists them). A Tornado Warning always takes over, whatever this says.
    "cards": "clock:20, news, tide:8, clock:20, news, greenhouse:6, trend:6, roll:8, clock:20, news, sun:6",
    # Tides come from Chatty: set CHATTY_TIDE_STATION in her /etc/chatty/secrets.env.
    # "rotation": 0,                  # 0 / 90 / 180 / 270: skips the tilt sensor (saves memory)
    # "node_name": "matrix",
    # "twelve_hour": True,
    # "night_start": 22, "night_end": 7,
    # "night_red": True,          # dim red at night (False = just dimmer)
}
