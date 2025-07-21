# SPDX-FileCopyrightText: 2023 Jeff Epler for Adafruit Industries
# SPDX-FileCopyrightText: 2023 Limor Fried for Adafruit Industries
#
# SPDX-License-Identifier: Unlicense

import ssl
import os
import time
import socketpool
import adafruit_requests
import rtc
import adafruit_ntp
import wifi
import bitmaptools
import displayio
import gifio
import jpegio
import ulab.numpy as np
import analogio
import board
import adafruit_pycamera

# Global variables
pycam = None
last_frame = None
onionskin = None
timelapse_remaining = None
timelapse_timestamp = None
battery_pin = None
voltage_history = []
last_recorded_time = 0
curr_setting = 0
jpeg_decoder = None

# Gallery state variables
gallery_mode = False
gallery_images = []
gallery_index = 0
gallery_image_buffer = None
gallery_zoom_level = 1  # 1 = scale 1 (320x240), 2 = scale 2 (160x120)

# Settings navigation array
SETTINGS = (
    None,
    "resolution",
    "effect",
    "mode",
    "led_level",
    "led_color",
    "timelapse_rate",
)

def setup_wifi_and_time():
    """Initialize WiFi connection and synchronize time via NTP."""
    utc_offset = os.getenv("UTC_OFFSET")
    tz = os.getenv("TZ")
    ssid = os.getenv("CIRCUITPY_WIFI_SSID")
    password = os.getenv("CIRCUITPY_WIFI_PASSWORD")

    if not ssid or not password:
        print("Wifi config not found in settings.toml. Time not set.")
        return

    print(f"Connecting to {ssid}")

    try:
        wifi.radio.connect(ssid, password)

        if wifi.radio.connected:
            print(f"Connected to {ssid}!")
            print("My IP address is", wifi.radio.ipv4_address)
            pool = socketpool.SocketPool(wifi.radio)

            # Get timezone offset if not manually set
            if utc_offset is None and tz:
                try:
                    requests = adafruit_requests.Session(pool, ssl.create_default_context())
                    response = requests.get(f"http://worldtimeapi.org/api/timezone/{tz}")
                    response_as_json = response.json()
                    utc_offset = response_as_json["raw_offset"] + response_as_json["dst_offset"]
                    print(f"UTC_OFFSET: {utc_offset}")
                except Exception as e:
                    print(f"Failed to get timezone info: {e}")
                    utc_offset = 0
            elif utc_offset:
                utc_offset = int(utc_offset)
            else:
                utc_offset = 0

            # Synchronize time via NTP
            try:
                ntp = adafruit_ntp.NTP(
                    pool, server="pool.ntp.org", tz_offset=utc_offset // 3600
                )
                print(f"ntp time: {ntp.datetime}")
                rtc.RTC().datetime = ntp.datetime
            except Exception as e:
                print(f"NTP sync failed: {e}")
        else:
            print("Wifi failed to connect. Time not set.")

    except Exception as e:
        print(f"WiFi connection error: {e}")

def init_battery_monitoring():
    """Initialize battery monitoring hardware."""
    global battery_pin
    battery_pin = analogio.AnalogIn(board.BATTERY_MONITOR)

def get_battery_voltage():
    """Get current battery voltage averaged over last 10 readings."""
    raw_value = battery_pin.value
    voltage = (raw_value / 65535) * 3.3 * 2
    voltage_history.append(voltage)
    if len(voltage_history) > 10:
        voltage_history.pop(0)
    return sum(voltage_history) / len(voltage_history)

def battery_percentage(voltage):
    """Convert battery voltage to percentage estimate."""
    if voltage >= 4.2:
        return 100
    elif voltage >= 3.7:
        return int((voltage - 3.7) / 0.5 * 100)
    elif voltage >= 3.5:
        return int((voltage - 3.5) / 0.2 * 25)
    elif voltage >= 3.2:
        return int((voltage - 3.2) / 0.3 * 25)
    else:
        return 0

def update_battery_status():
    """Update battery status every 10 seconds."""
    global last_recorded_time
    current_time = time.time()

    if current_time - last_recorded_time >= 10:
        battery_voltage = get_battery_voltage()
        last_recorded_time = current_time
        return battery_voltage
    return None

