"""The Matrix node's WiFi (the ESP32 co-processor) and its MQTT link to Chatty's board.

Works with the older libraries (adafruit_esp32spi sockets) and the newer ones
(adafruit_connection_manager). Chatty's board is found with chatty_hub.
"""
# pylint: disable=import-error,broad-except
import gc
import json
import time

import board
import busio
import microcontroller
from digitalio import DigitalInOut

import chatty_hub as hub
from chatty_bits import setting, now_ms

MQTT_LOOP_S = 0.25
HUB_SAVE_GAP_S = 600
TOPICS = ("chatty/hub", "chatty/clock", "chatty/tides", "chatty/alerts/active", "chatty/forecast/rain",
          "chatty/nodes/+/status", "chatty/nodes/rain/data",
          "chatty/nodes/lightning/data", "chatty/nodes/greenhouse/data")


class Net:
    """The ESP32 WiFi co-processor, used directly (no adafruit_matrixportal.network)."""

    def __init__(self, ssid, password):
        self.ssid, self.password = ssid, password
        self.esp = None
        self.fails = 0

    def setup(self):
        from adafruit_esp32spi import adafruit_esp32spi
        cs = DigitalInOut(board.ESP_CS)
        busy = DigitalInOut(board.ESP_BUSY)
        reset = DigitalInOut(board.ESP_RESET)
        spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
        self.esp = adafruit_esp32spi.ESP_SPIcontrol(spi, cs, busy, reset)

    def connected(self):
        try:
            return bool(self.esp and self.esp.is_connected)
        except Exception:
            return False

    def connect(self):
        if self.connected():
            return True
        if not self.ssid:
            print("No WiFi name (ssid) in secrets.py")
            return False
        try:
            if self.fails and self.fails % 4 == 0:
                print("Resetting the WiFi chip")
                self.esp.reset()
            print("Joining WiFi...")
            self.esp.connect_AP(self.ssid, self.password)
        except Exception as ex:
            print("WiFi didn't connect:", repr(ex))
        ok = self.connected()
        self.fails = 0 if ok else self.fails + 1
        return ok

    def pool(self):
        """(socket pool, ssl context) for newer libraries, or (None, None)."""
        try:
            import adafruit_connection_manager as acm
            return acm.get_radio_socketpool(self.esp), acm.get_radio_ssl_context(self.esp)
        except ImportError:
            return None, None

    def utc_now(self):
        """UTC from the WiFi chip's own time server, or None."""
        # The WiFi chip says 0 until it has heard from its time server. No web fallback
        # (the web library doesn't fit next to MQTT): Chatty posts the time on
        # chatty/clock every minute, and that sets the clock too.
        for _ in range(2):
            try:
                t = self.esp.get_time()
                t = t[0] if isinstance(t, (tuple, list)) else t
                if int(t) > 1700000000:
                    return int(t)
            except Exception:
                pass
            time.sleep(0.5)
        print("No time from the WiFi chip yet; waiting for Chatty's clock")
        return None

    def rssi(self):
        """WiFi signal strength in dBm (about -30 great .. -90 barely), or None.
        Newer esp32spi libraries have it in ap_info, older ones as esp.rssi."""
        if not self.connected():
            return None
        for getter in (lambda e: e.ap_info.rssi, lambda e: e.rssi):
            try:
                value = getter(self.esp)
                value = value() if callable(value) else value
                value = int(value)
                if value < 0:
                    return value
            except Exception:
                pass
        return None


def free():
    try:
        gc.collect()
        return gc.mem_free()
    except Exception:
        return -1


# --------------------------------------------------------------------------- MQTT

