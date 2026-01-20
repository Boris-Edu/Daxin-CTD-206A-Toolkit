CTD-206A Sensor Toolkit

Python utilities for reading, logging, and calibrating the CTD-206A Conductivity, Temperature, and Depth sensor via Modbus RTU.

## Files

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