def is_sd_card_available():
    """Check if SD card is actually mounted and writable."""
    try:
        import os

        # Check if /sd directory exists
        root_contents = os.listdir('/')

        if 'sd' not in root_contents:
            return False

        # Try to list SD card contents
        try:
            sd_contents = os.listdir('/sd')
        except OSError:
            return False

        # Try to get filesystem stats
        try:
            stat = os.statvfs('/sd')
            if stat[3] > 0:  # f_bavail (available blocks)
                return True
            else:
                return False
        except (OSError, AttributeError):
            # Fall back to simple directory listing test
            try:
                os.listdir('/sd')
                return True
            except OSError:
                return False

    except Exception:
        return False

def show_capture_status(success=True, preview_only=False):
    """Standardized status messages for capture operations."""
    if preview_only:
        pycam.display_message("Preview Only", color=0xFFFF00)
        time.sleep(1)
    elif success:
        pycam.display_message("Saved!", color=0x00FF00)
    else:
        pycam.display_message("Failed", color=0xFF0000)
        time.sleep(0.5)

def safe_capture_operation(capture_func, *args, **kwargs):
    """Wrapper for safe capture operations with standardized error handling."""
    if not is_sd_card_available():
        show_capture_status(preview_only=True)
        return False

    try:
        result = capture_func(*args, **kwargs)
        show_capture_status(success=True)
        return result
    except (TypeError, RuntimeError, OSError) as e:
        print(f"Capture failed: {e}")
        show_capture_status(success=False)
        return False

def handle_stop_motion_mode():
    """Handle stop motion mode with onion-skin overlay."""
    if pycam.stop_motion_frame != 0:
        new_frame = pycam.continuous_capture()
        bitmaptools.alphablend(
            onionskin, last_frame, new_frame, displayio.Colorspace.RGB565_SWAPPED
        )
        pycam.blit(onionskin)
    else:
        pycam.blit(pycam.continuous_capture())

def handle_gameboy_mode():
    """Handle Game Boy style dithered display mode."""
    bitmaptools.dither(
        last_frame, pycam.continuous_capture(), displayio.Colorspace.RGB565_SWAPPED
    )
    pycam.blit(last_frame)

def handle_timelapse_mode():
    """Handle time-lapse photography mode."""
    global timelapse_remaining, timelapse_timestamp

    if timelapse_remaining is None:
        pycam.timelapsestatus_label.text = "STOP"
    else:
        timelapse_remaining = timelapse_timestamp - time.time()
        pycam.timelapsestatus_label.text = f"{timelapse_remaining}s /    "

    # Manually updating the label text ensures proper re-painting
    pycam.timelapse_rate_label.text = pycam.timelapse_rate_label.text
    pycam.timelapse_submode_label.text = pycam.timelapse_submode_label.text

    # Only preview in high power mode or when stopped
    if (timelapse_remaining is None) or (pycam.timelapse_submode_label.text == "HiPwr"):
        pycam.blit(pycam.continuous_capture())

    # Adjust display brightness for low power mode
    if pycam.timelapse_submode_label.text == "LowPwr" and (timelapse_remaining is not None):
        pycam.display.brightness = 0.05
    else:
        pycam.display.brightness = 1

    pycam.display.refresh()

    # Check if it's time to capture
    if timelapse_remaining is not None and timelapse_remaining <= 0:
        pycam.blit(pycam.continuous_capture())
        # pycam.tone(200, 0.1)  # uncomment to add beep when photo is taken

        pycam.display_message("Snap!", color=0x0000FF)
        safe_capture_operation(pycam.capture_jpeg)

        pycam.live_preview_mode()
        pycam.display.refresh()
        pycam.blit(pycam.continuous_capture())
        timelapse_timestamp = time.time() + pycam.timelapse_rates[pycam.timelapse_rate] + 1

def handle_camera_modes():
    """Handle different camera capture modes."""
    if pycam.mode_text == "STOP":
        handle_stop_motion_mode()
    elif pycam.mode_text == "GBOY":
        handle_gameboy_mode()
    elif pycam.mode_text == "LAPS":
        handle_timelapse_mode()
    else:
        pycam.blit(pycam.continuous_capture())

