#!/usr/bin/env python3

import os
import time
import board
import busio
import gpiozero
import subprocess
import threading
import queue
from PIL import Image, ImageDraw, ImageFont
import adafruit_ssd1306
import evdev

# Rotary encoder setup
def find_rotary_device():
    """Find the first rotary encoder device that matches the pattern in /dev/input/by-path/."""
    by_path_dir = "/dev/input/by-path"
    try:
        for device_path in os.listdir(by_path_dir):
            if "platform-rotary" in device_path:
                full_path = os.path.join(by_path_dir, device_path)
                real_path = os.path.realpath(full_path)
                return evdev.InputDevice(real_path)
        raise FileNotFoundError("No rotary encoder device found")
    except (PermissionError, OSError) as e:
        raise RuntimeError(f"Error accessing rotary device: {e}")

d = find_rotary_device()

PAGE_COUNT = 5
page = 1
prev_page = None  # Track the last displayed page
page_queue = queue.Queue()

# Define the Reset Pin using gpiozero
oled_reset = gpiozero.OutputDevice(4, active_high=False)  # GPIO 4 (D4) used for reset

# Display Parameters
WIDTH = 128
HEIGHT = 64
TOGGLE_INTERVAL = 5  # Toggle between IP and SSID every 5 seconds

# I2C Communication
i2c = board.I2C()

# OLED Display Setup
oled_reset.on()
time.sleep(0.1)
oled_reset.off()
time.sleep(0.1)
oled_reset.on()

oled = adafruit_ssd1306.SSD1306_I2C(WIDTH, HEIGHT, i2c, addr=0x3C)
oled.fill(0)
oled.show()

# Create Image & Drawing Object
image = Image.new('1', (WIDTH, HEIGHT))
draw = ImageDraw.Draw(image)

# Get the absolute directory where the script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Load fonts using absolute paths
font_path = os.path.join(SCRIPT_DIR, 'PixelOperator.ttf')
icon_font_path = os.path.join(SCRIPT_DIR, 'lineawesome-webfont.ttf')

# Load fonts
font = ImageFont.truetype(font_path, 16)
icon_font = ImageFont.truetype(icon_font_path, 18)

# Icon Variables
ICON_CPU = chr(62171)
ICON_TEMP = chr(62609)
ICON_DISK = chr(63426)
ICON_WIFI = chr(61931)

# Positioning
LINE_HEIGHT = 20
COLUMN_WIDTH = WIDTH // 2

def get_system_stats():
    def run_command(cmd, default="Unknown"):
        try:
            return subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode().strip() or default
        except subprocess.CalledProcessError:
            return default

    return {
        "hostname": run_command("hostname"),
        "ip": run_command("hostname -I | cut -d' ' -f1", default="No IP"),
        "ssid": run_command("/usr/sbin/iwgetid -r", default="Not Connected"),
        "cpu": run_command("top -bn1 | grep load | awk '{printf \"%.2f\", $(NF-2)}'", default="N/A"),
        "disk": run_command("df -h | awk '$NF==\"/\"{printf \"%d/%dGB\", $3,$2}'", default="N/A"),
        "temp": run_command("vcgencmd measure_temp | cut -d '=' -f 2", default="N/A")
    }

def rotary_encoder_listener():
    """ Threaded function to listen for rotary encoder events and update the page number. """
    global page
    for e in d.read_loop():
        if e.type == evdev.ecodes.EV_REL:
            new_page = (page + e.value - 1) % PAGE_COUNT + 1
            page_queue.put(new_page)  # Queue page updates

# Start rotary encoder thread
threading.Thread(target=rotary_encoder_listener, daemon=True).start()

toggle = False
last_update_time = time.time()  # Track last OLED update

while True:
    now = time.time()
    redraw_required = False  # Flag to avoid unnecessary OLED updates

    # Check for page changes
    while not page_queue.empty():
        page = page_queue.get()
        if page != prev_page:
            redraw_required = True  # Force redraw if page changed

    # Update display every 1 second OR if the page changed
    if redraw_required or (now - last_update_time >= 1):
        draw.rectangle((0, 0, WIDTH, HEIGHT), outline=0, fill=0)  # Clear display

        stats = get_system_stats()

        # Line 1: CPU Icon & Hostname (Full Width)
        draw.text((2, 0), ICON_CPU, font=icon_font, fill=255)
        draw.text((24, 2), stats["hostname"], font=font, fill=255)

        # Line 2: Disk Icon + Usage (Col 1), Temp Icon + Temp (Col 2)
        draw.text((2, LINE_HEIGHT), ICON_DISK, font=icon_font, fill=255)
        draw.text((24, LINE_HEIGHT + 2), stats["disk"], font=font, fill=255)
        draw.text((COLUMN_WIDTH + 2, LINE_HEIGHT), ICON_TEMP, font=icon_font, fill=255)
        draw.text((COLUMN_WIDTH + 24, LINE_HEIGHT + 2), stats["temp"], font=font, fill=255)

        # Line 3: WiFi Icon + IP or SSID (Toggles every 5 sec)
        draw.text((2, LINE_HEIGHT * 2), ICON_WIFI, font=icon_font, fill=255)
        display_text = stats["ip"] if toggle else stats["ssid"]
        draw.text((24, LINE_HEIGHT * 2 + 2), display_text, font=font, fill=255)

        # Line 4: Page number
        draw.text((120, 2), str(page), font=font, fill=255)

        # Send updated image to OLED
        oled.image(image)
        oled.show()

        # Track last update time
        last_update_time = now
        prev_page = page  # Store the last displayed page

    # Toggle WiFi/IP every 5 seconds
    if int(now) % TOGGLE_INTERVAL == 0:
        toggle = not toggle
