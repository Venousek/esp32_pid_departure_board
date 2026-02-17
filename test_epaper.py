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
import os

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

def _build_custom_lut(levels, g0, g1, g2, voltage):
    timing = list(g0) + list(g1) + list(g2) + [0x00] * (7 * 9)
    lut = list(levels) + timing + list(voltage)
    if len(lut) != 153:
        raise ValueError(f"Invalid LUT size: {len(lut)}")
    return lut


_LUT_BW_CUSTOM_A = _build_custom_lut(
    levels=[
        0x00,0x24,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x60,0x60,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x90,0x90,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x30,0x90,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
    ],
    g0=[0x05,0x00,0x00,0x00,0x00,0x00,0x01],
    g1=[0x02,0x00,0x00,0x00,0x00,0x00,0x00],
    g2=[0x01,0x00,0x00,0x00,0x00,0x00,0x00],
    voltage=[0x22,0x22,0x22,0x22,0x22,0x22,0x00,0x00,0x00],
)

_LUT_BW_CUSTOM_B = _build_custom_lut(
    levels=[
        0x00,0x14,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x40,0x40,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0xA0,0xA0,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x20,0xA0,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
    ],
    g0=[0x03,0x00,0x00,0x00,0x00,0x00,0x01],
    g1=[0x01,0x00,0x00,0x00,0x00,0x00,0x00],
    g2=[0x00,0x00,0x00,0x00,0x00,0x00,0x00],
    voltage=[0x22,0x22,0x22,0x22,0x22,0x22,0x00,0x00,0x00],
)