def handle_shutter_button():
    """Handle shutter button press events."""
    if pycam.shutter.long_press:
        print("FOCUS")
        print(pycam.autofocus_status)
        pycam.autofocus()
        print(pycam.autofocus_status)

    if pycam.shutter.short_count:
        print("Shutter released")

        if pycam.mode_text == "STOP":
            handle_stop_motion_capture()
        elif pycam.mode_text == "GBOY":
            handle_gameboy_capture()
        elif pycam.mode_text == "GIF":
            handle_gif_capture()
        elif pycam.mode_text == "JPEG":
            handle_jpeg_capture()

def handle_stop_motion_capture():
    """Capture frame for stop motion animation."""
    pycam.capture_into_bitmap(last_frame)
    pycam.stop_motion_frame += 1

    pycam.display_message("Snap!", color=0x0000FF)
    safe_capture_operation(pycam.capture_jpeg)
    pycam.live_preview_mode()

def handle_gameboy_capture():
    """Capture single frame as Game Boy style GIF."""
    def capture_gameboy_gif():
        f = pycam.open_next_image("gif")
        with gifio.GifWriter(
            f,
            pycam.camera.width,
            pycam.camera.height,
            displayio.Colorspace.RGB565_SWAPPED,
            dither=True,
        ) as g:
            g.add_frame(last_frame, 1)
        return True

    safe_capture_operation(capture_gameboy_gif)

def handle_gif_capture():
    """Record animated GIF."""
    def capture_animated_gif():
        f = pycam.open_next_image("gif")

        i = 0
        ft = []
        pycam._mode_label.text = "RECORDING"  # pylint: disable=protected-access
        pycam.display.refresh()

        with gifio.GifWriter(
            f,
            pycam.camera.width,
            pycam.camera.height,
            displayio.Colorspace.RGB565_SWAPPED,
            dither=True,
        ) as g:
            t00 = t0 = time.monotonic()
            while (i < 15) or not pycam.shutter_button.value:
                i += 1
                _gifframe = pycam.continuous_capture()
                g.add_frame(_gifframe, 0.12)
                pycam.blit(_gifframe)
                t1 = time.monotonic()
                ft.append(1 / (t1 - t0))
                print(end=".")
                t0 = t1

        pycam._mode_label.text = "GIF"  # pylint: disable=protected-access
        print(f"\nfinal size {f.tell()} for {i} frames")
        print(f"average framerate {i / (t1 - t00)}fps")
        print(f"best {max(ft)} worst {min(ft)} std. deviation {np.std(ft)}")
        f.close()
        pycam.display.refresh()
        return True

    safe_capture_operation(capture_animated_gif)

def handle_jpeg_capture():
    """Capture standard JPEG photo."""
    pycam.tone(1500, 0.05)  # Shutter-like sound
    pycam.display_message("Snap!", color=0x0000FF)

    safe_capture_operation(pycam.capture_jpeg)
    pycam.live_preview_mode()

def handle_sd_card_events():
    """Handle SD card insertion and removal."""
    if pycam.card_detect.fell:
        print("SD card removed")
        pycam.unmount_sd_card()
        pycam.display.refresh()

    if pycam.card_detect.rose:
        print("SD card inserted")
        pycam.display_message("Mounting\nSD Card", color=0xFFFFFF)

        for _ in range(3):
            try:
                print("Mounting card")
                pycam.mount_sd_card()
                print("Success!")
                break
            except OSError as e:
                print("Retrying!", e)
                time.sleep(0.5)
        else:
            pycam.display_message("SD Card\nFailed!", color=0xFF0000)
            time.sleep(0.5)

        pycam.display.refresh()

def handle_navigation_buttons():
    """Handle directional button presses for settings navigation."""
    global curr_setting

    if pycam.up.fell:
        print("UP")
        key = SETTINGS[curr_setting]
        if key:
            print("getting", key, getattr(pycam, key))
            setattr(pycam, key, getattr(pycam, key) + 1)

    if pycam.down.fell:
        print("DN")
        key = SETTINGS[curr_setting]
        if key:
            setattr(pycam, key, getattr(pycam, key) - 1)

    if pycam.right.fell:
        print("RT")
        curr_setting = (curr_setting + 1) % len(SETTINGS)
        # Skip timelapse_rate if not in LAPS mode
        if pycam.mode_text != "LAPS" and SETTINGS[curr_setting] == "timelapse_rate":
            curr_setting = (curr_setting + 1) % len(SETTINGS)
        print(SETTINGS[curr_setting])
        pycam.select_setting(SETTINGS[curr_setting])

    if pycam.left.fell:
        print("LF")
        curr_setting = (curr_setting - 1 + len(SETTINGS)) % len(SETTINGS)
        # Skip timelapse_rate if not in LAPS mode
        if pycam.mode_text != "LAPS" and SETTINGS[curr_setting] == "timelapse_rate":
            curr_setting = (curr_setting + 1) % len(SETTINGS)
        print(SETTINGS[curr_setting])
        pycam.select_setting(SETTINGS[curr_setting])

