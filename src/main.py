import os
import board
import evdev
import socket
import psutil
import asyncio
import logging
import subprocess
import adafruit_ssd1306
from PIL import Image, ImageDraw, ImageFont

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

# Networking Icons
ICON_WIFI = chr(61931)  # FontAwesome Wi-Fi icon
ICON_ETH = chr(61927)   # FontAwesome Ethernet icon
ICON_NO_CONN = chr(61928)  # FontAwesome "no connection" icon

def get_network_status():
    """Returns a tuple: (network_icon, IP address or 'Not Connected')"""
    interfaces = psutil.net_if_addrs()

    # Prioritize Ethernet over Wi-Fi if both are active
    for iface in interfaces:
        if "eth" in iface or "en" in iface:  # Match Ethernet interfaces
            ip = get_ip_address(iface)
            if ip:
                log.debug(f"Ethernet connection detected: {iface} -> {ip}")
                return ICON_ETH, ip

    for iface in interfaces:
        if "wlan" in iface or "wifi" in iface:  # Match Wi-Fi interfaces
            ip = get_ip_address(iface)
            if ip:
                log.debug(f"Wi-Fi connection detected: {iface} -> {ip}")
                return ICON_WIFI, ip

    log.info("No active network connection detected.")
    return ICON_NO_CONN, "Not Connected"  # No network detected

def get_ip_address(interface):
    """Returns the IPv4 address of the given network interface, or None if unavailable."""
    addrs = psutil.net_if_addrs().get(interface, [])
    for addr in addrs:
        if addr.family == socket.AF_INET:  # IPv4 only
            return addr.address
    return None

def find_input_device(pattern):
    """Find the first input device that matches the pattern in /dev/input/by-path/."""
    by_path_dir = "/dev/input/by-path"
    try:
        for device_path in os.listdir(by_path_dir):
            if pattern in device_path:
                full_path = os.path.join(by_path_dir, device_path)
                real_path = os.path.realpath(full_path)
                log.info(f"Found input device: {full_path}")
                return evdev.InputDevice(real_path)
        raise FileNotFoundError(f"No device found matching pattern: {pattern}")
    except (PermissionError, OSError) as e:
        raise RuntimeError(f"Error accessing device: {e}")

class OLEDDisplay:
    def __init__(self, width=128, height=64, i2c_addr=0x3C):
        self.width = width
        self.height = height
        self.i2c_addr = i2c_addr

        self.i2c = board.I2C()
        self.oled = adafruit_ssd1306.SSD1306_I2C(self.width, self.height, self.i2c)
        self.oled.fill(0)
        self.oled.show()

        self.image = Image.new('1', (self.width, self.height))
        self.draw = ImageDraw.Draw(self.image)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        font_path = os.path.join(os.path.dirname(script_dir), 'fonts', 'PixelOperator.ttf')
        icon_font_path = os.path.join(os.path.dirname(script_dir), 'fonts', 'lineawesome-webfont.ttf')

        self.font = ImageFont.truetype(font_path, 16)
        self.icon_font = ImageFont.truetype(icon_font_path, 18)
        log.info("OLED display initialized.")

    def draw_text(self, text, position=(0, 0), fill=255, clear=True, clear_screen=False):
        # Get bounding box (left, top, right, bottom) relative to (0, 0)
        left, top, right, bottom = self.font.getbbox(text)

        if clear:
            # Clear the line the text will be drawn on
            self.draw.rectangle(
                (position[0] + left, position[1] + top, self.width, position[1] + bottom),
                outline=0, fill=0
            )

        if clear_screen:
            self.draw.rectangle((0, 0, self.width, self.height), outline=0, fill=0)

        self.draw.text(position, text, font=self.font, fill=fill)
        self.oled.image(self.image)
        self.oled.show()
        log.debug(f"Displayed text: {text}")        

    def draw_icon(self, text, position=(0, 0), fill=255, clear=True, clear_screen=False):
        # Get bounding box (left, top, right, bottom) relative to (0, 0)
        left, top, right, bottom = self.icon_font.getbbox(text)

        if clear:
            self.draw.rectangle(
                (position[0] + left, position[1] + top, self.width - (position[0] + right), position[1] + bottom),
                outline=0, fill=0
            )

        if clear_screen:
            self.draw.rectangle((0, 0, self.width, self.height), outline=0, fill=0)

        self.draw.text(position, text, font=self.icon_font, fill=fill)
        self.oled.image(self.image)
        self.oled.show()        

