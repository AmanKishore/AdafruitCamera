# Adafruit MEMENTO Camera Board Setup Guide

This guide covers the complete setup and development process for the Adafruit MEMENTO Camera Board with CircuitPython.

## Hardware Overview

The MEMENTO Camera Board is a powerful ESP32-S3 based development board designed for camera and vision projects.

### Key Specifications
- **Processor**: ESP32-S3 (240 MHz dual-core) with 4MB Flash, 2MB PSRAM
- **Camera**: 5MP OV5640 with auto-focus (72° viewing angle)
- **Display**: 1.54" 240x240 color TFT (ST7789 driver)
- **Storage**: MicroSD card slot (supports up to 32GB)
- **Connectivity**: WiFi, USB-C, I2C Stemma QT
- **Sensors**: LIS3DH accelerometer, analog microphone
- **Interface**: 6 user buttons, buzzer, NeoPixel LED
- **Power**: USB-C or LiPoly battery with charging circuit

### Physical Connections
- **Two Stemma ports**: GPIO17 (A0) and GPIO18 (A1) for analog/digital sensors
- **I2C/Stemma QT**: GPIO34 (SDA) and GPIO33 (SCL)
- **Battery monitoring**: Available via GPIO
- **Expansion**: Multiple GPIO pins accessible for custom interfacing

## CircuitPython Setup

### 1. Install CircuitPython Firmware