def handle_select_button():
    """Handle select button press."""
    global gallery_mode
    print("SEL")

    if pycam.mode_text == "LAPS":
        pycam.timelapse_submode += 1
        pycam.display.refresh()
    else:
        # Toggle gallery mode
        gallery_mode = not gallery_mode
        if gallery_mode:
            enter_gallery_mode()
        else:
            exit_gallery_mode()

def handle_ok_button():
    """Handle OK button press for timelapse control or battery display."""
    global timelapse_remaining, timelapse_timestamp

    print("OK")

    if pycam.mode_text == "LAPS":
        if timelapse_remaining is None:  # stopped
            print("Starting timelapse")
            timelapse_remaining = pycam.timelapse_rates[pycam.timelapse_rate]
            timelapse_timestamp = time.time() + timelapse_remaining + 1

            # Lock camera settings to prevent auto-adjustment
            saved_settings = pycam.get_camera_autosettings()
            pycam.set_camera_exposure(saved_settings["exposure"])
            pycam.set_camera_gain(saved_settings["gain"])
            pycam.set_camera_wb(saved_settings["wb"])
        else:  # is running, turn off
            print("Stopping timelapse")
            timelapse_remaining = None

            # Re-enable automatic camera settings
            pycam.camera.exposure_ctrl = True
            pycam.set_camera_gain(None)  # go back to autogain
            pycam.set_camera_wb(None)  # go back to autobalance
            pycam.set_camera_exposure(None)  # go back to auto shutter
    else:
        # Display battery status
        battery_voltage = get_battery_voltage()
        battery_percent = battery_percentage(battery_voltage)
        print(f"Battery: {battery_voltage:.2f}V ({battery_percent}%)")
        pycam.display_message(f"{battery_percent}%", color=0xFFFFFF)

def scan_gallery_images():
    """Scan SD card for image files and return sorted list."""
    global gallery_images
    gallery_images = []

    if not is_sd_card_available():
        print("No SD card available for gallery")
        return []

    try:
        import os
        files = os.listdir('/sd')

        # Filter for image files (case insensitive)
        for file in files:
            file_lower = file.lower()
            if (file_lower.endswith('.jpg') or
                file_lower.endswith('.jpeg') or
                file_lower.endswith('.gif')):
                gallery_images.append(file)

        # Sort files by name
        gallery_images.sort()
        print("Found " + str(len(gallery_images)) + " images: " + str(gallery_images))
        return gallery_images

    except Exception as e:
        print("Error scanning gallery images: " + str(e))
        gallery_images = []
        return []

def enter_gallery_mode():
    """Enter gallery browsing mode."""
    global gallery_mode, gallery_index, gallery_zoom_level

    print("Entering gallery mode")
    gallery_mode = True
    gallery_index = 0
    gallery_zoom_level = 1  # Start at zoom level 1 (scale 1 = 320x240)

    # Scan for images
    images = scan_gallery_images()

    if not images:
        pycam.display_message("No Photos", color=0xFFFF00)
        time.sleep(1)
        exit_gallery_mode()
        return

    pycam.display_message("Gallery Mode", color=0x00FF00)
    time.sleep(0.5)
    display_current_image()

def cleanup_gallery_display():
    """Clean up gallery display resources without clearing camera UI."""
    try:
        # Force garbage collection to free image memory
        import gc
        gc.collect()
        print("Gallery display cleaned up, memory freed")

    except Exception as e:
        print("Error during gallery cleanup: " + str(e))

