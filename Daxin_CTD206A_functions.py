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

def calibrate_temperature_offset(ser: serial.Serial, offset_value: int, device_address: int = 1):
    """
    Performs a TEMPERATURE OFFSET calibration.
    Adjusts the temperature reading by the given offset (in 0.1°C units).
    Physical Step: Place sensor in known temperature environment.
    
    Args:
        offset_value: Offset value in 0.1°C units. 
                     E.g., 10 = +1.0°C, -5 = -0.5°C
    """
    print(f"Starting Temperature OFFSET Calibration to {offset_value} (0.1°C units)...")
    return _send_calibration_frame(ser, device_address, 0x1038, offset_value)

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
    """
    Parses the raw 12-byte payload into engineering units.
    Now also returns the raw 'decimal shift' values for debugging.
    """
    # --- Conductivity (Bytes 0-1: Value, Bytes 2-3: Decimal Places) ---
    cond_val = int.from_bytes(data_payload[0:2], 'big', signed=False)
    cond_dec = int.from_bytes(data_payload[2:4], 'big', signed=False)
    
    # Apply decoding: Value / 10^(Decimal Places)
    conductivity = cond_val / (10**cond_dec) if cond_dec > 0 else float(cond_val)

    # --- Temperature (Bytes 4-5: Value, Bytes 6-7: Decimal Places) ---
    temp_val = int.from_bytes(data_payload[4:6], 'big', signed=True)
    temp_dec = int.from_bytes(data_payload[6:8], 'big', signed=False)
    
    # Apply decoding
    temp_c = temp_val / (10**temp_dec) if temp_dec > 0 else float(temp_val)
    temp_f = temp_c * 9/5 + 32

    # --- Liquid Level (Bytes 8-9: Value, Bytes 10-11: Decimal Places) ---
    level_val = int.from_bytes(data_payload[8:10], 'big', signed=False)
    level_dec = int.from_bytes(data_payload[10:12], 'big', signed=False)
    
    # Apply decoding
    level_mm = level_val / (10**level_dec) if level_dec > 0 else float(level_val)

    return {
        'conductivity': conductivity,
        'cond_raw_val': cond_val,      # Raw Integer (0-65535)
        'cond_decimal_shift': cond_dec,# Decimal Places (e.g., 0, 1, 2, 3)
        
        'temperature_celsius': temp_c,
        'temp_raw_val': temp_val,
        'temp_decimal_shift': temp_dec,
        
        'liquid_level_mm': level_mm,
        'level_raw_val': level_val,
        'level_decimal_shift': level_dec
    }

def get_measurements_fast(
    ser: serial.Serial,
    device_address: int = 1,
    log_callback=None
) -> dict | None:
    """Reads measurements quietly (optimized for loops). Returns None on error."""
    frame = bytearray()
    frame.append(device_address)
    frame.append(0x03)
    frame.extend([0x00, 0x00, 0x00, 0x06]) # Start 0, Len 6
    frame.extend(calculate_crc(frame).to_bytes(2, 'little'))

    try:
        ser.flushInput()
        ser.write(frame)
        if log_callback:
            log_callback("SEND", f"TX: {frame.hex(' ')}")
        time.sleep(0.2)
        response = ser.read(ser.in_waiting)
        if log_callback:
            log_callback("RECV", f"RX: {response.hex(' ')}")
        is_valid, payload = _validate_read_response(frame, response)
        return _parse_measurement_data(payload) if is_valid else None
    except Exception:
        return None

def start_continuous_read_loop(ser: serial.Serial, device_address: int = 1, interval_sec: float = 1.0):
    """
    Continuously prints sensor readings to console with extended debug info.
    """
    print(f"--- Continuous Read (Interval: {interval_sec}s) - Ctrl+C to stop ---")
    print(f"{'TIME':<12} | {'COND (uS/mS)':<12} | {'RAW':<6} {'DEC':<3} | {'TEMP (C)':<10} | {'LEVEL (mm)':<10}")
    print("-" * 80)
    
    try:
        while True:
            start_time = time.time()
            data = get_measurements_fast(ser, device_address)
            
            if data:
                ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                
                # Format the output to show the calculated value AND the raw decoding components
                print(f"{ts:<12} | "
                      f"{data['conductivity']:<12.3f} | "
                      f"{data['cond_raw_val']:<6} "
                      f"{data['cond_decimal_shift']:<3} | "
                      f"{data['temperature_celsius']:<10.1f} | "
                      f"{data['liquid_level_mm']:<10.1f}", 
                      end='\r')
            else:
                print(f"{'No response...':<75}", end='\r')
                
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
        plot_sensor_response('sensor_log.csv')


def set_conductivity_mode(ser: serial.Serial, mode: int, device_address: int = 1):
    """
    Switches the conductivity measurement unit.
    Register: 0x8009
    
    Modes:
    0: Conductivity (uS/cm) - Default. Max ~65.5 mS/cm.
    1: Conductivity (mS/cm) - Use this if value > 65 mS/cm.
    2: TDS (ppm)
    3: Salinity (ppt)
    """
    valid_modes = {
        0: "uS/cm",
        1: "mS/cm",
        2: "ppm",
        3: "ppt"
    }
    
    if mode not in valid_modes:
        print(f"Error: Invalid mode {mode}. Options: 0=uS, 1=mS, 2=ppm, 3=ppt")
        return False, "Invalid Mode"

    print(f"--- Switching Conductivity Mode to {mode} ({valid_modes[mode]}) ---")
    
    # Send command to Register 0x8009
    return _send_calibration_frame(ser, device_address, 0x8009, mode)

