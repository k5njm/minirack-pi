#!/usr/bin/env python3

import os
import time
import board
import busio
import gpiozero
import subprocess
import asyncio
from asyncio import Queue
from PIL import Image, ImageDraw, ImageFont
import adafruit_ssd1306
import evdev

def find_input_device(pattern):
    """Find the first input device that matches the pattern in /dev/input/by-path/."""
    by_path_dir = "/dev/input/by-path"
    try:
        for device_path in os.listdir(by_path_dir):
            if pattern in device_path:
                full_path = os.path.join(by_path_dir, device_path)
                real_path = os.path.realpath(full_path)
                return evdev.InputDevice(real_path)
        raise FileNotFoundError(f"No device found matching pattern: {pattern}")
    except (PermissionError, OSError) as e:
        raise RuntimeError(f"Error accessing device: {e}")

# Input device setup
rotary_device = find_input_device("platform-rotary")
button_device = find_input_device("platform-button")

# Available modes/pages
MODES = ["Off", "NWS Balloon", "HAM Balloon", "ADS-B", "APRS"]
current_mode_index = 0  # Start in "Off" mode
button_pressed = False
prev_mode = None  # Track the last displayed mode
display_queue = asyncio.Queue()  # Queue for display updates
show_hostname = True  # Start by showing hostname

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
font_path = os.path.join(os.path.dirname(SCRIPT_DIR), 'fonts', 'PixelOperator.ttf')
icon_font_path = os.path.join(os.path.dirname(SCRIPT_DIR), 'fonts', 'lineawesome-webfont.ttf')

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

class DisplayManager:
    def __init__(self):
        self.stats = get_system_stats()
        self.toggle = False
        self.last_stats_update = 0
        self.stats_update_interval = 1.0  # Update stats every second
        self.toggle_interval = TOGGLE_INTERVAL
        
    async def update_stats(self):
        """Periodically update system stats"""
        while True:
            self.stats = get_system_stats()
            await asyncio.sleep(self.stats_update_interval)
            
    async def toggle_wifi_display(self):
        """Toggle between IP and SSID display"""
        while True:
            await asyncio.sleep(self.toggle_interval)
            self.toggle = not self.toggle
            await self.update_ui()
            
    def draw_page_indicator(self):
        """Draw just the page indicator"""
        # Clear just the page indicator area
        draw.rectangle((110, 0, WIDTH, 16), outline=0, fill=0)
        page_text = f"{'*' if button_pressed else ' '}{current_mode_index + 1}"
        draw.text((112, 2), page_text, font=font, fill=255)
        
    def draw_system_info(self):
        """Draw the system information"""
        draw.rectangle((0, 0, WIDTH, HEIGHT), outline=0, fill=0)
        
        # Line 1: CPU Icon & Hostname/Mode
        draw.text((2, 0), ICON_CPU, font=icon_font, fill=255)
        if show_hostname and MODES[current_mode_index] == "Off":
            draw.text((24, 2), self.stats["hostname"], font=font, fill=255)
        else:
            draw.text((24, 2), MODES[current_mode_index], font=font, fill=255)
        
        # Line 2: Disk & Temp
        draw.text((2, LINE_HEIGHT), ICON_DISK, font=icon_font, fill=255)
        draw.text((24, LINE_HEIGHT + 2), self.stats["disk"], font=font, fill=255)
        draw.text((COLUMN_WIDTH + 2, LINE_HEIGHT), ICON_TEMP, font=icon_font, fill=255)
        draw.text((COLUMN_WIDTH + 24, LINE_HEIGHT + 2), self.stats["temp"], font=font, fill=255)
        
        # Line 3: WiFi
        draw.text((2, LINE_HEIGHT * 2), ICON_WIFI, font=icon_font, fill=255)
        display_text = self.stats["ip"] if self.toggle else self.stats["ssid"]
        draw.text((24, LINE_HEIGHT * 2 + 2), display_text, font=font, fill=255)
        
        self.draw_page_indicator()
        
    async def update_ui(self):
        """Update the display"""
        oled.image(image)
        oled.show()

async def handle_ui_updates():
    """Manage all UI updates"""
    display_mgr = DisplayManager()
    
    # Start background tasks
    asyncio.create_task(display_mgr.update_stats())
    asyncio.create_task(display_mgr.toggle_wifi_display())
    
    # Initial draw
    display_mgr.draw_system_info()
    await display_mgr.update_ui()
    
    while True:
        update_type = await display_queue.get()
        if update_type == "page_change" or update_type == "button_event":
            # Quick update for UI interactions
            display_mgr.draw_page_indicator()
        elif update_type == "full_refresh":
            # Full refresh for system stats
            display_mgr.draw_system_info()
        await display_mgr.update_ui()

async def handle_device_events(device):
    """Handle events from a single input device."""
    global current_mode_index, button_pressed, show_hostname
    async for event in device.async_read_loop():
        if device == rotary_device and event.type == evdev.ecodes.EV_REL:
            current_mode_index = (current_mode_index + event.value) % len(MODES)
            if current_mode_index != 0:  # If we're not in "Off" mode
                show_hostname = False  # Stop showing hostname
            print(f"Rotary event: new mode = {MODES[current_mode_index]}")
            # Immediate UI update for input events
            await display_queue.put("page_change")
        elif device == button_device and event.type == evdev.ecodes.EV_KEY:
            if event.code == evdev.ecodes.KEY_A:
                button_pressed = bool(event.value)
                print(f"Button event: pressed = {button_pressed}")
                await display_queue.put("button_event")

async def cleanup():
    """Clean up resources before shutdown."""
    # Clear the display
    draw.rectangle((0, 0, WIDTH, HEIGHT), outline=0, fill=0)
    oled.image(image)
    oled.show()
    
    # Close input devices
    rotary_device.close()
    button_device.close()
    
    # Reset OLED
    oled_reset.off()

if __name__ == "__main__":
    # Set up event loop
    loop = asyncio.get_event_loop()
    
    # Create tasks
    tasks = [
        asyncio.ensure_future(handle_ui_updates()),
        asyncio.ensure_future(handle_device_events(rotary_device)),
        asyncio.ensure_future(handle_device_events(button_device))
    ]
    
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")
        # Cancel all tasks
        for task in tasks:
            task.cancel()
        # Run cleanup
        loop.run_until_complete(cleanup())
    finally:
        loop.stop()
        loop.close()
