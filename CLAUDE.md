# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a CircuitPython project for an Adafruit ESP32-S3 camera device. The project implements a smart camera with multiple capture modes including JPEG photography, GIF recording, stop-motion animation, time-lapse photography, and "Game Boy" style dithered images.

## Hardware Platform

- **Target Device**: Adafruit ESP32-S3 camera board
- **Firmware**: CircuitPython 9.1.1
- **Storage**: SD card support for image/video storage
- **Display**: Built-in display for preview and UI
- **Controls**: Physical buttons for navigation and capture

## Key Files

- `code.py` - Main application entry point with camera control logic
- `boot.py` - Boot-time setup that creates SD card mount point
- `lib/` - CircuitPython libraries (compiled .mpy files)
- `CAMERABOOT/` - Contains CircuitPython firmware for flashing
- `remount-CIRCUITPY.sh` - macOS utility script to fix filesystem mounting issues

## Development Environment

### File Transfer
Files are transferred directly to the CircuitPython device filesystem (usually mounted as `CIRCUITPY` drive). No traditional build process is required - CircuitPython runs the code directly.

### Configuration
WiFi and timezone settings are configured via environment variables in a `settings.toml` file (not included in repo):
- `CIRCUITPY_WIFI_SSID` - WiFi network name
- `CIRCUITPY_WIFI_PASSWORD` - WiFi password  
- `TZ` - Timezone (e.g., "America/Phoenix")
- `UTC_OFFSET` - Manual UTC offset override (optional)

### macOS Development Workaround
Run `./remount-CIRCUITPY.sh` to fix file system corruption issues on macOS 14.x systems when writing to the CircuitPython device.

## Architecture

### Core Components

1. **PyCamera Class** (`adafruit_pycamera` library) - Main camera interface providing:
   - Live preview mode
   - Image capture (JPEG)
   - Video recording (GIF)
   - Camera settings control (resolution, effects, LED)
   - UI management and button handling

2. **Capture Modes**:
   - **JPEG** - Standard photo capture with autofocus
   - **GIF** - Animated GIF recording (15 frames or until button release)
   - **STOP** - Stop-motion animation with onion-skin overlay
   - **GBOY** - Game Boy style dithered single-frame capture
   - **LAPS** - Time-lapse photography with configurable intervals

3. **Hardware Integration**:
   - WiFi connectivity for NTP time synchronization
   - Battery voltage monitoring with percentage calculation
   - SD card hot-swap detection and mounting
   - Physical button interface (shutter, navigation, settings)

### Main Loop Structure
The application runs in a continuous loop handling:
- Camera preview updates based on current mode
- Button input processing and debouncing
- SD card insertion/removal events
- Battery monitoring (every 10 seconds)
- Time-lapse scheduling and execution

### Settings System
Navigation through camera settings using directional buttons:
- Resolution selection
- Visual effects
- Capture mode
- LED brightness and color
- Time-lapse interval rates

## Common Tasks

### Testing Changes
1. Save modified files to the CircuitPython device
2. Device automatically reloads and runs updated code
3. Monitor serial output for debugging information

### Adding New Capture Modes
Extend the mode handling logic in the main loop around line 123-178 in `code.py`, following the pattern of existing modes.

### Modifying UI Elements
PyCamera library handles most UI rendering. Access labels and display elements through the `pycam` object methods.

## Modification Guidelines

- **code.py Modifications**:
  - Only modify code.py when making changes to the core application logic
  - Ensure backwards compatibility with existing capture modes
  - Test thoroughly after any modifications