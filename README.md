# Daxin CTD-206A & LoRaWAN Integration Toolkit

This repository provides the utilities to support integration of the **Daxin CTD-206A** sensor with **Dragino LoRaWAN converters** for autonomous, long-range environmental monitoring.

<img width="1445" height="765" alt="ToolBoxScreenshots" src="https://github.com/user-attachments/assets/58640347-3da4-424b-8d2f-e87163196779" />

## About the Daxin CTD-206A
The Daxin CTD-206A is a cost-effective, industrial-grade submerged transducer designed for high-resolution monitoring of water bodies.

## Product Information
For detailed hardware specifications and purchasing, refer to the official product pages:
* **Daxin CTD-206A Sensor:** [Daxin Technology Official Site](http://www.daxinsensor.com/en/index.php?m=content&c=index&a=show&catid=10&id=46)
* **Dragino RS485-LB Converter:** [Dragino RS485-LB Product Page](https://www.dragino.com/products/lora-lorawan-end-node/item/203-rs485-lb.html)

# TTN Payload Formatter

This repository includes a specialized JavaScript payload formatter (`TTN_PayloadFormatter.js`) designed for **The Things Stack (v3)**. It serves as the bridge between raw LoRaWAN radio packets and actionable environmental data.

## Key Features
* **Modbus CRC-16 Verification:** Unlike standard decoders, this script re-calculates the Modbus checksum for every packet. This ensures that only data with 100% integrity is passed to your database.
* **Automatic Unit Normalization:** The formatter lets you indicate the sensor's measurement mode (µS/cm vs. mS/cm) and scales all values to the chosen unit (µS/cm or ms/cm).

## How to Use
1.  Navigate to your **Application** on The Things Stack Console.
2.  Go to **Payload Formatters** > **Uplink**.
3.  Select **Formatter type: JavaScript**.
4.  Copy and paste the contents of `TTN_PayloadFormatter.js` into the editor.
5.  Click **Save changes**.

Once active, your "Live Data" tab will display formatted JSON objects containing real-time values like `conductivity_uS_cm`, `temp_C`, and `depth_m`.

# Configuration of the Converter
The Dragino RS485-LS LoRaWAN converter must be configured using the sequence of AT commands listed below to poll the Daxin sensor via Modbus and create the LoRaWAN payload.

* **Sampling and Stabilization:** These commands set the sampling frequency to 5 minutes (300,000 ms) and provide a 10 s (10,000 ms) stabilization period to ensure sensor readings have settled before transmission:
    ```bash
    AT+TDC=300000 
    ```
    ```bash
    AT+5VT=10000 
    ```
* **Modbus Polling:** This command initiates a read of the Modbus registers:
    ```bash
    AT+COMMAND1=01 03 00 00 00 06 c5 c8, 0
    ```

* **Payload Orchestration:** This command handles data slicing. It captures the first 17 bytes, ignores the first 3 bytes (containing the sensor's address, function code, and byte count), and transmits the critical 12 bytes containing the sensor data (bytes 4 through 15):
    ```bash
    AT+DATACUT1=12,2,4~17
    ```
    
# Python ToolBox
This toolkit provides a comprehensive graphical user interface and Python API for interacting with the Daxin CTD-206A sensor via Modbus RTU protocol.

## Components

### 1. **`Daxin_CTD206A_UI.py`** - Graphical User Interface
A full-featured desktop application built with Tkinter that provides:

#### Real-Time Monitoring
* **Live sensor readings** with large, color-coded displays for:
  * Conductivity (µS/cm or dS/cm)
  * Temperature (°C)
  * Liquid Level (mm)
* **Dynamic plot visualization** with auto-scaling axes
* **Configurable sampling rate** (default: 0.5 seconds)
* **Adjustable time window** (default: 60 seconds)

#### Data Logging
* **CSV export** with timestamped measurements
* **Modbus packet logging** for debugging and protocol analysis
* Live/Stop logging controls
* Color-coded log viewer (TX, RX, parsed data, errors)

#### Calibration Tools
* **Conductivity Calibration:**
  * Zero calibration (sensor in air)
  * Single-point slope calibration (with standard solution)
  * Multi-point slope calibration (up to 5 points)
* **Level/Depth Calibration:**
  * Zero calibration (sensor in air)
  * Slope calibration (known depth)
* **Temperature Calibration:**
  * Offset adjustment (0.1°C resolution)

#### Advanced Features
* **Conductivity unit switching** (µS/cm ↔ dS/cm)
* **Measurement mode selection** (conductivity, TDS, salinity)
* **Auto-refresh COM port detection**
* **Dark mode visualization** with color-coded axes
* **Button state management** (calibration disabled during logging/reading)

### 2. **`Daxin_CTD206A_functions.py`** - Python API
Low-level Python functions for Modbus communication and sensor control:

#### Communication Functions
* `calculate_crc()` - Modbus CRC-16 checksum calculation
* `get_measurements_fast()` - Fast polling for continuous data acquisition
* `start_continuous_read_loop()` - Terminal-based live monitoring
* `log_data_to_csv()` - Command-line data logging

#### Calibration Functions
* `calibrate_cond_zero()` - Conductivity zero point calibration
* `calibrate_cond_single_point_slope()` - Single standard calibration
* `calibrate_cond_multi_point_slope()` - Multi-point calibration (1-5 points)
* `calibrate_level_zero()` - Depth zero point (P0)
* `calibrate_level_slope()` - Depth slope calibration
* `calibrate_temperature_offset()` - Temperature offset adjustment

#### Configuration Functions
* `set_conductivity_mode()` - Switch between µS/cm, mS/cm, TDS (ppm), Salinity (ppt)
* `check_calibration_success()` - Response validation for write commands

#### Data Parsing
* `_parse_measurement_data()` - Decodes raw Modbus payload with automatic decimal scaling
* `_validate_read_response()` - CRC validation and error detection

## Setup
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Connect the CTD-206A sensor via RS485-to-USB adapter

3. Launch the UI application:
   ```bash
   python Daxin_CTD206A_UI.py
   ```

## Usage Examples

### Using the UI
1. Select your COM port from the dropdown
2. Click **Connect**
3. Click **Start** to begin reading data
4. Use **Log CSV** to save measurements to file
5. Perform calibrations when sensor is stable and not actively logging

### Using the Python API
```python
import serial
import Daxin_CTD206A_functions as ctd

# Connect to sensor
ser = serial.Serial('COM3', 9600, timeout=1)

# Read single measurement
data = ctd.get_measurements_fast(ser)
print(f"Conductivity: {data['conductivity']} µS/cm")
print(f"Temperature: {data['temperature_celsius']} °C")

# Perform zero calibration (sensor in air)
success, msg = ctd.calibrate_cond_zero(ser)
print(msg)

# Calibrate with 1413 µS/cm standard
success, msg = ctd.calibrate_cond_single_point_slope(ser, 1413)
print(msg)
```

## License
MIT License - Free to use, modify, and distribute. See file headers for full license text.

This software can be reused and improved for future sensor versions (note: future versions may use different Modbus registers).

## Acknowledgments
This work was developed at the **East Carolina University Water Resources Center (WRC)**, Department of Earth, Environment and Planning.

**Funding:** This work was supported by the National Science Foundation under Grant No. 2052889.

**Authors:** Boris Dessimond, Alex K. Manda, Stephen Moysey, Robert Howard, Char'Rese Finney
