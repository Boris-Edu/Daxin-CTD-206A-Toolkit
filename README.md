# Daxin CTD-206A & LoRaWAN Integration Toolkit

This repository provides the utilities to support integration of the **Daxin CTD-206A** sensor with **Dragino LoRaWAN converters** for autonomous, long-range environmental monitoring.
 
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
    AT+TDC=300000, AT+5VT=10000
    ```

* **Modbus Polling:** This command initiates a read of the Modbus registers:
    ```bash
    AT+COMMAND1=01 03 00 00 00 06 c5 c8 ,0
    ```

* **Payload Orchestration:** This command handles data slicing. It captures the first 17 bytes, ignores the first 3 bytes (containing the sensor's address, function code, and byte count), and transmits the critical 12 bytes containing the sensor data (bytes 4 through 15):
    ```bash
    AT+DATACUT1=12,2,4 17
    ```
    
# Python Scripts
 
1.  **`*_control.py`**: 
    * Reads live data from the sensor.
    * Logs data to CSV.
    * Performs single-point and multi-point calibration.
2.  **`*_visualize.py`**:
    * Visualizes response time and steady-state values from generated CSV logs.

## Setup
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
