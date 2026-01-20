#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CTD-206A Sensor Control & Calibration Script

This script provides functions to read from and calibrate the CTD-206A 
sensor via MODBUS-RTU. It supports:
- Real-time data logging to CSV
- Conductivity Calibration (Zero, Single-Point Slope, Multi-Point Slope)
- Level/Depth Calibration (Zero, Slope)

Dependencies:
- pyserial
"""

import serial
import time
from datetime import datetime
import os
import csv

# --- Configuration ---
# UPDATE THIS PORT BEFORE RUNNING
SERIAL_PORT = 'COM32'  # Windows: 'COMx', Linux: '/dev/ttyUSBx'

# Sensor Settings
BAUDRATE = 9600
PARITY = serial.PARITY_NONE
STOPBITS = serial.STOPBITS_ONE
BYTESIZE = serial.EIGHTBITS
TIMEOUT = 1
DEFAULT_ADDRESS = 1

# --- Core MODBUS Functions ---

def calculate_crc(data: bytearray) -> int:
    """Calculates the MODBUS CRC16 for a given bytearray."""
    crc = 0xFFFF
    polynomial = 0xA001

    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ polynomial
            else:
                crc >>= 1
    return crc

def check_calibration_success(request_frame: bytes, response_frame: bytes) -> (bool, str):
    """
    Validates the sensor's response to a write command.
    A successful write returns the exact same frame as the request.
    """
    if not response_frame:
        return False, "Error: No response from sensor. Check connection and timeout."

    # 1. Primary Success Condition: Response matches request
    if request_frame == response_frame:
        return True, "Success: Sensor acknowledged command."

    # 2. Check for CRC mismatch in the response
    if len(response_frame) < 4:
        return False, f"Error: Response is too short. Got: {response_frame.hex(' ')}"
        
    data_part = response_frame[:-2]
    received_crc = int.from_bytes(response_frame[-2:], 'little')
    calculated_crc = calculate_crc(bytearray(data_part))

    if received_crc != calculated_crc:
        return False, f"Error: Response CRC mismatch. Got: {response_frame.hex(' ')}"

    # 3. Check for standard MODBUS error frame
    if len(response_frame) == 5 and response_frame[1] == (request_frame[1] | 0x80):
        error_code = response_frame[2]
        error_messages = {
            0x01: "Function code error",
            0x02: "Register address error",
            0x03: "Data error"
        }
        message = error_messages.get(error_code, "Unknown error code")
        return False, f"Sensor Error (Code {error_code}): {message}."

    return False, f"Error: Unexpected response. Got: {response_frame.hex(' ')}"

def _send_calibration_frame(ser: serial.Serial, device_address: int, register: int, data_value: int) -> (bool, str):
    """
    Internal helper to build, send, and validate a Write Single Register (0x06) command.
    """
    frame = bytearray()
    frame.append(device_address)
    frame.append(0x06)  # Function Code 0x06
    frame.extend(register.to_bytes(2, 'big'))
    frame.extend(data_value.to_bytes(2, 'big'))

    crc = calculate_crc(frame)
    frame.extend(crc.to_bytes(2, 'little'))

    print(f"  > Sending Frame: {frame.hex(' ')}")

    try:
        ser.flushInput()
        ser.flushOutput()
        ser.write(frame)
        
        # Wait for device to process (write commands can be slow)
        time.sleep(2) 
        
        response = ser.read(ser.in_waiting)
        print(f"  < Rcvd Frame:  {response.hex(' ')}")

        return check_calibration_success(frame, response)

    except Exception as e:
        return False, f"Serial Communication Error: {e}"

# --- User-Facing Calibration Functions ---

def calibrate_cond_zero(ser: serial.Serial, device_address: int = 1, multi_point_mode: bool = False):
    """
    Performs a ZERO calibration for Conductivity.
    Physical Step: Sensor in air, dry, vertical.
    """
    if multi_point_mode:
        register = 0x1050
        print("Starting Conductivity ZERO Calibration (Multi-Point Mode)...")
    else:
        register = 0x1000
        print("Starting Conductivity ZERO Calibration (Single-Point Mode)...")
        
    return _send_calibration_frame(ser, device_address, register, 0x0000)

def calibrate_cond_single_point_slope(ser: serial.Serial, standard_value_us: int, device_address: int = 1):
    """
    Performs a SINGLE-POINT SLOPE calibration for Conductivity.
    Physical Step: Sensor in known standard solution.
    """
    register = 0x1004
    print(f"Starting Conductivity SINGLE-POINT SLOPE Calibration to {standard_value_us} uS/cm...")
    return _send_calibration_frame(ser, device_address, register, standard_value_us)

def calibrate_cond_multi_point_slope(ser: serial.Serial, point_index: int, standard_value_us: int, device_address: int = 1):
    """
    Performs one point of a MULTI-POINT SLOPE calibration.
    Physical Step: Calibrate in ascending order (Cal1 < Cal2 < ...).
    """
    point_registers = {
        1: 0x1054, 2: 0x1058, 3: 0x105C, 4: 0x1060, 5: 0x1064
    }
    
    if point_index not in point_registers:
        print(f"Error: Invalid point_index {point_index}. Must be 1-5.\n")
        return False
        
    register = point_registers[point_index]
    print(f"Starting Conductivity MULTI-POINT SLOPE Calibration (Point {point_index}) to {standard_value_us} uS/cm...")
    return _send_calibration_frame(ser, device_address, register, standard_value_us)

def calibrate_level_zero(ser: serial.Serial, device_address: int = 1):
    """
    Performs a ZERO calibration for Liquid Level (P0).
    Physical Step: Sensor in air, dry, vertical.
    """
    print("Starting Level ZERO Calibration (P0)...")
    return _send_calibration_frame(ser, device_address, 0x1030, 0x0000)

def calibrate_level_slope(ser: serial.Serial, known_level_mm: int, device_address: int = 1):
    """
    Performs a SLOPE calibration for Liquid Level.
    Physical Step: Sensor in liquid with known depth (mm).
    """
    print(f"Starting Level SLOPE Calibration to {known_level_mm} mm...")
    return _send_calibration_frame(ser, device_address, 0x1034, known_level_mm)

# --- Reading Functions ---

def _validate_read_response(request_frame: bytes, response_frame: bytes) -> (bool, bytes | str):
    if not response_frame:
        return False, "Error: No response from sensor."

    # Check for Error Frame
    if len(response_frame) == 5 and response_frame[1] == (request_frame[1] | 0x80):
        return False, f"Sensor Error Code: {response_frame[2]}"

    # Validate Length, Address, Function, CRC
    if len(response_frame) < 5:
        return False, "Error: Response too short."
    
    data_part = response_frame[:-2]
    received_crc = int.from_bytes(response_frame[-2:], 'little')
    if received_crc != calculate_crc(bytearray(data_part)):
        return False, "Error: CRC Mismatch."

    if response_frame[0] != request_frame[0] or response_frame[1] != request_frame[1]:
        return False, "Error: Header mismatch."

    # Extract Payload
    # Request asks for 6 regs (12 bytes). Response format: [Addr][Func][ByteCount][Data...][CRC]
    expected_bytes = 12
    if response_frame[2] != expected_bytes:
        return False, f"Error: Expected {expected_bytes} bytes, got {response_frame[2]}."

    return True, response_frame[3:-2]

def _parse_measurement_data(data_payload: bytes) -> dict:
    """Parses the raw 12-byte payload into engineering units."""
    # Conductivity
    cond_val = int.from_bytes(data_payload[0:2], 'big', signed=False)
    cond_dec = int.from_bytes(data_payload[2:4], 'big', signed=False)
    conductivity = cond_val / (10**cond_dec) if cond_dec > 0 else cond_val

    # Temperature
    temp_val = int.from_bytes(data_payload[4:6], 'big', signed=True)
    temp_dec = int.from_bytes(data_payload[6:8], 'big', signed=False)
    temp_c = temp_val / (10**temp_dec) if temp_dec > 0 else temp_val
    temp_f = temp_c * 9/5 + 32

    # Level
    level_val = int.from_bytes(data_payload[8:10], 'big', signed=False)
    level_dec = int.from_bytes(data_payload[10:12], 'big', signed=False)
    level_mm = level_val / (10**level_dec) if level_dec > 0 else level_val

    return {
        'conductivity': conductivity,
        'temperature_celsius': temp_c,
        'temperature_fahrenheit': temp_f,
        'liquid_level_mm': level_mm
    }

def get_measurements_fast(ser: serial.Serial, device_address: int = 1) -> dict | None:
    """Reads measurements quietly (optimized for loops). Returns None on error."""
    frame = bytearray()
    frame.append(device_address)
    frame.append(0x03)
    frame.extend([0x00, 0x00, 0x00, 0x06]) # Start 0, Len 6
    frame.extend(calculate_crc(frame).to_bytes(2, 'little'))

    try:
        ser.flushInput()
        ser.write(frame)
        time.sleep(0.5)
        response = ser.read(ser.in_waiting)
        is_valid, payload = _validate_read_response(frame, response)
        return _parse_measurement_data(payload) if is_valid else None
    except Exception:
        return None

def start_continuous_read_loop(ser: serial.Serial, device_address: int = 1, interval_sec: float = 1.0):
    """Continuously prints sensor readings to console."""
    print(f"--- Continuous Read (Interval: {interval_sec}s) - Ctrl+C to stop ---")
    try:
        while True:
            start_time = time.time()
            data = get_measurements_fast(ser, device_address)
            
            if data:
                ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                print(f"  > [{ts}] COND: {data['conductivity']:.2f} uS | TEMP: {data['temperature_celsius']:.1f} C | LVL: {data['liquid_level_mm']:.1f} mm  ", end='\r\n')
            else:
                print("  > No device response...                          ", end='\r')
                
            elapsed = time.time() - start_time
            time.sleep(max(0, interval_sec - elapsed))
    except KeyboardInterrupt:
        print("\nStopped.")

def log_data_to_csv(ser: serial.Serial, filename: str, device_address: int = 1, interval_sec: float = 1.0):
    """Logs sensor readings to a CSV file."""
    file_exists = os.path.isfile(filename)
    print(f"--- Logging to '{filename}' (Interval: {interval_sec}s) - Ctrl+C to stop ---")

    try:
        with open(filename, mode='a', newline='') as csvfile:
            fieldnames = ['Timestamp', 'Conductivity (uS/cm)', 'Temperature (C)', 'Liquid Level (mm)']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()

            while True:
                start_time = time.time()
                data = get_measurements_fast(ser, device_address)

                if data:
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    writer.writerow({
                        'Timestamp': ts,
                        'Conductivity (uS/cm)': data['conductivity'],
                        'Temperature (C)': data['temperature_celsius'],
                        'Liquid Level (mm)': data['liquid_level_mm']
                    })
                    csvfile.flush()
                    print(f"  > [{ts}] Saved: {data['conductivity']:.2f} uS | {data['liquid_level_mm']:.1f} mm")
                
                time.sleep(max(0, interval_sec - (time.time() - start_time)))

    except KeyboardInterrupt:
        print(f"\nStopped. Data saved to {filename}.")


# --- Main Execution / Interactive Block ---
if __name__ == "__main__":
    
    # 1. Initialize Serial
    try:
        ser = serial.Serial(
            port=SERIAL_PORT,
            baudrate=BAUDRATE,
            parity=PARITY,
            stopbits=STOPBITS,
            bytesize=BYTESIZE,
            timeout=TIMEOUT
        )
        if ser.is_open:
            print(f"Connected to {SERIAL_PORT} at {BAUDRATE} baud.")
    except serial.SerialException as e:
        print(f"Error connecting to {SERIAL_PORT}: {e}")
        ser = None

    # Note: The blocks below are set up for Spyder/VSCode Interactive execution
    # Uncomment the function calls to run them.

#%% 
if ser:
    # --- Example: Data Logging ---
    log_data_to_csv(ser, filename="sensor_log.csv", device_address=DEFAULT_ADDRESS, interval_sec=1.0)

#%%
if ser:
    # --- Example: Continuous Read to Console ---
    start_continuous_read_loop(ser, DEFAULT_ADDRESS, interval_sec=0.5)

#%%
# ==========================================
# CALIBRATION COMMANDS (Use with Caution)
# ==========================================

# 1. LEVEL ZERO (Air)
# start_continuous_read_loop(ser, DEFAULT_ADDRESS, interval_sec=0.1)
# calibrate_level_zero(ser, DEFAULT_ADDRESS)

# 2. LEVEL SLOPE (Known Depth)
# start_continuous_read_loop(ser, DEFAULT_ADDRESS, interval_sec=0.1)
# calibrate_level_slope(ser, known_level_mm=1000, device_address=DEFAULT_ADDRESS)

# 3. CONDUCTIVITY ZERO (Air)
# start_continuous_read_loop(ser, DEFAULT_ADDRESS, interval_sec=0.1)
# calibrate_cond_zero(ser, DEFAULT_ADDRESS, multi_point_mode=False)

# 4. CONDUCTIVITY SLOPE (Standard Solution)
# start_continuous_read_loop(ser, DEFAULT_ADDRESS, interval_sec=0.1)
# calibrate_cond_single_point_slope(ser, standard_value_us=1413, device_address=DEFAULT_ADDRESS)