# E-Paper Display Setup Guide

## Hardware Connection ✓

Your DESPI-C02 is correctly connected:

```
DESPI-C02 Pin    →  Raspberry Pi Zero Pin
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
3.3V             →  Pin 1 (3.3V)
GND              →  Pin 6 (GND)
SDI              →  Pin 19 — GPIO10 (MOSI)
SCK              →  Pin 23 — GPIO11 (SCLK)
CS               →  Pin 24 — GPIO8 (CE0)
D/C              →  Pin 22 — GPIO25
RES              →  Pin 18 — GPIO24
BUSY             →  Pin 16 — GPIO23
```

## Software Setup

### Step 1: Enable SPI Interface

On your Raspberry Pi Zero, enable SPI:

```bash
sudo raspi-config
```

Navigate to: **Interface Options** → **SPI** → **Yes**

Or enable directly:

```bash
sudo sed -i 's/#dtparam=spi=on/dtparam=spi=on/' /boot/config.txt
sudo reboot
```

### Step 2: Install Required Packages

#### For Debian Trixie / Bookworm and newer:

```bash
sudo apt-get update
sudo apt-get install -y python3-pip python3-pil python3-numpy python3-rpi.gpio python3-spidev python3-setuptools git fonts-dejavu-core
```

**Note:** Debian Trixie uses PEP 668 externally-managed-environment protection. Use system packages (python3-rpi.gpio, python3-spidev) instead of pip to avoid conflicts.

#### For older Debian/Raspbian versions:

```bash
sudo apt-get update
sudo apt-get install -y python3-pip python3-pil python3-numpy git
pip3 install RPi.GPIO spidev
```

#### Alternative: Using Virtual Environment (if needed):

If you need packages not available via apt:

```bash
python3 -m venv ~/epaper-env
source ~/epaper-env/bin/activate
pip install RPi.GPIO spidev pillow numpy
```

### Step 3: Install E-Paper Library

#### Option A: Install using pip (Recommended for Debian Trixie)

```bash
cd ~
git clone https://github.com/waveshare/e-Paper.git
cd e-Paper/RaspberryPi_JetsonNano/python/
sudo pip3 install . --break-system-packages
```

**Note:** The `--break-system-packages` flag is needed on Debian Trixie. This is safe for this library.

#### Option B: Copy library to your project directory (Easiest, No Installation)

```bash
cd ~
git clone https://github.com/waveshare/e-Paper.git
cd e-Paper/RaspberryPi_JetsonNano/python/
cp -r lib/waveshare_epd ~/odjezdova_tabule/
```

Then run your script from the project directory. **This is the simplest method!**

#### Option C: Install to user directory (Old method, deprecated)

```bash
cd ~/e-Paper/RaspberryPi_JetsonNano/python/
python3 setup.py install --user
```

**Warning:** This method is deprecated and may not work on newer systems.

### Step 4: Configure for Your Display

**Your Display: 2.6" NEWTON BWR (Black-White-Red) ESL Display**

The test script is already configured for your display! It will try these drivers:
1. `epd2in66b` - 2.66" BWR (296x152) - **Recommended**
2. `epd2in7b` - 2.7" BWR (176x264) - Fallback option

#### If you need to test other resolutions:

For 2.6" displays, common resolutions are:
- 296x152 (most common for 2.6")
- 296x128

Edit the top of `test_epaper.py` to try different settings:

```python
# Try different resolutions if needed
DISPLAY_WIDTH = 296
DISPLAY_HEIGHT = 152  # or try 128 if 152 doesn't work
```

#### About BWR (Three-Color) Displays:

Your display supports Black, White, AND Red. The script creates two image layers:
- **Black layer**: For black text/graphics
- **Red layer**: For red highlights

This makes it perfect for shelf labels with price highlights!

## Running the Test

### Display "Hello World":

```bash
python3 test_epaper.py
```

### Clear the display:

```bash
python3 test_epaper.py clear
```

## Troubleshooting

### SPI not enabled
- Run `ls /dev/spi*` - you should see `/dev/spidev0.0` and `/dev/spidev0.1`
- If not, check SPI is enabled in raspi-config

### Import errors
- Make sure you installed the waveshare_epd library
- Check that the module name matches your display model

### Display not responding
- Verify all pin connections are secure
- Check that the display is powered (3.3V)
- Some displays require a full power cycle after first connection

### GPIO permissions
If you get GPIO permission errors:

```bash
sudo adduser $USER gpio
# Then log out and log back in
```

## Next Steps

Once the test works, you can:
1. Create custom graphics using PIL (Python Imaging Library)
2. Display dynamic content (time, weather, etc.)
3. Implement partial refresh (if your display supports it)
4. Create your departure board application for the e-paper display

## E-Paper Display Notes

- E-paper displays retain their image without power
- Refresh rates are slower than LCDs (typically 10-20 seconds for BWR displays)
- **BWR displays are SLOWER** than BW displays due to the third color
- Displays should not be refreshed too frequently (can cause ghosting)
- ESL displays are designed for infrequent updates (perfect for departure boards!)
- Most e-paper displays work best at room temperature (0-50°C)
- Red color updates may take longer to settle

### ESL Display Specific Notes:

Your 2.6" NEWTON BWR is an Electronic Shelf Label display:
- Originally designed for retail price tags
- Very low power consumption
- Excellent sunlight readability
- Perfect for departure boards and information displays
- Three-color capability allows you to highlight important info in red