class SSD1619Display:
    """Driver for SSD1619A e-paper controller (184x360 BWR) via DESPI-C02."""

    def __init__(self, width=WIDTH, height=HEIGHT):
        if width % 8 != 0:
            raise ValueError("Display width must be divisible by 8")
        self.width = width
        self.height = height
        self.buf_size = (width // 8) * height
        self.spi = None
        self._h = None
        self.bw_partial_profile = "custom_a"

    # ── Low-level SPI ────────────────────────────────────────────────────

    def set_bw_partial_profile(self, profile):
        aliases = {
            "stable": "custom_a",
            "turbo": "custom_b",
            "custom_a": "custom_a",
            "custom_b": "custom_b",
            "otp": "otp",
        }
        mapped = aliases.get(profile)
        if mapped is None:
            raise ValueError("profile must be one of: custom_a, custom_b, otp")
        self.bw_partial_profile = mapped

    def _require_ready(self):
        if self.spi is None or self._h is None:
            raise RuntimeError("Display not initialized. Call init() first.")

    def send_command(self, cmd):
        self._require_ready()
        h = self._h
        spi = self.spi
        if h is None or spi is None:
            raise RuntimeError("Display not initialized. Call init() first.")
        lgpio.gpio_write(h, DC_PIN, 0)
        spi.writebytes([cmd])

    def send_data(self, data):
        self._require_ready()
        h = self._h
        spi = self.spi
        if h is None or spi is None:
            raise RuntimeError("Display not initialized. Call init() first.")
        lgpio.gpio_write(h, DC_PIN, 1)
        spi.writebytes([data])

    def send_data_bulk(self, data):
        self._require_ready()
        h = self._h
        spi = self.spi
        if h is None or spi is None:
            raise RuntimeError("Display not initialized. Call init() first.")
        lgpio.gpio_write(h, DC_PIN, 1)
        chunk = 4096
        for i in range(0, len(data), chunk):
            spi.writebytes(data[i : i + chunk])

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

    def _init_no_reset(self):
        """Re-configure controller registers without resetting panel RAM."""
        self._wait_busy_silent(5)

        self.send_command(0x01)
        self.send_data((self.height - 1) & 0xFF)
        self.send_data(((self.height - 1) >> 8) & 0xFF)
        self.send_data(0x00)

        self.send_command(0x11)
        self.send_data(0x03)

        self.send_command(0x44)
        self.send_data(0x00)
        self.send_data((self.width // 8 - 1) & 0xFF)

        self.send_command(0x45)
        self.send_data(0x00)
        self.send_data(0x00)
        self.send_data((self.height - 1) & 0xFF)
        self.send_data(((self.height - 1) >> 8) & 0xFF)

        self.send_command(0x3C)
        self.send_data(0x01)

        self.send_command(0x18)
        self.send_data(0x80)

    def _set_window(self, x_byte_start, x_byte_end, y_start, y_end):
        self.send_command(0x44)
        self.send_data(x_byte_start & 0xFF)
        self.send_data(x_byte_end & 0xFF)

        self.send_command(0x45)
        self.send_data(y_start & 0xFF)
        self.send_data((y_start >> 8) & 0xFF)
        self.send_data(y_end & 0xFF)
        self.send_data((y_end >> 8) & 0xFF)

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
        self._wait_busy("BWR refresh", timeout=35)

    def _refresh_bw(self):
        """B/W-only partial refresh path using custom LUT or OTP mode."""
        if self.bw_partial_profile == "otp":
            return self._refresh_bw_otp()

        if not self._wait_busy_silent(8, poll_interval=0.02):
            print("  B/W refresh skipped: controller stayed busy before update")
            return False

        self.send_command(0x3C)
        self.send_data(0x80)

        self.send_command(0x32)
        lut = _LUT_BW_CUSTOM_B if self.bw_partial_profile == "custom_b" else _LUT_BW_CUSTOM_A
        self.send_data_bulk(lut)

        self.send_command(0x22)
        self.send_data(0xC0)
        self.send_command(0x20)
        if not self._wait_busy_silent(8, poll_interval=0.02):
            print("  B/W refresh skipped: power-on step timeout")
            return False

        self.send_command(0x22)
        self.send_data(0x04)
        self.send_command(0x20)
        if not self._wait_busy("B/W refresh", timeout=25, pre_delay=0.02, poll_interval=0.02):
            self._wait_busy_silent(35, poll_interval=0.02)
            return False

        self.send_command(0x22)
        self.send_data(0x03)
        self.send_command(0x20)
        if not self._wait_busy_silent(10, poll_interval=0.02):
            return False
        return True

    def _refresh_bw_otp(self):
        if not self._wait_busy_silent(8, poll_interval=0.02):
            print("  B/W refresh skipped: controller stayed busy before update")
            return False

        self.send_command(0x22)
        self.send_data(0xF8)
        self.send_command(0x20)
        if not self._wait_busy_silent(10, poll_interval=0.02):
            print("  B/W refresh skipped: OTP power-on timeout")
            return False

        self.send_command(0x22)
        self.send_data(0xCC)
        self.send_command(0x20)
        if not self._wait_busy("B/W refresh (OTP)", timeout=25, pre_delay=0.02, poll_interval=0.02):
            self._wait_busy_silent(35, poll_interval=0.02)
            return False
        return True

    def _wait_busy(self, label="Refreshing", timeout=30, pre_delay=0.2, poll_interval=0.1):
        self._require_ready()
        h = self._h
        if h is None:
            raise RuntimeError("Display not initialized. Call init() first.")

        print(f"  {label}...", end="", flush=True)
        if pre_delay > 0:
            time.sleep(pre_delay)
        start = time.monotonic()
        while lgpio.gpio_read(h, BUSY_PIN) == 1:
            time.sleep(poll_interval)
            elapsed = time.monotonic() - start
            if elapsed > timeout:
                print(f" timeout after {timeout}s!")
                return False
        elapsed = time.monotonic() - start
        print(f" done ({elapsed:.1f}s)")
        return True

    def _wait_busy_silent(self, timeout=5, poll_interval=0.05):
        self._require_ready()
        h = self._h
        if h is None:
            raise RuntimeError("Display not initialized. Call init() first.")

        start = time.monotonic()
        while lgpio.gpio_read(h, BUSY_PIN) == 1:
            time.sleep(poll_interval)
            if time.monotonic() - start > timeout:
                return False
        return True

    # ── Image packing ────────────────────────────────────────────────────

    def _pack_image(self, image):
        """Convert PIL mode '1' image to packed 1-bit bytes (MSB first)."""
        if image.mode != "1":
            raise ValueError(f"Expected image mode '1', got '{image.mode}'")
        if image.size != (self.width, self.height):
            raise ValueError(
                f"Expected image size {(self.width, self.height)}, got {image.size}"
            )

        pixels = image.load()
        buf = bytearray(self.buf_size)
        idx = 0
        for y in range(self.height):
            for x_byte in range(self.width // 8):
                byte = 0
                for bit in range(8):
                    x = x_byte * 8 + bit
                    if pixels[x, y] != 0:
                        byte |= 0x80 >> bit
                buf[idx] = byte
                idx += 1
        return buf

    def _pack_image_window(self, image, x_byte_start, x_byte_end, y_start, y_end):
        pixels = image.load()
        width_bytes = x_byte_end - x_byte_start + 1
        total = width_bytes * (y_end - y_start + 1)
        buf = bytearray(total)
        idx = 0
        for y in range(y_start, y_end + 1):
            for x_byte in range(x_byte_start, x_byte_end + 1):
                byte = 0
                x0 = x_byte * 8
                for bit in range(8):
                    if pixels[x0 + bit, y] != 0:
                        byte |= 0x80 >> bit
                buf[idx] = byte
                idx += 1
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

        if image_red is not None:
            red_packed = self._pack_image(image_red)
            red_bytes = [~b & 0xFF for b in red_packed]
        else:
            red_bytes = [0x00] * self.buf_size

        self.send_command(0x26)
        self.send_data_bulk(red_bytes)
        self._refresh()

    def display_bw_only(self, image_bw):
        """Fast B/W-only update of the full display. Red RAM is untouched."""
        bw_bytes = self._pack_image(image_bw)
        self._init_no_reset()
        self._set_cursor(0, 0)
        self.send_command(0x24)
        self.send_data_bulk(bw_bytes)
        if not self._refresh_bw():
            print("  Falling back to full refresh for stability...")
            self._refresh()

    def display_bw_partial(self, image_bw, x, y, w, h):
        """Fast B/W-only partial update of a region, byte-aligned in X."""
        if image_bw.mode != "1":
            raise ValueError(f"Expected image mode '1', got '{image_bw.mode}'")
        if image_bw.size != (self.width, self.height):
            raise ValueError(
                f"Expected image size {(self.width, self.height)}, got {image_bw.size}"
            )
        if w <= 0 or h <= 0:
            return

        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.width - 1, x + w - 1)
        y1 = min(self.height - 1, y + h - 1)
        if x0 > x1 or y0 > y1:
            return

        x0_aligned = (x0 // 8) * 8
        x1_aligned = ((x1 + 7) // 8) * 8 - 1
        x_byte_start = x0_aligned // 8
        x_byte_end = x1_aligned // 8

        self._init_no_reset()
        self._set_window(x_byte_start, x_byte_end, y0, y1)
        self._set_cursor(x_byte_start, y0)

        bw_bytes = self._pack_image_window(image_bw, x_byte_start, x_byte_end, y0, y1)
        self.send_command(0x24)
        self.send_data_bulk(bw_bytes)
        if not self._refresh_bw():
            print("  Partial region update unstable, doing full B/W-area refresh...")
            self._set_window(0, (self.width // 8) - 1, 0, self.height - 1)
            self._set_cursor(0, 0)
            self.send_command(0x24)
            self.send_data_bulk(self._pack_image(image_bw))
            self._refresh()

    def sleep(self):
        """Enter deep sleep mode."""
        self.send_command(0x10)
        self.send_data(0x01)

    def cleanup(self):
        """Release resources."""
        if self.spi:
            self.spi.close()
            self.spi = None
        if self._h is not None:
            lgpio.gpiochip_close(self._h)
            self._h = None


# ── Demo ─────────────────────────────────────────────────────────────────────


def main():
    import datetime
    import statistics

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

        print("\n--- Priming full BWR frame (sets red layer) ---")
        now = datetime.datetime.now()
        img_bw = Image.new("1", (WIDTH, HEIGHT), 255)
        draw_bw = ImageDraw.Draw(img_bw)
        draw_bw.rectangle([(0, 0), (WIDTH - 1, HEIGHT - 1)], outline=0, width=2)
        draw_bw.text((10, 10), now.strftime("%H:%M"), font=font_big, fill=0)
        draw_bw.text((10, 55), now.strftime(":%S"), font=font_med, fill=0)
        draw_bw.text((10, 95), now.strftime("%d.%m.%Y"), font=font_med, fill=0)
        draw_bw.text((10, 120), now.strftime("%A"), font=font_sm, fill=0)
        draw_bw.text((10, 205), "Mode: FULL BWR", font=font_sm, fill=0)
        draw_bw.text((10, 225), "Benchmark follows", font=font_sm, fill=0)

        img_red = Image.new("1", (WIDTH, HEIGHT), 255)
        draw_red = ImageDraw.Draw(img_red)
        draw_red.text((10, 330), "RED LAYER PERSISTS", font=font_sm, fill=0)
        display.display(img_bw, img_red)

        benchmark_profiles = ["custom_a", "custom_b", "otp"]
        benchmark_cycles = 3
        results = {}

        print("\n=== Partial B/W benchmark ===")
        for profile in benchmark_profiles:
            display.set_bw_partial_profile(profile)
            samples = []
            print(f"\n--- Profile: {profile} ({benchmark_cycles} cycles) ---")

            for cycle in range(1, benchmark_cycles + 1):
                now = datetime.datetime.now()
                img_bw = Image.new("1", (WIDTH, HEIGHT), 255)
                draw_bw = ImageDraw.Draw(img_bw)

                draw_bw.rectangle([(0, 0), (WIDTH - 1, HEIGHT - 1)], outline=0, width=2)
                draw_bw.text((10, 10), now.strftime("%H:%M"), font=font_big, fill=0)
                draw_bw.text((10, 55), now.strftime(":%S"), font=font_med, fill=0)
                draw_bw.line([(5, 85), (WIDTH - 5, 85)], fill=0, width=1)
                draw_bw.text((10, 95), now.strftime("%d.%m.%Y"), font=font_med, fill=0)
                draw_bw.text((10, 120), now.strftime("%A"), font=font_sm, fill=0)
                draw_bw.line([(5, 145), (WIDTH - 5, 145)], fill=0, width=1)
                draw_bw.text((10, 155), f"{profile} {cycle}/{benchmark_cycles}", font=font_med, fill=0)
                draw_bw.text((10, 185), f"SSD1619 {WIDTH}x{HEIGHT}", font=font_sm, fill=0)
                draw_bw.text((10, 205), "Mode: PARTIAL B/W", font=font_sm, fill=0)
                draw_bw.text((10, 225), f"Profile: {profile}", font=font_sm, fill=0)

                t0 = time.monotonic()
                display.display_bw_only(img_bw)
                dt = time.monotonic() - t0
                samples.append(dt)
                print(f"  Cycle {cycle}: {dt:.2f}s")

                if cycle < benchmark_cycles:
                    time.sleep(2)

            results[profile] = samples

        print("\n=== Benchmark summary ===")
        for profile in benchmark_profiles:
            samples = results[profile]
            avg = statistics.mean(samples)
            best = min(samples)
            worst = max(samples)
            print(
                f"  {profile:8s} avg={avg:.2f}s  best={best:.2f}s  "
                f"worst={worst:.2f}s  samples={[round(s, 2) for s in samples]}"
            )

        fastest = min(benchmark_profiles, key=lambda name: statistics.mean(results[name]))
        print(f"\nFastest profile on this panel: {fastest}")

        # Secondary benchmark: OTP with reduced update window (top area only)
        # to verify whether region-limited updates save additional time.
        print("\n=== OTP ROI benchmark (partial window) ===")
        display.set_bw_partial_profile("otp")
        roi_x, roi_y, roi_w, roi_h = 0, 0, WIDTH, 160
        roi_cycles = 5
        roi_samples = []
        print(f"Window: x={roi_x}, y={roi_y}, w={roi_w}, h={roi_h}")

        for cycle in range(1, roi_cycles + 1):
            now = datetime.datetime.now()
            img_bw = Image.new("1", (WIDTH, HEIGHT), 255)
            draw_bw = ImageDraw.Draw(img_bw)

            # Only dynamic top area content: ideal for departure-board clock/status
            draw_bw.rectangle([(0, 0), (WIDTH - 1, roi_h - 1)], fill=255, outline=0, width=1)
            draw_bw.text((10, 10), now.strftime("%H:%M"), font=font_big, fill=0)
            draw_bw.text((10, 55), now.strftime(":%S"), font=font_med, fill=0)
            draw_bw.line([(5, 85), (WIDTH - 5, 85)], fill=0, width=1)
            draw_bw.text((10, 95), now.strftime("%d.%m.%Y"), font=font_med, fill=0)
            draw_bw.text((10, 120), now.strftime("%A"), font=font_sm, fill=0)

            t0 = time.monotonic()
            display.display_bw_partial(img_bw, roi_x, roi_y, roi_w, roi_h)
            dt = time.monotonic() - t0
            roi_samples.append(dt)
            print(f"  ROI cycle {cycle}: {dt:.2f}s")
            if cycle < roi_cycles:
                time.sleep(1)

        roi_avg = statistics.mean(roi_samples)
        roi_best = min(roi_samples)
        roi_worst = max(roi_samples)
        otp_full_avg = statistics.mean(results["otp"])
        gain = otp_full_avg - roi_avg
        print(
            f"  OTP full avg={otp_full_avg:.2f}s vs OTP ROI avg={roi_avg:.2f}s "
            f"(gain {gain:+.2f}s)"
        )
        print(
            f"  OTP ROI best={roi_best:.2f}s worst={roi_worst:.2f}s "
            f"samples={[round(s, 2) for s in roi_samples]}"
        )

        display.sleep()
        print("\nTEST COMPLETE — benchmark done")

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