class ModeStateMachine:
    MODES = ["Off", "NWS Balloon", "HAM Balloon", "ADS-B", "APRS"]
    
    def __init__(self, display):
        self.selected_mode_index = 0  # Previously "current_mode_index"
        self.active_mode_index = 0  # Active mode
        self.display = display
        self.last_knob_time = asyncio.get_event_loop().time()
        self.timeout_seconds = 5  # Time before reverting to active mode
        self.inactivity_task = asyncio.create_task(self.monitor_inactivity())

        self.update_display()

    async def monitor_inactivity(self):
        """Reverts display to active mode after inactivity."""
        while True:
            await asyncio.sleep(1)
            if asyncio.get_event_loop().time() - self.last_knob_time > self.timeout_seconds:
                self.display_active_mode()

    def next_mode(self, direction=1):
        """Move to the next or previous mode."""
        self.selected_mode_index = (self.selected_mode_index + direction) % len(self.MODES)
        self.last_knob_time = asyncio.get_event_loop().time()
        self.update_display()

    def get_selected_mode(self):
        return self.MODES[self.selected_mode_index]

    def get_active_mode(self):
        return self.MODES[self.active_mode_index]

    def activate(self):
        """Activates the selected mode."""
        self.active_mode_index = self.selected_mode_index
        log.info(f"Activating {self.get_active_mode()}")
        self.last_knob_time = asyncio.get_event_loop().time()

        self.display.draw_text(f"Mode: {self.get_active_mode()}", position=(0, 0))
        activation_text = "Deactivating..." if self.active_mode_index == 0 else "Activating..."
        self.display.draw_text(activation_text, position=(0, 24))

    def handle_event(self, event):
        """Handles knob and button events."""
        self.last_knob_time = asyncio.get_event_loop().time()
        if event == "knob_forward":
            self.next_mode(1)
        elif event == "knob_backward":
            self.next_mode(-1)
        elif event == "button_pressed":
            self.activate()

    def update_display(self):
        """Updates the display with the selected mode."""
        mode_text = f"Mode: ({self.get_selected_mode()})"
        self.display.draw_text(mode_text, position=(0, 0))

    def display_active_mode(self):
        """Reverts display to the active mode after inactivity."""
        self.display.draw_text(f"Mode: {self.get_active_mode()}", position=(0, 0))


async def input(device):
    async for event in device.async_read_loop():
        #log.debug(repr(event))
        if device == rotary_knob and event.type == evdev.ecodes.EV_REL:
            event_name = "knob_forward" if event.value > 0 else "knob_backward"
            await event_queue.put(event_name)
            log.debug(f"Rotary event: {event_name}")

        elif device == button and event.type == evdev.ecodes.EV_KEY:
            if event.code == evdev.ecodes.KEY_A:
                event_name = "button_pressed" if event.value == 1 else "button_released"
                await event_queue.put(event_name)
                log.debug(f"Button event: {event_name}")

async def process_events():
    """Continuously processes events from the queue and updates the mode state."""
    while True:
        event = await event_queue.get()
        if event in ["knob_forward", "knob_backward", "button_pressed"]:
            mode_manager.handle_event(event)

        event_queue.task_done()

def get_wifi_ssid():
    """Returns the connected Wi-Fi SSID, or None if not connected."""
    try:
        ssid = subprocess.check_output(["iwgetid", "-r"], text=True).strip()
        return ssid if ssid else None
    except subprocess.CalledProcessError:
        return None

async def update_network_status(display, position=(0, 50)):
    last_icon, last_ip, last_ssid = None, None, None
    show_ip = True  # Toggle between IP and SSID

    while True:
        icon, ip = get_network_status()
        ssid = get_wifi_ssid() if icon == ICON_WIFI else None  # Only get SSID for Wi-Fi

        if icon != last_icon or ip != last_ip or ssid != last_ssid:
            display.draw_icon(icon, position=position)

        if icon == ICON_WIFI and ssid:
            display_text = ip if show_ip else ssid
            show_ip = not show_ip  # Toggle for next cycle
        else:
            display_text = ip  # Ethernet or no network

        display.draw_text(display_text, position=(position[0] + 20, position[1]))

        last_icon, last_ip, last_ssid = icon, ip, ssid
        await asyncio.sleep(5)  # Toggle every 5 seconds

async def main():
    global mode_manager
    display = OLEDDisplay()

    mode_manager = ModeStateMachine(display)  # Initialize state machine

    tasks = [
        asyncio.create_task(input(rotary_knob)),
        asyncio.create_task(input(button)),
        asyncio.create_task(process_events()),
        asyncio.create_task(update_network_status(display))
    ]
    
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        display.draw_text("Goodbye!", position=(28, 32), clear_screen=True)
        print("Shutting down gracefully...")
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)  # Allow tasks to exit
        print("All tasks cancelled. Exiting.")

# Input device setup
rotary_knob = find_input_device("platform-rotary")
button = find_input_device("platform-button")

# Async queue
event_queue = asyncio.Queue()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nKeyboardInterrupt received. Exiting cleanly.")

