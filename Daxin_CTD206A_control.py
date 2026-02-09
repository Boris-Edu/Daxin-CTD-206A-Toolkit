#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CTD-206A Graphical Control & Calibration Interface
Implements full MODBUS command set per manufacturer manual
"""

import serial
import serial.tools.list_ports
import struct
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

# ============================================================
# CONFIGURATION
# ============================================================

BAUDRATE = 9600
TIMEOUT = 1.0
DEVICE_ADDR = 1

ser = None
reading = False

# ============================================================
# MODBUS CRC
# ============================================================

def modbus_crc(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF

# ============================================================
# MODBUS PRIMITIVES
# ============================================================

def write_register(register, value) -> bool:
    global ser
    try:
        frame = struct.pack(">B B H H", DEVICE_ADDR, 0x06, register, value & 0xFFFF)
        frame += struct.pack("<H", modbus_crc(frame))
        ser.write(frame)
        resp = ser.read(8)
        return resp == frame
    except Exception:
        return False


def read_measurements():
    global ser
    try:
        frame = struct.pack(">B B H H", DEVICE_ADDR, 0x03, 0x0000, 6)
        frame += struct.pack("<H", modbus_crc(frame))
        ser.write(frame)
        resp = ser.read(17)
        if len(resp) < 17:
            return None

        data = resp[3:-2]
        r = struct.unpack(">6H", data)

        cond = r[0] / (10 ** r[1])
        temp = struct.unpack(">h", struct.pack(">H", r[2]))[0] / (10 ** r[3])
        depth = r[4] / (10 ** r[5])

        return cond, temp, depth
    except Exception:
        return None

# ============================================================
# SERIAL HANDLING
# ============================================================

def connect_serial():
    global ser
    ports = list(serial.tools.list_ports.comports())

    if not ports:
        messagebox.showerror("Error", "No serial ports found")
        return

    if len(ports) == 1:
        port = ports[0].device
    else:
        port = simpledialog.askstring(
            "Select Port",
            "Available ports:\n" + "\n".join(p.device for p in ports)
        )
        if not port:
            return

    try:
        ser = serial.Serial(port, BAUDRATE, timeout=TIMEOUT)
        status_var.set(f"Connected to {port}")
    except Exception as e:
        messagebox.showerror("Connection failed", str(e))

# ============================================================
# LIVE READING THREAD
# ============================================================

def start_reading():
    global reading
    reading = True

    def loop():
        while reading:
            data = read_measurements()
            if data:
                cond, temp, depth = data
                meas_var.set(
                    f"Cond: {cond:.2f} | Temp: {temp:.2f} °C | Depth: {depth:.1f} mm"
                )
            else:
                meas_var.set("⚠ No data / disconnected")
            time.sleep(0.5)

    threading.Thread(target=loop, daemon=True).start()


def stop_reading():
    global reading
    reading = False
    meas_var.set("Stopped")

# ============================================================
# CALIBRATION ACTIONS
# ============================================================

def confirm(text):
    return messagebox.askyesno("Confirm", text)


def cond_zero():
    if confirm("Conductivity ZERO calibration.\nSensor must be DRY in AIR.\nContinue?"):
        ok = write_register(0x1000, 0)
        messagebox.showinfo("Result", "Success" if ok else "Failed")


def cond_single_slope():
    val = simpledialog.askinteger("Standard", "Conductivity standard (uS/cm):")
    if val is None:
        return
    if confirm(f"Place sensor in {val} uS/cm solution.\nProceed?"):
        ok = write_register(0x1004, val)
        messagebox.showinfo("Result", "Success" if ok else "Failed")


def cond_multi_point():
    regs = {1:0x1054,2:0x1058,3:0x105C,4:0x1060,5:0x1064}

    choice = messagebox.askquestion(
        "Multi-point",
        "Yes = full sequence (1→5)\nNo = single point"
    )

    if choice == "no":
        p = simpledialog.askinteger("Point", "Select point (1–5):")
        if p not in regs:
            return
        val = simpledialog.askinteger("Standard", "Conductivity (uS/cm):")
        if val is None:
            return
        if confirm(f"Point {p}: {val} uS/cm\nProceed?"):
            ok = write_register(regs[p], val)
            messagebox.showinfo("Result", "Success" if ok else "Failed")

    else:
        if not confirm("You will calibrate points 1→5 in ascending order.\nContinue?"):
            return
        for p in range(1,6):
            val = simpledialog.askinteger("Standard", f"Point {p} value (uS/cm):")
            if val is None:
                return
            if not confirm(f"Point {p}: {val} uS/cm\nProceed?"):
                return
            if not write_register(regs[p], val):
                messagebox.showerror("Error", f"Failed at point {p}")
                return
        messagebox.showinfo("Done", "Multi-point calibration complete")


def depth_zero():
    if confirm("Depth ZERO calibration.\nSensor in AIR.\nContinue?"):
        ok = write_register(0x1030, 0)
        messagebox.showinfo("Result", "Success" if ok else "Failed")


def depth_slope():
    val = simpledialog.askinteger("Depth", "Known depth (mm):")
    if val is None:
        return
    if confirm(f"Known depth = {val} mm\nProceed?"):
        ok = write_register(0x1034, val)
        messagebox.showinfo("Result", "Success" if ok else "Failed")


def temp_offset():
    temp = simpledialog.askfloat("Temperature", "Actual temperature (°C):")
    if temp is None:
        return
    reg_val = int(temp * 10)
    if confirm(f"Actual temperature = {temp:.1f} °C\nProceed?"):
        ok = write_register(0x1010, reg_val)
        messagebox.showinfo("Result", "Success" if ok else "Failed")


def set_cond_mode():
    mode = simpledialog.askinteger(
        "Mode",
        "0 = uS/cm\n1 = mS/cm\n2 = TDS (ppm)\n3 = Salinity (ppt)"
    )
    if mode is None:
        return
    ok = write_register(0x8009, mode)
    messagebox.showinfo("Result", "Success" if ok else "Failed")

# ============================================================
# GUI
# ============================================================

root = tk.Tk()
root.title("CTD-206A Control & Calibration")

frame = ttk.Frame(root, padding=10)
frame.grid()

ttk.Button(frame, text="Connect", command=connect_serial).grid(row=0, column=0, sticky="ew")
ttk.Button(frame, text="Start Read", command=start_reading).grid(row=0, column=1, sticky="ew")
ttk.Button(frame, text="Stop Read", command=stop_reading).grid(row=0, column=2, sticky="ew")

ttk.Separator(frame).grid(row=1, columnspan=3, sticky="ew", pady=5)

ttk.Button(frame, text="Cond ZERO", command=cond_zero).grid(row=2, column=0, sticky="ew")
ttk.Button(frame, text="Cond Slope", command=cond_single_slope).grid(row=2, column=1, sticky="ew")
ttk.Button(frame, text="Cond Multi-Point", command=cond_multi_point).grid(row=2, column=2, sticky="ew")

ttk.Button(frame, text="Depth ZERO", command=depth_zero).grid(row=3, column=0, sticky="ew")
ttk.Button(frame, text="Depth Slope", command=depth_slope).grid(row=3, column=1, sticky="ew")
ttk.Button(frame, text="Temp Offset", command=temp_offset).grid(row=3, column=2, sticky="ew")

ttk.Button(frame, text="Set Cond Mode", command=set_cond_mode).grid(row=4, column=1, sticky="ew")

status_var = tk.StringVar(value="Disconnected")
meas_var = tk.StringVar(value="No data")

ttk.Label(frame, textvariable=status_var).grid(row=5, columnspan=3, pady=5)
ttk.Label(frame, textvariable=meas_var, font=("Courier", 11)).grid(row=6, columnspan=3, pady=5)

root.mainloop()
