CTD-206A Sensor Toolkit

## Configuration of the Converter
The Dragino RS485-LS LoRaWAN converter must be configured using the sequence of AT commands listed below to poll the Daxin sensor via Modbus and create the LoRaWAN payload.
**Sampling and Power Management:** These commands set the sampling frequency to 5 minutes ( ms), with a 10 s ( ms) stabilization period:
`AT+TDC=300000`
`AT+5VT=10000`
**Modbus Polling:** Read the Modbus registers:
`AT+COMMAND1=01 03 00 00 00 06 c5 c8 ,0`
**Payload Orchestration:** Get the first 17 bytes, ignore the unnecessary first 3 bytes (containing sensor's address, function code and number of bytes), and transmit the remaining 12 bytes (4th to 15th):
`AT+DATACUT1=12,2,4 17`

## Configuration of the Converter


## Python Utility

1.  **`ctd_control.py`**: 
    * Reads live data from the sensor.
    * Logs data to CSV.
    * Performs single-point and multi-point calibration.
2.  **`visualize_response.py`**:
    * Visualizes response time and steady-state values from generated CSV logs.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
