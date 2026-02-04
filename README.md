CTD-206A Sensor Toolkit


## Configuration of the Converter
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