1. Download the latest CircuitPython firmware for ESP32-S3 from [circuitpython.org](https://circuitpython.org/board/adafruit_camera_esp32s3/)
2. Connect the MEMENTO board via USB-C
3. Put the board into bootloader mode:
   - Hold the BOOT button while pressing and releasing RESET
   - The board should appear as a USB drive named "CAMERA"
4. Copy the `.uf2` firmware file to the drive
5. The board will restart automatically with CircuitPython installed

### 2. Initial File System Setup

After CircuitPython is installed, the board will appear as a drive named "CIRCUITPY":

1. **Create SD card mount point** (required for CircuitPython 9+):
   - Open the CIRCUITPY drive in your file manager
   - Create a new folder named `sd`
   - This enables proper SD card mounting and web workflow access

2. **Verify installation**:
   - The drive should contain `boot_out.txt` showing CircuitPython version
   - You should see `code.py` and `lib/` folder

### 3. Install Required Libraries

Copy the required libraries to the `lib/` folder on the CIRCUITPY drive:

**Essential Libraries:**
- `adafruit_pycamera/` - Main camera control library
- `adafruit_display_text/` - Text rendering
- `adafruit_debouncer.mpy` - Button debouncing
- `adafruit_lis3dh.mpy` - Accelerometer
- `adafruit_requests.mpy` - HTTP requests
- `adafruit_ntp.mpy` - Network time protocol
- `neopixel.mpy` - LED control

**Download from**: [Adafruit CircuitPython Library Bundle](https://circuitpython.org/libraries)

## WiFi Configuration

Create a `settings.toml` file in the root of the CIRCUITPY drive:

```toml
# WiFi credentials
CIRCUITPY_WIFI_SSID = "YourNetworkName"
CIRCUITPY_WIFI_PASSWORD = "YourPassword"

# Timezone (optional)
TZ = "America/New_York"
# Or use UTC offset directly:
# UTC_OFFSET = -18000
```

**Security Note**: Add `settings.toml` to your `.gitignore` file to prevent committing WiFi credentials.

## Development Workflow

### 1. Code Structure

- **`code.py`**: Main application entry point (auto-runs on boot)
- **`boot.py`**: Boot-time configuration (runs before code.py)
- **`lib/`**: CircuitPython libraries
- **`settings.toml`**: Configuration and secrets

### 2. Development Process

1. **Edit code**: Use any text editor to modify files on the CIRCUITPY drive
2. **Auto-reload**: CircuitPython automatically restarts when files are saved
3. **Serial monitor**: Connect via serial terminal to see debug output
4. **File transfer**: Simply copy/paste files to the drive - no compilation needed

### 3. Recommended Editors

- **Mu Editor**: Beginner-friendly with built-in serial monitor
- **VS Code**: With Python and CircuitPython extensions
- **Any text editor**: Files are plain Python scripts

### 4. Testing and Debugging

```python
# Add debug prints to your code
print("Camera initialized")
print(f"Battery voltage: {battery_voltage}V")

# Use try/except for error handling
try:
    pycam.capture_jpeg()
    print("Photo captured successfully")
except RuntimeError as e:
    print(f"Capture failed: {e}")
```

## Camera Application Features

The included camera application supports multiple capture modes:

- **JPEG**: Standard photo capture with autofocus
- **GIF**: Animated recording (15 frames or until button release)
- **STOP**: Stop-motion animation with onion-skin overlay
- **GBOY**: Game Boy style dithered images
- **LAPS**: Time-lapse photography with configurable intervals

### Button Controls

- **Shutter**: Capture photo/start recording
- **Up/Down**: Adjust current setting value
- **Left/Right**: Navigate between settings
- **Select**: Display battery status / toggle time-lapse power mode
- **OK**: Start/stop time-lapse mode

### Settings Navigation

Use directional buttons to adjust:
- Resolution (various sizes supported by OV5640)
- Visual effects (normal, negative, sepia, etc.)
- Capture mode selection
- LED brightness and color
- Time-lapse interval rates

## Hardware Integration Examples

### Battery Monitoring
```python
import analogio
import board

battery_pin = analogio.AnalogIn(board.BATTERY_MONITOR)
voltage = (battery_pin.value / 65535) * 3.3 * 2
percentage = calculate_battery_percentage(voltage)
```

### Accelerometer Access
```python
import adafruit_lis3dh
import busio

i2c = busio.I2C(board.SCL, board.SDA)
lis3dh = adafruit_lis3dh.LIS3DH_I2C(i2c)
acceleration = lis3dh.acceleration
```

### NeoPixel Control
```python
import neopixel
import board

pixel = neopixel.NeoPixel(board.NEOPIXEL, 1)
pixel[0] = (255, 0, 0)  # Red
```

## Troubleshooting

### Common Issues

**1. macOS File System Corruption**
- **Symptom**: Files appear corrupted or incomplete
- **Solution**: Run the included `remount-CIRCUITPY.sh` script before file transfers
- **Cause**: macOS 14.x delayed write issue

**2. SD Card Not Detected**
- **Symptom**: "No SD Card" error messages
- **Solutions**:
  - Ensure `/sd` folder exists on CIRCUITPY drive
  - Check SD card is properly inserted
  - Try reformatting SD card (FAT32)
  - Check card size (32GB maximum)

**3. WiFi Connection Fails**
- **Symptom**: "Wifi failed to connect" message
- **Solutions**:
  - Verify `settings.toml` credentials
  - Check WiFi network is 2.4GHz (ESP32-S3 doesn't support 5GHz)
  - Ensure network allows new device connections

**4. Camera Initialization Errors**
- **Symptom**: Black screen or camera failure
- **Solutions**:
  - Check all library files are present in `lib/`
  - Verify CircuitPython version compatibility
  - Power cycle the device
  - Check for adequate power supply (USB-C or charged battery)

**5. Memory Errors**
- **Symptom**: MemoryError exceptions
- **Solutions**:
  - Use `.mpy` compiled libraries instead of `.py` files
  - Reduce image resolution settings
  - Limit number of stored variables

### Performance Optimization

- Use compiled libraries (`.mpy` files) for better memory efficiency
- Implement garbage collection in long-running loops:
  ```python
  import gc
  gc.collect()  # Free unused memory
  ```
- Monitor available memory:
  ```python
  import gc
  print(f"Free memory: {gc.mem_free()} bytes")
  ```

## Development Tips

1. **Start simple**: Begin with basic camera preview before adding features
2. **Test incrementally**: Add one feature at a time to isolate issues
3. **Use version control**: Track your code changes with git
4. **Read documentation**: Refer to [CircuitPython](https://docs.circuitpython.org/) and [Adafruit PyCamera](https://docs.circuitpython.org/projects/pycamera/en/latest/) docs
5. **Monitor serial output**: Essential for debugging and development feedback

## Additional Resources

- [Adafruit MEMENTO Learning Guide](https://learn.adafruit.com/adafruit-memento-camera-board)
- [CircuitPython Documentation](https://docs.circuitpython.org/)
- [PyCamera Library Reference](https://docs.circuitpython.org/projects/pycamera/en/latest/)
- [ESP32-S3 Datasheet](https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf)
- [Adafruit Discord Community](https://adafru.it/discord)

## License

This project is released under the Unlicense. See the SPDX headers in source files for full license information.