class Link:
    """The MQTT connection to Chatty's board, found with chatty_hub."""

    def __init__(self, net, name, on_message):
        self.net, self.name, self.on_message = net, name, on_message
        self.client, self.host = None, None
        self.port = int(setting("mqtt_port", 1883))
        self.configured = setting("mqtt_hosts", setting("mqtt_host", ""))
        self.last_good, self.note = self._load()
        self.note_saved_at = -HUB_SAVE_GAP_S
        try:
            uid = microcontroller.cpu.uid
            self.client_id = name + "-" + "".join("%02x" % b for b in uid[-4:])
        except Exception:
            self.client_id = name + "-node"

    @staticmethod
    def _load():
        try:
            return hub.unpack(microcontroller.nvm[0:hub.MAX_SAVE])
        except Exception:
            return None, None

    def _save(self):
        try:
            data = hub.pack(self.last_good, self.note)
            if bytes(microcontroller.nvm[0:len(data)]) != data:
                microcontroller.nvm[0:len(data)] = data
        except Exception as ex:
            print("Couldn't keep the hub note:", repr(ex))

    @staticmethod
    def mqtt_lib():
        """Loaded at start-up (chatty_matrix calls this before anything else uses much
        memory), so the big MQTT library finds room in one piece."""
        import adafruit_minimqtt.adafruit_minimqtt as MQTT
        return MQTT

    def status_topic(self):
        return "chatty/nodes/" + self.name + "/status"

    def _client(self, host):
        MQTT = self.mqtt_lib()
        pool, ssl = self.net.pool()
        base = {"broker": host, "port": self.port, "client_id": self.client_id, "keep_alive": 90}
        if pool is not None:
            base.update({"socket_pool": pool, "ssl_context": ssl, "is_ssl": False})
        else:
            import adafruit_esp32spi.adafruit_esp32spi_socket as sock
            MQTT.set_socket(sock, self.net.esp)
        for extra in ({"socket_timeout": MQTT_LOOP_S / 2, "connect_retries": 1},
                      {"socket_timeout": MQTT_LOOP_S / 2}, {}):
            kw = dict(base)
            kw.update(extra)
            try:
                return MQTT.MQTT(**kw)
            except TypeError:
                continue
        raise RuntimeError("this adafruit_minimqtt is too old")

    def connect(self):
        """Try each known address once. True when connected."""
        for host in hub.to_try(self.last_good, self.note, self.configured):
            gc.collect()
            try:
                print("Looking for Chatty at", host, "- free memory", free())
                client = self._client(host)
                client.will_set(self.status_topic(), json.dumps({"state": "offline"}), retain=True)
                client.on_message = self._message
                client.connect()
                for topic in TOPICS:
                    client.subscribe(topic)
                self.client, self.host = client, host
                if host != self.last_good:
                    self.last_good = host
                    self._save()
                print("Connected to Chatty's board at", host, "- free memory", free())
                return True
            except Exception as ex:
                print("  no:", repr(ex))
                self._close(client)
                client = None
                gc.collect()
        return False

    def _close(self, client):
        """After a failed try: close its socket, or each try keeps one (and its memory)."""
        try:
            if client:
                client.disconnect()
        except Exception:
            pass
        try:
            import adafruit_connection_manager as acm
            acm.connection_manager_close_all(release_references=True)
        except Exception:
            pass

    def _message(self, client, topic, message):
        if topic == "chatty/hub":
            note = hub.note_from(message)
            if note and note != self.note:
                self.note = note
                mono = now_ms() // 1000
                if mono - self.note_saved_at >= HUB_SAVE_GAP_S:
                    self.note_saved_at = mono
                    self._save()
            return
        self.on_message(topic, message)

    def loop(self):
        if not self.client:
            return False
        try:
            try:
                self.client.loop(timeout=MQTT_LOOP_S)
            except TypeError:
                self.client.loop()
            return True
        except Exception as ex:
            print("Lost Chatty's board:", repr(ex))
            self.drop()
            return False

    def publish(self, topic, body):
        if not self.client:
            return False
        try:
            self.client.publish(topic, json.dumps(body), retain=True)
            return True
        except Exception as ex:
            print("Couldn't post", topic, repr(ex))
            self.drop()
            return False

    def drop(self):
        try:
            if self.client:
                self.client.disconnect()
        except Exception:
            pass
        self.client = None