def exit_gallery_mode():
    """Exit gallery browsing mode and return to camera."""
    global gallery_mode, gallery_images, gallery_index, gallery_image_buffer

    print("Exiting gallery mode")
    gallery_mode = False

    # Clean up gallery data to free memory
    cleanup_gallery_display()
    gallery_images = []
    gallery_index = 0

    # Clear the gallery image buffer
    if gallery_image_buffer:
        for y in range(pycam.camera.height):
            for x in range(pycam.camera.width):
                gallery_image_buffer[x, y] = 0x0000

    print("Attempting to restore camera mode...")

    try:
        # Simple approach: Just remove any extra display groups and restore preview
        existing_group = pycam.display.root_group

        # Remove the gallery overlay group, if it exists, without disturbing the HUD
        if hasattr(pycam, "gallery_group"):
            if pycam.gallery_group in existing_group:
                existing_group.remove(pycam.gallery_group)
            delattr(pycam, "gallery_group")

        # Force PyCamera to redraw its UI by calling live_preview_mode
        pycam.live_preview_mode()

        # Force a complete display refresh to restore all UI elements
        pycam.display.refresh()
        time.sleep(0.2)  # Give more time for full refresh

        # Force PyCamera to update all its labels and UI elements
        pycam.display.refresh()
        time.sleep(0.1)

        # One more refresh to ensure everything is properly restored
        pycam.display.refresh()

        print("Camera mode restored successfully")

        # Brief confirmation message
        pycam.display_message("Camera Mode", color=0x00FF00)
        time.sleep(0.5)

    except Exception as e:
        print("Error restoring camera mode: " + str(e))

def get_current_scale_factor():
    """Get the current zoom scale factor based on user zoom level."""
    global gallery_zoom_level
    return gallery_zoom_level

def load_image_file(filename):
    """Attempt to load an image file into a displayable bitmap."""
    global gallery_image_buffer

    try:
        filename_lower = filename.lower()

        if filename_lower.endswith('.jpg') or filename_lower.endswith('.jpeg'):
            print("Loading JPEG file: " + str(filename))
            bitmap = load_jpeg_file(filename)
            # JPEG files don't need a palette, so return None for palette
            return bitmap, None

        elif filename_lower.endswith('.gif'):
            print("Loading GIF file: " + str(filename))
            return load_gif_file(filename)  # Returns (bitmap, palette)

        else:
            print("Unsupported image format: " + str(filename))
            return None, None

    except Exception as e:
        print("Error loading image " + str(filename) + ": " + str(e))
        return None, None

def load_jpeg_file(filename):
    """Load a JPEG file using jpegio with appropriate scaling."""
    global jpeg_decoder, pycam

    if not jpeg_decoder:
        print("JPEG decoder not available")
        return None

    try:
        file_path = "/sd/" + filename

        # First, open the JPEG to get original dimensions
        original_width, original_height = jpeg_decoder.open(file_path)
        print("JPEG original dimensions: " + str(original_width) + "x" + str(original_height))

        # Use current zoom level from gallery controls
        scale = get_current_scale_factor()

        # Calculate scaled dimensions
        scale_factors = [1, 2, 4, 8]  # Corresponding to scale 0, 1, 2, 3
        scale_factor = scale_factors[scale]
        scaled_width = original_width // scale_factor
        scaled_height = original_height // scale_factor

        print("JPEG scaled dimensions: " + str(scaled_width) + "x" + str(scaled_height) + " (scale=" + str(scale) + ")")

        # Create a bitmap for the scaled image
        jpeg_bitmap = displayio.Bitmap(scaled_width, scaled_height, 65535)

        # Decode the JPEG into the bitmap with scaling
        jpeg_decoder.decode(jpeg_bitmap, scale=scale)

        print("Successfully loaded and scaled JPEG: " + str(filename))
        return jpeg_bitmap

    except Exception as e:
        print("Error loading JPEG: " + str(e))
        return None

def load_gif_file(filename):
    """Load a GIF file and return a bitmap using adafruit_imageload."""
    try:
        file_path = "/sd/" + filename

        # Use adafruit_imageload for proper GIF loading
        import adafruit_imageload

        with open(file_path, "rb") as f:
            bitmap, palette = adafruit_imageload.load(f, bitmap=displayio.Bitmap, palette=displayio.Palette)

            # Note: adafruit_imageload doesn't support automatic scaling like jpegio
            # Large GIFs will show only the top-left portion on the display
            # For best results, use GIFs that are 240x240 or smaller
            print("GIF loaded: " + str(bitmap.width) + "x" + str(bitmap.height))
            if bitmap.width > 240 or bitmap.height > 240:
                print("Warning: GIF is larger than display (240x240) - will be cropped")

            return bitmap, palette

    except Exception as e:
        print("Error loading GIF: " + str(e))
        return None, None

