# Additional Library Requirements

## Required Library for Gallery Functionality

The gallery feature requires the `adafruit_imageload` library to properly display GIF images.

### Installation Steps:

1. Download the Adafruit CircuitPython Library Bundle from:
   https://circuitpython.org/libraries

2. Extract the bundle and copy the following to your `lib/` folder:
   - `adafruit_imageload/` (entire folder)

3. The library should be placed at:
   ```
   lib/adafruit_imageload/
   ├── __init__.py
   ├── bmp/
   ├── gif/
   ├── png/
   └── ...
   ```

### Supported Image Formats:

- **JPEG**: Fully supported with automatic scaling through built-in jpegio module
- **GIF**: Supported through adafruit_imageload (large GIFs will be cropped to display size)
- **BMP**: Supported through adafruit_imageload 
- **PNG**: Limited support (indexed color only) through adafruit_imageload

### Image Scaling Behavior:

- **JPEG files**: Automatically scaled down to fit the 240x240 display using hardware-accelerated scaling
- **GIF/BMP/PNG files**: Displayed at original size (large images cropped, small images centered)
- **Recommended sizes**: For best results with GIF files, use images 240x240 or smaller

### Memory Considerations:

The `adafruit_imageload` library is designed for memory-constrained devices and loads images efficiently. Images are loaded on-demand and memory is cleaned up between image navigations.

### Fallback Behavior:

- **JPEG images**: Use built-in jpegio module, no additional library needed
- **Other formats**: If adafruit_imageload is not installed, the gallery will show informational placeholders for GIF/BMP/PNG files