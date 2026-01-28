# ESP32 PID Departure Board

A MicroPython project for displaying real-time public transportation departures on an ESP32 with an SH1106 OLED display. The board fetches live departure data from the Prague Integrated Transport (PID) Golemio API and displays it on a 128x64 monochrome OLED screen.

## Features

- **Real-time Departures**: Fetches live departure data from Prague public transport API
- **OLED Display**: Shows departures on a 128x64 SH1106 I2C OLED display
- **Auto WiFi Reconnection**: Automatically reconnects to WiFi if connection is lost
- **Czech Character "Support"**: Converts Czech diacritics to ASCII for display compatibility
- **Stop Name Abbreviation**: Shortens common stop name parts to fit on display
- **Multiple Transport Types**: Supports trams, buses, and metro (configurable)
- **Memory Management**: Includes garbage collection to prevent memory issues

## Hardware Requirements

- **ESP32 Development Board**
- **SH1106 OLED Display** (128x64, I2C)
- Jumper wires

### Wiring Diagram

Connect the SH1106 OLED display to the ESP32:

| SH1106 Pin | ESP32 Pin |
|------------|-----------|
| VCC        | 3.3V      |
| GND        | GND       |
| SCL        | GPIO 22   |
| SDA        | GPIO 21   |

This can be customized and also depends on your specific board - this config is for ESP32-WROOM.

## Software Requirements

Both can be installed using `pip install esptool mpremote`:

- `esptool` to flash MicroPython to your ESP32
- `mpremote` for uploading files to ESP32 with MicroPython running

## Installation

1. **Install MicroPython** on your ESP32 if not already installed:
   - Download the latest MicroPython firmware from [micropython.org](https://micropython.org/download/esp32/)
   - Connect your board to your computer and note serial port number of your board (further, I use COM12).
   - Flash it using `esptool`
     - hold "FLASH/BOOT" button and run `python -m esptool --chip esp32 --port COM12 erase_flash`
     - hold "FLASH/BOOT" button and run `python -m esptool --port COM12 --baud 460800 write_flash 0x1000 .\YOUR_DOWNLOADED_FIRMWARE.bin`

2. **Clone or download this repository**

3. **Get a Golemio API Token**:
   - Visit [api.golemio.cz](https://api.golemio.cz/api-keys)
   - Register and obtain your API access token
   
4. **Configure your secrets** in `secrets.py`:
   ```python
   WIFI_SSID = "your_wifi_ssid"
   WIFI_PASSWORD = "your_wifi_password"
   GOLEMIO_TOKEN = "your_golemio_api_token"
   ```

5. **Configure your stop** in `departure_board.py`:
   ```python
   STOP_ID = "58759"  # Replace with your stop ID
   
   ```
   - Find stop ID in [JSON](https://data.pid.cz/stops/json/stops.json) - use the `cis` value

6. **Get SH1106 driver**
   - download `sh1106.py` file from [SH1106](https://github.com/robert-hh/SH1106) and place it in the same folder.

7. **Upload files to ESP32**:
   ```bash
   mpremote connect COM12 cp departure_board.py :main.py
   mpremote connect COM12 cp secrets.py :secrets.py
   mpremote connect COM12 cp sh1106.py :sh1106.py
   ```

8. **Restart the board**:
   ```bash
   mpremote connect COM12
   press CTRL+D
   ```

9. **See your departures**
  - Departures should be visible in the display as well as in the `mpremote` console, together with come debugging info.

## Configuration

### Stop ID
Change the `STOP_ID` variable in `departure_board.py` to your desired stop:
```python
STOP_ID = "58820"  # Muzeum
```

### Display Limit
Adjust how many departures to display:
```python
DISPLAY_LIMIT = 7  # Number of departures to show (max 7 for 64px display)
```

### Update Interval
Change the refresh rate in the main loop (default is 15 seconds):
```python
UPDATE_INTERVAL = 30
```

### Filter by Transport Type
Uncomment this line in `parse_departures()` to show only trams:
```python
if departure.get("route", {}).get("type") != 0:  # Only trams
    continue
```

## Display Format

The display shows departures in the following format:
```
22 Zahradni Me<1
19 Pankrac    <1
22 Nadrazi Hos 1
22 Bila Hora   1
19 Depo Hostiv 2
6  Kubanske na 4
124Zelivskeho  4
```

The columns are:

- **LINE**: Route number (3 characters)
- **DESTINATION**: Final destination (11 characters, truncated)
- **MIN**: Minutes until departure (2 characters)

## Files

- **`departure_board.py`**: Main application code
- **`secrets.py`**: WiFi credentials and API token (not committed to git)
- **`README.md`**: This file


**Note**: Remember to keep your `secrets.py` file private and never commit it to version control with real credentials.