def display_current_image():
    """Show the current gallery image centred on the 240 × 240 TFT."""
    global gallery_index, gallery_images, pycam

    if not gallery_images or gallery_index >= len(gallery_images):
        pycam.display_message("No Image", color=0xFF0000)
        return

    current_file = gallery_images[gallery_index]
    loaded_bitmap, loaded_palette = load_image_file(current_file)
    if not loaded_bitmap:
        show_image_info_fallback(current_file)
        return

    # --- build the TileGrid ---------------------------------------------------
    if loaded_palette:   # GIF / paletted BMP
        tg = displayio.TileGrid(loaded_bitmap, pixel_shader=loaded_palette)
    else:                # JPEG (RGB565)
        tg = displayio.TileGrid(
            loaded_bitmap,
            pixel_shader=displayio.ColorConverter(
                input_colorspace=displayio.Colorspace.RGB565_SWAPPED)
        )

    # --- centre it ------------------------------------------------------------
    disp_w, disp_h = pycam.display.width, pycam.display.height  # 240 × 240  [oai_citation:0‡Adafruit Learning System](https://learn.adafruit.com/adafruit-memento-camera-board?view=all&utm_source=chatgpt.com)
    img_w,  img_h  = loaded_bitmap.width, loaded_bitmap.height

    # If the picture is larger than the screen we simply crop the centre.
    # (displayio supports integer upscale with tg.scale > 1, but cannot down-scale.)
    tg.x = (disp_w - img_w) // 2 if img_w <= disp_w else -(img_w - disp_w) // 2
    tg.y = (disp_h - img_h) // 2 if img_h <= disp_h else -(img_h - disp_h) // 2

    # Modern CircuitPython (≥ 9.0) alternative – one line:
    # tg.anchor_point = (0.5, 0.5); tg.anchored_position = (disp_w//2, disp_h//2)

    # --- place the bitmap in a *dedicated* overlay group so the built-in HUD is untouched
    if not hasattr(pycam, "gallery_group"):
        # first time we enter the gallery, create a group sitting on top of the HUD
        pycam.gallery_group = displayio.Group()
        pycam.display.root_group.append(pycam.gallery_group)

    # clear any previous frame from the overlay and add the new one
    while len(pycam.gallery_group):
        pycam.gallery_group.pop()
    pycam.gallery_group.append(tg)

    pycam.display.refresh()
    print(f"Displayed {current_file} – centred at ({tg.x}, {tg.y})")

def show_image_info_fallback(filename):
    """Show image information when actual image cannot be displayed."""
    global gallery_index, gallery_images, gallery_image_buffer

    try:
        import os
        file_path = "/sd/" + filename
        file_stats = os.stat(file_path)
        file_size = file_stats[6]  # File size in bytes
        size_kb = file_size // 1024

        # Determine file type
        filename_lower = filename.lower()
        if filename_lower.endswith('.jpg') or filename_lower.endswith('.jpeg'):
            format_info = "JPEG (load failed)"
        elif filename_lower.endswith('.gif'):
            format_info = "GIF (load failed)"
        else:
            format_info = "Unknown format"

        info_text = str(gallery_index + 1) + "/" + str(len(gallery_images)) + "\n" + filename + "\n" + format_info + "\n" + str(size_kb) + "KB"
    except Exception as e:
        print("Error getting file stats: " + str(e))
        info_text = str(gallery_index + 1) + "/" + str(len(gallery_images)) + "\n" + filename + "\nInfo unavailable"

    # Clear the display with a solid color background first
    if gallery_image_buffer is None:
        gallery_image_buffer = displayio.Bitmap(pycam.camera.width, pycam.camera.height, 65535)

    # Fill with a dark background
    for y in range(pycam.camera.height):
        for x in range(pycam.camera.width):
            gallery_image_buffer[x, y] = 0x0000  # Black background

    pycam.blit(gallery_image_buffer)
    pycam.display.refresh()  # Force display update
    pycam.display_message(info_text, color=0xFFFFFF)

