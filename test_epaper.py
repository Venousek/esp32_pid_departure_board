#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
E-Paper Driver for 2.6" NEWTON BWR ESL Display on DESPI-C02

Confirmed configuration:
  - Controller: SSD1619A
  - Resolution: 184 x 360 (width x height)
  - Colors: Black, White, Red (BWR)
  - Interface: SPI mode 0, 2 MHz

Pin connections (DESPI-C02 -> Raspberry Pi Zero):
  3.3V -> Pin 1       GND  -> Pin 6
  SDI  -> GPIO10      SCK  -> GPIO11
  CS   -> GPIO8       D/C  -> GPIO25
  RES  -> GPIO24      BUSY -> GPIO23

RESE switch: 2.2
"""

import time

import spidev
from PIL import Image, ImageDraw, ImageFont

import lgpio


# ── Display configuration ────────────────────────────────────────────────────
WIDTH = 184
HEIGHT = 360

RST_PIN = 24
DC_PIN = 25
BUSY_PIN = 23

SPI_BUS = 0
SPI_DEV = 0
SPI_SPEED = 2000000


class SSD1619Display:
    """Driver for SSD1619A e-paper controller (184x360 BWR) via DESPI-C02."""

    def __init__(self, width=WIDTH, height=HEIGHT):
        self.width = width
        self.height = height
        self.buf_size = (width // 8) * height
        self.spi = None
        self._h = None

    # ── Low-level SPI ────────────────────────────────────────────────────

    def send_command(self, cmd):
        lgpio.gpio_write(self._h, DC_PIN, 0)
        self.spi.writebytes([cmd])

    def send_data(self, data):
        lgpio.gpio_write(self._h, DC_PIN, 1)
        self.spi.writebytes([data])

    def send_data_bulk(self, data):
        lgpio.gpio_write(self._h, DC_PIN, 1)
        chunk = 4096
        for i in range(0, len(data), chunk):
            self.spi.writebytes(data[i : i + chunk])

    # ── Init / Reset ─────────────────────────────────────────────────────

    def init(self):
        """Initialize GPIO and SPI (call once)."""
        self._h = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_output(self._h, RST_PIN, 1)
        lgpio.gpio_claim_output(self._h, DC_PIN, 0)
        lgpio.gpio_claim_input(self._h, BUSY_PIN)

        self.spi = spidev.SpiDev()
        self.spi.open(SPI_BUS, SPI_DEV)
        self.spi.max_speed_hz = SPI_SPEED
        self.spi.mode = 0b00
        self.spi.no_cs = False

    def _init_controller(self):
        """Full hardware reset + controller register init."""
        lgpio.gpio_write(self._h, RST_PIN, 1)
        time.sleep(0.05)
        lgpio.gpio_write(self._h, RST_PIN, 0)
        time.sleep(0.01)
        lgpio.gpio_write(self._h, RST_PIN, 1)
        time.sleep(0.2)

        self.send_command(0x12)  # SW reset
        time.sleep(0.5)

        self.send_command(0x01)  # Driver Output Control
        self.send_data((self.height - 1) & 0xFF)
        self.send_data(((self.height - 1) >> 8) & 0xFF)
        self.send_data(0x00)

        self.send_command(0x11)  # Data Entry Mode
        self.send_data(0x03)

        self.send_command(0x44)  # RAM X range
        self.send_data(0x00)
        self.send_data((self.width // 8 - 1) & 0xFF)

        self.send_command(0x45)  # RAM Y range
        self.send_data(0x00)
        self.send_data(0x00)
        self.send_data((self.height - 1) & 0xFF)
        self.send_data(((self.height - 1) >> 8) & 0xFF)

        self.send_command(0x3C)  # Border waveform
        self.send_data(0x01)

        self.send_command(0x18)  # Temperature sensor
        self.send_data(0x80)

    def _set_cursor(self, x=0, y=0):
        self.send_command(0x4E)
        self.send_data(x & 0xFF)
        self.send_command(0x4F)
        self.send_data(y & 0xFF)
        self.send_data((y >> 8) & 0xFF)

    def _refresh(self):
        self.send_command(0x22)
        self.send_data(0xF7)
        self.send_command(0x20)

        # Wait for BUSY pin: HIGH=busy, LOW=ready
        print("  Refreshing...", end="", flush=True)
        time.sleep(0.2)
        start = time.time()
        while lgpio.gpio_read(self._h, BUSY_PIN) == 1:
            time.sleep(0.1)
            if time.time() - start > 30:
                print(f" timeout after 30s!")
                return
        print(f" done ({time.time() - start:.1f}s)")

    # ── Image packing ────────────────────────────────────────────────────

    def _pack_image(self, image):
        """Convert PIL mode '1' image to packed 1-bit bytes (MSB first)."""
        pixels = image.load()
        buf = []
        for y in range(self.height):
            for x_byte in range(self.width // 8):
                byte = 0
                for bit in range(8):
                    x = x_byte * 8 + bit
                    if pixels[x, y] != 0:
                        byte |= 0x80 >> bit
                buf.append(byte)
        return buf

    # ── Public API ───────────────────────────────────────────────────────

    def clear(self, color=0xFF):
        """Fill display: 0xFF=white, 0x00=black."""
        print(f"  Clearing ({'white' if color == 0xFF else 'black'})...")
        self._init_controller()
        self._set_cursor(0, 0)
        self.send_command(0x24)
        self.send_data_bulk([color] * self.buf_size)
        self.send_command(0x26)
        self.send_data_bulk([0x00] * self.buf_size)
        self._refresh()

    def display(self, image_bw, image_red=None):
        """Write PIL Image(s) to the display and refresh.

        Args:
            image_bw:  PIL Image mode '1', size (184,360) — 0=black, 255=white
            image_red: PIL Image mode '1', size (184,360) — 0=red, 255=no-red
        """
        self._init_controller()
        self._set_cursor(0, 0)

        bw_bytes = self._pack_image(image_bw)
        self.send_command(0x24)
        self.send_data_bulk(bw_bytes)

        if image_red:
            red_packed = self._pack_image(image_red)
            red_bytes = [~b & 0xFF for b in red_packed]
        else:
            red_bytes = [0x00] * self.buf_size

        self.send_command(0x26)
        self.send_data_bulk(red_bytes)
        self._refresh()

    def sleep(self):
        """Enter deep sleep mode."""
        self.send_command(0x10)
        self.send_data(0x01)

    def cleanup(self):
        """Release resources."""
        if self.spi:
            self.spi.close()
        if self._h is not None:
            lgpio.gpiochip_close(self._h)


# ── Demo ─────────────────────────────────────────────────────────────────────


def main():
    import datetime

    print("=" * 60)
    print("E-Paper Test — SSD1619 @ 184x360 BWR")
    print("=" * 60)

    display = SSD1619Display()

    try:
        print("\nInitializing...")
        display.init()

        # Find a TrueType font
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
        font_path = None
        for fp in font_paths:
            import os

            if os.path.exists(fp):
                font_path = fp
                break

        if font_path:
            print(f"  Using font: {font_path}")
            font_big = ImageFont.truetype(font_path, 36)
            font_med = ImageFont.truetype(font_path, 18)
            font_sm = ImageFont.truetype(font_path, 14)
        else:
            print("  WARNING: No TrueType fonts found")
            font_big = ImageFont.load_default()
            font_med = font_big
            font_sm = font_big

        for i in range(1, 6):
            now = datetime.datetime.now()
            print(f"\n--- Refresh {i}/5 at {now.strftime('%H:%M:%S')} ---")

            img_bw = Image.new("1", (WIDTH, HEIGHT), 255)
            img_red = Image.new("1", (WIDTH, HEIGHT), 255)
            draw_bw = ImageDraw.Draw(img_bw)
            draw_red = ImageDraw.Draw(img_red)

            # Border
            draw_bw.rectangle([(0, 0), (WIDTH - 1, HEIGHT - 1)], outline=0, width=2)

            # Time (big, in black)
            draw_bw.text((10, 10), now.strftime("%H:%M"), font=font_big, fill=0)

            # Seconds (red)
            draw_red.text((10, 55), now.strftime(":%S"), font=font_med, fill=0)

            # Separator
            draw_bw.line([(5, 85), (WIDTH - 5, 85)], fill=0, width=1)

            # Date
            draw_bw.text((10, 95), now.strftime("%d.%m.%Y"), font=font_med, fill=0)
            draw_bw.text((10, 120), now.strftime("%A"), font=font_sm, fill=0)

            # Separator
            draw_bw.line([(5, 145), (WIDTH - 5, 145)], fill=0, width=1)

            # Refresh counter (red)
            draw_red.text((10, 155), f"Refresh {i}/5", font=font_med, fill=0)

            # Info
            draw_bw.text((10, 185), f"SSD1619 {WIDTH}x{HEIGHT}", font=font_sm, fill=0)
            draw_bw.text((10, 205), "DESPI-C02 BWR", font=font_sm, fill=0)

            display.display(img_bw, img_red)

            if i < 5:
                print("  Waiting 10s before next refresh...")
                time.sleep(10)

        display.sleep()
        print("\nTEST COMPLETE — 5 refreshes done")

    except KeyboardInterrupt:
        print("\nInterrupted!")
        display.sleep()
    except Exception as e:
        print(f"\nError: {e}")
        import traceback

        traceback.print_exc()
    finally:
        display.cleanup()


if __name__ == "__main__":
    main()