def plot_sensor_response(filename: str):
    """
    Reads sensor log data, splits it into trials based on time gaps,
    normalizes the data, and plots the response curves.
    """
    # 1. Load Data
    try:
        df = pd.read_csv(filename)
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found. Please run the logging script first.")
        return

    # Cleanup headers
    df.columns = df.columns.str.strip()
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])

    # 2. Separate Trials
    # Logic: If the time difference between rows is > 5 seconds, assume a new trial started.
    df['dt'] = df['Timestamp'].diff().dt.total_seconds()
    split_indices = df[df['dt'] > 5].index.tolist()
    starts = [0] + split_indices
    ends = split_indices + [len(df)]
    
    trials = []
    cols = ['Conductivity (uS/cm)', 'Temperature (C)', 'Liquid Level (mm)']
    steady_vals_accumulator = {c: [] for c in cols}

    for s, e in zip(starts, ends):
        sub = df.iloc[s:e].copy()
        if len(sub) < 10: continue  # Skip short snippets
        
        # Find start of activity (first non-zero value)
        is_active = sub[cols].ne(0).any(axis=1)
        if not is_active.any(): continue 
        start_idx = is_active.idxmax()
        sub = sub.loc[start_idx:].copy()
        
        # Normalize to steady state (average of last 5 points)
        sub_norm = sub.copy()
        for col in cols:
            val = sub[col].iloc[-5:].mean()
            if pd.isna(val) or val == 0: val = 1
            sub_norm[col] = sub[col] / val
            steady_vals_accumulator[col].append(val)
            
        sub_norm['Time'] = (sub['Timestamp'] - sub['Timestamp'].iloc[0]).dt.total_seconds()
        trials.append(sub_norm.set_index('Time')[cols])

    if not trials:
        print("No valid trials found in the data.")
        return

    # 3. Average Trials
    common_time = np.linspace(0, 15, 150)
    avg_df = pd.DataFrame(index=common_time)
    for col in cols:
        interp_vals = []
        for t in trials:
            valid_t = t[~t.index.duplicated()]
            val = np.interp(common_time, valid_t.index, valid_t[col], left=np.nan, right=np.nan)
            interp_vals.append(val)
        avg_df[col] = np.nanmean(interp_vals, axis=0)

    # 4. Plot Setup
    fig, ax_main = plt.subplots(figsize=(10, 6))
    
    # Reserve space on the right for the extra axes
    plt.subplots_adjust(right=0.75) 

    colors = {'Conductivity (uS/cm)': 'blue', 'Temperature (C)': 'red', 'Liquid Level (mm)': 'green'}
    labels = {'Conductivity (uS/cm)': 'Conductivity', 'Temperature (C)': 'Temperature', 'Liquid Level (mm)': 'Depth'}
    
    # Plot Normalized Curves
    for col in cols:
        ax_main.plot(avg_df.index, avg_df[col], color=colors[col], label=labels[col], linewidth=2)

    ax_main.set_xlim(0, 12)
    ax_main.set_ylim(0, 1.1)
    ax_main.set_xlabel("Time (seconds)")
    ax_main.set_ylabel("Normalized Response")
    ax_main.set_title("Sensor Response Time")
    ax_main.legend(loc='lower right')
    ax_main.grid(True, linestyle='--', alpha=0.5)
    ax_main.axhline(1.0, color='k', linestyle=':', alpha=0.5)

    # 5. Configure Twin Axes for Real Scales
    avg_steady_vals = {k: np.mean(v) for k, v in steady_vals_accumulator.items()}
    
    # (Axis Object, Column Name, Label, Color, Position Offset)
    scales = [
        (ax_main.twinx(), 'Temperature (C)', 'Temperature (°C)', 'red', 1.0),
        (ax_main.twinx(), 'Conductivity (uS/cm)', 'Conductivity (uS/cm)', 'blue', 1.15),
        (ax_main.twinx(), 'Liquid Level (mm)', 'Depth (mm)', 'green', 1.3)
    ]

    for ax, col, label, color, pos in scales:
        ss_val = avg_steady_vals[col]
        ax.spines["right"].set_position(("axes", pos))
        ax.set_frame_on(True)
        ax.patch.set_visible(False)
        ax.set_ylim(0, 1.1 * ss_val)
        ax.set_ylabel(label, color=color)
        ax.tick_params(axis='y', labelcolor=color)

    output_file = 'sensor_response_plot.png'
    plt.savefig(output_file, bbox_inches='tight', dpi=300)
    print(f"Success: Plot saved to {output_file}")
    plt.show()


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
        
#%%
# ==========================================
# MANUAL CALIBRATION COMMANDS (Use with Caution)
# ==========================================

# # --- Configuration ---
# # UPDATE THIS PORT BEFORE RUNNING
# SERIAL_PORT = 'COM11'  # Windows: 'COMx', Linux: '/dev/ttyUSBx'

# # Sensor Settings
# BAUDRATE = 9600
# PARITY = serial.PARITY_NONE
# STOPBITS = serial.STOPBITS_ONE
# BYTESIZE = serial.EIGHTBITS
# TIMEOUT = 1
# DEFAULT_ADDRESS = 1



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

# # --- Example: Data Logging ---
# log_data_to_csv(ser, filename="sensor_log.csv", device_address=DEFAULT_ADDRESS, interval_sec=0.0)

# # --- Example: Continuous Read to Console ---
# start_continuous_read_loop(ser, DEFAULT_ADDRESS, interval_sec=0.1)

# # --- Example: Continuous Read to Console ---
# # This function writes to register 0x8009.
# # You can use this to switch from uS/cm (Mode 0) to mS/cm (Mode 1) if your readings are overflowing (65535).
# set_conductivity_mode(ser, mode=1, device_address = 1)

