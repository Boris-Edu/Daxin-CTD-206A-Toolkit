# Daxin CTD-206A & LoRaWAN Integration Toolkit

This repository provides the utilities and documentation required to integrate the **Daxin CTD-206A** sensor with **Dragino LoRaWAN converters** for autonomous, long-range environmental monitoring.

## About the Daxin CTD-206A
The Daxin CTD-206A is a cost-effective, industrial-grade submerged transducer designed for high-resolution monitoring of water bodies. It utilizes a Modbus RTU (RS485) interface to provide three critical environmental parameters:
* **Conductivity:** Measured via a four-pole graphite probe, providing specific conductivity normalized to $25^{\circ}\text{C}$.
* **Temperature:** Captured using a high-precision PT1000 RTD.
* **Depth (Pressure):** Determined through a vented piezoresistive transducer to account for barometric pressure changes.

## System Integration
This toolkit focuses on the integration of the sensor with the **Dragino RS485-LB** LoRaWAN converter. This combination allows for:
* **Telemetry without Recurring Fees:** Utilizing the LoRaWAN protocol via The Things Network (TTN).
* **Energy Autonomy:** Support for solar-powered operation with positive energy balance.
* **Remote Configuration:** Using AT commands to manage sampling intervals and payload orchestration.

## Product Information
For detailed hardware specifications and purchasing, refer to the official product pages:
* **Daxin CTD-206A Sensor:** [Daxin Technology Official Site](http://www.daxinsensor.com/en/index.php?m=content&c=index&a=show&catid=10&id=46)
* **Dragino RS485-LB Converter:** [Dragino RS485-LB Product Page](https://www.dragino.com/products/lora-lorawan-end-node/item/203-rs485-lb.html)

## Contents
* `calibration/`: Python scripts for automated multi-point sensor calibration.
* `telemetry/`: AT command sequences and payload decoders for Dragino converters.
* `analysis/`: Jupyter notebooks for characterizing sensor bias and dispersion.

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
