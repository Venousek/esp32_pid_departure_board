import network
import urequests
import time
import gc
from machine import Pin, I2C
import sh1106
import time

# WiFi credentials and API token
from secrets import WIFI_SSID, WIFI_PASSWORD, GOLEMIO_TOKEN
# WIFI_SSID = "WIFI_SSID"
# WIFI_PASSWORD = "WIFI_PASSWORD"
# GOLEMIO_TOKEN = "GOLEMIO_TOKEN"

STOP_ID = "58759"  # Anděl
LIMIT = 7
DISPLAY_LIMIT = 7
UPDATE_INTERVAL = 15  # seconds

# API URL and token
URL = f"https://api.golemio.cz/v2/pid/departureboards?cisIds={STOP_ID}&minutesBefore=0&minutesAfter=60&limit={LIMIT}"

# Mapping for Czech/European accented characters to ASCII
DIACRITICS_MAP = {
    "á": "a",
    "č": "c",
    "ď": "d",
    "é": "e",
    "ě": "e",
    "í": "i",
    "ň": "n",
    "ó": "o",
    "ř": "r",
    "š": "s",
    "ť": "t",
    "ú": "u",
    "ů": "u",
    "ý": "y",
    "ž": "z",
    "Á": "A",
    "Č": "C",
    "Ď": "D",
    "É": "E",
    "Ě": "E",
    "Í": "I",
    "Ň": "N",
    "Ó": "O",
    "Ř": "R",
    "Š": "S",
    "Ť": "T",
    "Ú": "U",
    "Ů": "U",
    "Ý": "Y",
    "Ž": "Z",
    "ä": "a",
    "ö": "o",
    "ü": "u",
    "ß": "ss",
    "Ä": "A",
    "Ö": "O",
    "Ü": "U",
}


def to_ascii(text):
    """Convert accented characters to ASCII equivalents."""
    result = []
    for char in text:
        result.append(DIACRITICS_MAP.get(char, char))
    return "".join(result)


def shorten_stop_name(name):
    """Shorten common stop name parts."""
    replacements = {
        "Namesti": "Nam.",
        "namesti": "nam.",
        "Sidliste": "S.",
        "Nemocnice": "Nem.",
        "Zastavka": "Zast.",
    }
    for long, short in replacements.items():
        name = name.replace(long, short)
    return name


def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if not wlan.isconnected():
        print("Connecting to WiFi...")
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)

        timeout = 20  # seconds
        start = time.time()
        while not wlan.isconnected():
            if time.time() - start > timeout:
                print("WiFi connection timeout!")
                return None
            time.sleep(0.5)

    print("Connected! IP:", wlan.ifconfig()[0])
    return wlan


def ensure_wifi():
    """Check WiFi connection and reconnect if needed."""
    wlan = network.WLAN(network.STA_IF)
    if not wlan.isconnected():
        print("WiFi disconnected, reconnecting...")
        return connect_wifi()
    return wlan


def parse_departures(data):
    """Parse departures from API response."""
    departures = data.get("departures", [])
    parsed = []
    for departure in departures:
        # if departure.get("route", {}).get("type") != 0:  # Only trams
        #     continue
        line = departure.get("route", {}).get("short_name", "N/A")
        destination = to_ascii(departure.get("trip", {}).get("headsign", "N/A"))
        destination = shorten_stop_name(destination)
        departure_in_minutes = departure.get("departure_timestamp", {}).get("minutes", "N/A")
        text = f"{line:<3}{destination:<11.11}{departure_in_minutes:>2}"
        parsed.append(text)
    return parsed


i2c = I2C(scl=Pin(22), sda=Pin(21), freq=400000)
display = sh1106.SH1106_I2C(128, 64, i2c, None, 0x3C, rotate=180)
display.sleep(False)
display.fill(0)
display.text("Connecting...", 0, 0, 1)
display.show()

# Connect to WiFi
connect_wifi()

HEADERS = {
    "accept": "application/json",
    "Accept-Encoding": "identity",
    "X-Access-Token": GOLEMIO_TOKEN,
}

while True:
    gc.collect()
    print("Free memory:", gc.mem_free())
    response = None
    try:
        ensure_wifi()
        print("Fetching departures...")
        response = urequests.get(URL, headers=HEADERS, timeout=10)
        print("Free memory after fetching:", gc.mem_free())
        print("Response status:", response.status_code)
        data = response.json()
        response.close()
        response = None
        gc.collect()

        display.fill(0)
        print("\n")
        departures = parse_departures(data)[:DISPLAY_LIMIT]
        for i, departure in enumerate(departures):
            print(departure)
            display.text(departure, 0, i * 9, 1)
        display.show()
        del data, departures
    except Exception as e:
        print("Error:", e)
        display.fill(0)
        display.text("Error, retrying...", 0, 0, 1)
        display.text(str(e), 0, 10, 1)
        display.show()
    finally:
        if response:
            try:
                response.close()
            except:
                pass
        gc.collect()
        time.sleep(1)  # Give socket time to fully release

    time.sleep(UPDATE_INTERVAL)