def gallery_zoom_in():
    """Zoom in (smaller scale number = larger image)."""
    global gallery_zoom_level

    if gallery_zoom_level > 1:
        gallery_zoom_level -= 1
        print("Zooming in to level " + str(gallery_zoom_level))
        display_current_image()
    else:
        print("Already at maximum zoom")

def gallery_zoom_out():
    """Zoom out (larger scale number = smaller image)."""
    global gallery_zoom_level

    if gallery_zoom_level < 3:  # Don't go beyond scale 3
        gallery_zoom_level += 1
        print("Zooming out to level " + str(gallery_zoom_level))
        display_current_image()
    else:
        print("Already at minimum zoom")

def gallery_navigate(direction):
    """Navigate to previous (-1) or next (+1) image in gallery."""
    global gallery_index, gallery_images

    if not gallery_images:
        return

    # Clean up previous image from memory before loading new one
    try:
        import gc
        gc.collect()  # Free memory from previous image
    except Exception:
        pass

    gallery_index += direction

    # Wrap around at boundaries
    if gallery_index < 0:
        gallery_index = len(gallery_images) - 1
    elif gallery_index >= len(gallery_images):
        gallery_index = 0

    display_current_image()

def handle_all_buttons():
    """Process all button inputs."""
    pycam.keys_debounce()

    if gallery_mode:
        handle_gallery_buttons()
    else:
        handle_camera_buttons()

def handle_gallery_buttons():
    """Handle button inputs when in gallery mode."""
    # Check if SD card is still available
    if not is_sd_card_available():
        print("SD card removed while in gallery mode")
        pycam.display_message("SD Card\nRemoved", color=0xFF0000)
        time.sleep(1)
        exit_gallery_mode()
        return

    if pycam.left.fell:
        print("Gallery: Previous image")
        gallery_navigate(-1)

    if pycam.right.fell:
        print("Gallery: Next image")
        gallery_navigate(1)

    if pycam.select.fell:
        handle_select_button()  # Exit gallery

    if pycam.shutter.short_count:
        print("Gallery: Exit via shutter")
        exit_gallery_mode()

    # Up/Down for zoom control
    if pycam.up.fell:
        print("Gallery: Zoom in")
        gallery_zoom_in()

    if pycam.down.fell:
        print("Gallery: Zoom out")
        gallery_zoom_out()

def handle_camera_buttons():
    """Handle button inputs when in camera mode."""
    handle_shutter_button()
    handle_navigation_buttons()

    if pycam.select.fell:
        handle_select_button()

    if pycam.ok.fell:
        handle_ok_button()

def init_camera_system():
    """Initialize camera and related systems."""
    global pycam, last_frame, onionskin, last_recorded_time, gallery_image_buffer, jpeg_decoder

    print("Initializing camera system...")
    pycam = adafruit_pycamera.PyCamera()

    # Initialize frame buffers
    last_frame = displayio.Bitmap(pycam.camera.width, pycam.camera.height, 65535)
    onionskin = displayio.Bitmap(pycam.camera.width, pycam.camera.height, 65535)
    gallery_image_buffer = displayio.Bitmap(pycam.camera.width, pycam.camera.height, 65535)

    # Initialize JPEG decoder for gallery
    try:
        jpeg_decoder = jpegio.JpegDecoder()
        print("JPEG decoder initialized")
    except Exception as e:
        print("JPEG decoder initialization failed: " + str(e))
        jpeg_decoder = None

    # Initialize timing
    last_recorded_time = time.time()

    print("Camera system ready!")

def main():
    """Main application entry point."""
    print("Starting Adafruit MEMENTO Camera...")

    # Initialize all systems
    setup_wifi_and_time()
    init_battery_monitoring()
    init_camera_system()

    print("Entering main loop...")

    # Main application loop
    while True:
        # Update battery status periodically
        update_battery_status()

        # Only handle camera modes and preview when not in gallery mode
        if not gallery_mode:
            # Handle camera modes and preview
            handle_camera_modes()

        # Process user input
        handle_all_buttons()

        # Handle SD card events (but not when in gallery mode to avoid conflicts)
        if not gallery_mode:
            handle_sd_card_events()

if __name__ == "__main__":
    main()
