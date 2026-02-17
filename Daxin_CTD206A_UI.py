#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Clean CTD-206A UI with live plotting, modbus logging, and CSV export.
"""

import sys
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import serial
import serial.tools.list_ports
import threading
import time
import csv
from datetime import datetime
from collections import deque
from queue import Queue

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import Daxin_CTD206A_functions as ctd

BAUDRATE = 9600
TIMEOUT = 1.0


class CTDApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CTD-206A Control")
        self.geometry("700x700")
        self.resizable(True, True)
        
        self.ser = None
        self.is_reading = False
        self.is_logging = False
        self.read_thread = None
        self.data_queue = Queue()
        
        self.data = deque()
        self.modbus_log = deque(maxlen=1000)
        self.csv_file = None
        self.csv_writer = None
        self.sample_period = 0.5
        self.plot_window_sec = 60
        self.log_queue = Queue()
        
        # Dynamic scaling for axes
        self.cond_scale_levels = [120, 1000, 10000, 30000, 60000, 120000]
        self.cond_scale_idx = 0
        self.level_scale_levels = [100, 1000, 5000, 10000]
        self.level_scale_idx = 0
        self.temp_scale_levels = [2, 5, 10, 20, 40]
        self.temp_scale_idx = 2  # Start with 10°C range
        
        # Conductivity unit toggle
        self.cond_unit = "µS/cm"
        self.cond_unit_options = ["µS/cm", "dS/cm"]
        self.cond_unit_var = tk.BooleanVar(value=False)  # False=µS/cm, True=dS/cm
        
        self.connection_dependent_buttons = []
        self.calibration_buttons = []
        self.plot_visible = True
        
        self._build_ui()
        self.after(100, self.process_queue)
        self.after(1000, self._refresh_ports)
        self._setup_terminal_mirror()

    def _build_ui(self):
        """Build clean, minimal UI."""
        # Top: Connection
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=5, pady=5, side=tk.TOP)
        
        ports = self._get_serial_ports()
        self.port_combo = ttk.Combobox(top, values=ports, width=15, state="readonly")
        if ports:
            self.port_combo.current(0)
        self.port_combo.pack(side=tk.LEFT, padx=2)
        
        self.connect_btn = ttk.Button(top, text="Connect", command=self.toggle_connection)
        self.connect_btn.pack(side=tk.LEFT, padx=2)
        
        self.status_lbl = ttk.Label(top, text="Disconnected", foreground="red")
        self.status_lbl.pack(side=tk.LEFT, padx=5)
        
        # Readouts - centered with modern fonts
        readouts = ttk.Frame(self)
        readouts.pack(fill=tk.X, padx=5, pady=10, side=tk.TOP)
        
        # Center container for readouts
        readouts_center = ttk.Frame(readouts)
        readouts_center.pack(anchor=tk.CENTER)
        
        # Conductivity
        cond_frame = ttk.Frame(readouts_center)
        cond_frame.pack(side=tk.LEFT, padx=15)
        ttk.Label(cond_frame, text="Conductivity", font=("Helvetica Neue", 10)).pack()
        self.cond_lbl = ttk.Label(cond_frame, text="--", font=("Helvetica Neue", 18, "bold"), foreground="#00d4ff")
        self.cond_lbl.pack()
        self.cond_unit_lbl = ttk.Label(cond_frame, text=self.cond_unit, font=("Helvetica Neue", 9))
        self.cond_unit_lbl.pack()
        
        # Temperature
        temp_frame = ttk.Frame(readouts_center)
        temp_frame.pack(side=tk.LEFT, padx=15)
        ttk.Label(temp_frame, text="Temperature", font=("Helvetica Neue", 10)).pack()
        self.temp_lbl = ttk.Label(temp_frame, text="--", font=("Helvetica Neue", 18, "bold"), foreground="#ff9f1c")
        self.temp_lbl.pack()
        self.temp_unit_lbl = ttk.Label(temp_frame, text="°C", font=("Helvetica Neue", 9))
        self.temp_unit_lbl.pack()
        
        # Level
        level_frame = ttk.Frame(readouts_center)
        level_frame.pack(side=tk.LEFT, padx=15)
        ttk.Label(level_frame, text="Liquid Level", font=("Helvetica Neue", 10)).pack()
        self.level_lbl = ttk.Label(level_frame, text="--", font=("Helvetica Neue", 18, "bold"), foreground="#2ecc71")
        self.level_lbl.pack()
        self.level_unit_lbl = ttk.Label(level_frame, text="mm", font=("Helvetica Neue", 9))
        self.level_unit_lbl.pack()
        
        # View status
        view_frame = ttk.Frame(self)
        view_frame.pack(fill=tk.X, padx=5, pady=2, side=tk.TOP)
        
        self.log_status = ttk.Label(view_frame, text="", foreground="gray")
        self.log_status.pack(side=tk.LEFT, padx=10)
        
        # Controls - Two rows with dynamic centering (like calibration)
        ctrl = ttk.Frame(self)
        ctrl.pack(fill=tk.BOTH, padx=5, pady=2, side=tk.TOP)
        
        # Row 1: Start, Stop, Clear (centered wrapper)
        ctrl_row1_wrapper = ttk.Frame(ctrl)
        ctrl_row1_wrapper.pack(fill=tk.X, expand=True)
        
        ctrl_row1 = ttk.Frame(ctrl_row1_wrapper)
        ctrl_row1.pack(anchor=tk.CENTER)
        
        ttk.Label(ctrl_row1, text="Read:").pack(side=tk.LEFT, padx=2)
        
        self.start_btn = ttk.Button(ctrl_row1, text="Start", command=self.start_read, state="disabled")
        self.start_btn.pack(side=tk.LEFT, padx=1)
        self.connection_dependent_buttons.append(self.start_btn)
        
        self.stop_btn = ttk.Button(ctrl_row1, text="Stop", command=self.stop_read, state="disabled")
        self.stop_btn.pack(side=tk.LEFT, padx=1)
        self.connection_dependent_buttons.append(self.stop_btn)
        
        self.clear_btn = ttk.Button(ctrl_row1, text="Clear", command=self.clear_plot, state="disabled")
        self.clear_btn.pack(side=tk.LEFT, padx=1)
        self.connection_dependent_buttons.append(self.clear_btn)
        
        ttk.Separator(ctrl_row1, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=3)
        
        # Row 2: Sample, Window, dS/cm, Log CSV, Stop Log (centered wrapper)
        ctrl_row2_wrapper = ttk.Frame(ctrl)
        ctrl_row2_wrapper.pack(fill=tk.X, expand=True)
        
        ctrl_row2 = ttk.Frame(ctrl_row2_wrapper)
        ctrl_row2.pack(anchor=tk.CENTER)
        
        ttk.Label(ctrl_row2, text="Sample:").pack(side=tk.LEFT, padx=2)
        self.sample_ent = ttk.Entry(ctrl_row2, width=4)
        self.sample_ent.insert(0, "0.5")
        self.sample_ent.pack(side=tk.LEFT, padx=2)
        
        ttk.Label(ctrl_row2, text="Window:").pack(side=tk.LEFT, padx=2)
        self.window_ent = ttk.Entry(ctrl_row2, width=4)
        self.window_ent.insert(0, "60")
        self.window_ent.pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(ctrl_row2, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=3)
        
        self.cond_unit_chk = ttk.Checkbutton(ctrl_row2, text="dS/cm", variable=self.cond_unit_var, command=self._update_cond_unit)
        self.cond_unit_chk.pack(side=tk.LEFT, padx=5)
        
        ttk.Separator(ctrl_row2, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=3)
        
        self.log_start_btn = ttk.Button(ctrl_row2, text="Log CSV", command=self.start_logging, state="disabled")
        self.log_start_btn.pack(side=tk.LEFT, padx=1)
        self.connection_dependent_buttons.append(self.log_start_btn)
        
        self.log_stop_btn = ttk.Button(ctrl_row2, text="Stop Log", command=self.stop_logging, state="disabled")
        self.log_stop_btn.pack(side=tk.LEFT, padx=1)
        self.connection_dependent_buttons.append(self.log_stop_btn)
        
        # Separator between controls and calibration
        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=5, pady=5, side=tk.TOP)
        
        # Calibration - Two rows with dynamic centering
        cal = ttk.Frame(self)
        cal.pack(fill=tk.BOTH, padx=5, pady=2, side=tk.TOP)
        
        # Row 1: Conductivity calibration (centered wrapper)
        cal_row1_wrapper = ttk.Frame(cal)
        cal_row1_wrapper.pack(fill=tk.X, expand=True)
        
        cal_row1 = ttk.Frame(cal_row1_wrapper)
        cal_row1.pack(anchor=tk.CENTER)
        
        ttk.Label(cal_row1, text="Calibration:").pack(side=tk.LEFT, padx=2)
        
        self.cond_z_btn = ttk.Button(cal_row1, text="Cond Zero", command=self.cal_cond_zero, state="disabled")
        self.cond_z_btn.pack(side=tk.LEFT, padx=1)
        self.connection_dependent_buttons.append(self.cond_z_btn)
        self.calibration_buttons.append(self.cond_z_btn)
        
        self.cond_s_btn = ttk.Button(cal_row1, text="Cond Slope", command=self.cal_cond_slope, state="disabled")
        self.cond_s_btn.pack(side=tk.LEFT, padx=1)
        self.connection_dependent_buttons.append(self.cond_s_btn)
        self.calibration_buttons.append(self.cond_s_btn)
        
        self.cond_m_btn = ttk.Button(cal_row1, text="Cond Multi", command=self.cal_cond_multi, state="disabled")
        self.cond_m_btn.pack(side=tk.LEFT, padx=1)
        self.connection_dependent_buttons.append(self.cond_m_btn)
        self.calibration_buttons.append(self.cond_m_btn)
        
        ttk.Separator(cal_row1, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=3)
        
        # Row 2: Level, Temperature and Mode (centered wrapper)
        cal_row2_wrapper = ttk.Frame(cal)
        cal_row2_wrapper.pack(fill=tk.X, expand=True)
        
        cal_row2 = ttk.Frame(cal_row2_wrapper)
        cal_row2.pack(anchor=tk.CENTER)
        
        ttk.Label(cal_row2, text=" " * 14).pack(side=tk.LEFT, padx=2)
        
        self.level_z_btn = ttk.Button(cal_row2, text="Level Zero", command=self.cal_level_zero, state="disabled")
        self.level_z_btn.pack(side=tk.LEFT, padx=1)
        self.connection_dependent_buttons.append(self.level_z_btn)
        self.calibration_buttons.append(self.level_z_btn)
        
        self.level_s_btn = ttk.Button(cal_row2, text="Level Slope", command=self.cal_level_slope, state="disabled")
        self.level_s_btn.pack(side=tk.LEFT, padx=1)
        self.connection_dependent_buttons.append(self.level_s_btn)
        self.calibration_buttons.append(self.level_s_btn)
        
        ttk.Separator(cal_row2, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=3)
        
        self.temp_offset_btn = ttk.Button(cal_row2, text="Temp Offset", command=self.cal_temp_offset, state="disabled")
        self.temp_offset_btn.pack(side=tk.LEFT, padx=1)
        self.connection_dependent_buttons.append(self.temp_offset_btn)
        self.calibration_buttons.append(self.temp_offset_btn)
        
        ttk.Separator(cal_row2, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=3)
        
        self.mode_btn = ttk.Button(cal_row2, text="Set Mode", command=self.set_mode, state="disabled")
        self.mode_btn.pack(side=tk.LEFT, padx=1)
        self.connection_dependent_buttons.append(self.mode_btn)
        self.calibration_buttons.append(self.mode_btn)
        
        # Display area (PACKED LAST with expand=True so it takes remaining space)
        self.display_area = ttk.Frame(self)
        self.display_area.pack(fill=tk.BOTH, expand=True, padx=5, pady=5, side=tk.TOP)
        
        # View tabs
        self.view_tabs = ttk.Notebook(self.display_area)
        self.view_tabs.pack(fill=tk.BOTH, expand=True)
        self.view_tabs.bind("<<NotebookTabChanged>>", self._on_view_tab_change)

        # Plot area
        self.plot_container = ttk.LabelFrame(self.view_tabs, text="Live Data")
        self.plot_container.pack_propagate(False)
        
        fig = Figure(figsize=(10, 4), dpi=100, facecolor="#2b2b2b")
        fig.subplots_adjust(left=0.15, right=0.75, top=0.95, bottom=0.12)
        self.ax = fig.add_subplot(111)
        self.ax_t = self.ax.twinx()
        self.ax_d = self.ax.twinx()
        self.ax_d.spines["right"].set_position(("axes", 1.20))
        
        # Dark mode styling
        for ax in [self.ax, self.ax_t, self.ax_d]:
            ax.set_facecolor("#1e1e1e")
            ax.tick_params(colors="white", labelsize=8)
            ax.spines["bottom"].set_color("white")
            ax.spines["left"].set_color("white")
            ax.spines["right"].set_color("white")
            for spine in ax.spines.values():
                spine.set_edgecolor("white")
        
        self.line_c, = self.ax.plot([], [], color="#00d4ff", linewidth=2, label="Cond")
        self.line_t, = self.ax_t.plot([], [], color="#ff9f1c", linewidth=2, label="Temp")
        self.line_d, = self.ax_d.plot([], [], color="#2ecc71", linewidth=2, label="Level")
        
        self.ax.set_ylim(0, 120000)
        self.ax_t.set_ylim(-5, 40)
        self.ax_d.set_ylim(0, 10000)
        self.ax.set_xlabel("Time (s)", fontsize=9, color="white")
        self.ax.set_ylabel("Cond (µS)", color="#00d4ff", fontsize=9)
        self.ax_t.set_ylabel("Temp (°C)", color="#ff9f1c", fontsize=9)
        self.ax_d.set_ylabel("Level (mm)", color="#2ecc71", fontsize=9)
        
        self.ax.tick_params(axis="y", colors="#00d4ff")
        self.ax_t.tick_params(axis="y", colors="#ff9f1c")
        self.ax_d.tick_params(axis="y", colors="#2ecc71")
        self.ax.tick_params(axis="x", colors="white")
        
        self.canvas = FigureCanvasTkAgg(fig, master=self.plot_container)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Modbus log
        self.log_container = ttk.LabelFrame(self.view_tabs, text="Modbus Log")
        self.log_container.pack_propagate(False)
        
        self.log_text = tk.Text(self.log_container, height=20, bg="#1a1a1a", fg="#00ff00", 
                               font=("Courier", 8), highlightthickness=0)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.config(state="disabled")
        
        self.log_text.tag_config("send", foreground="#00ff00")
        self.log_text.tag_config("recv", foreground="#ffff00")
        self.log_text.tag_config("err", foreground="#ff0000")
        self.log_text.tag_config("parsed", foreground="#00d4ff")
        
        # Add tabs
        self.view_tabs.add(self.plot_container, text="Plot")
        self.view_tabs.add(self.log_container, text="Modbus Log")
        
    def _update_calibration_buttons(self):
        self._stdout_original = sys.stdout
        self._stderr_original = sys.stderr
        sys.stdout = _TerminalTee(self._enqueue_terminal_line, self._stdout_original, "TERM")
        sys.stderr = _TerminalTee(self._enqueue_terminal_line, self._stderr_original, "ERR")

    def _enqueue_terminal_line(self, tag, line):
        if line is None:
            return
        self.log_queue.put((tag, line))

    def _update_calibration_buttons(self):
        enabled = bool(self.ser and self.ser.is_open and not self.is_reading and not self.is_logging)
        state = "normal" if enabled else "disabled"
        for btn in self.calibration_buttons:
            btn.config(state=state)
    
    def _update_start_stop_buttons(self):
        """Update start/stop button states based on reading state."""
        if self.is_reading:
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")
        else:
            self.start_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
    
    def _get_serial_ports(self):
        """Get list of available serial ports."""
        ports = []
        for port in serial.tools.list_ports.comports():
            ports.append(port.device)
        return ports
    
    def _setup_terminal_mirror(self):
        """Set up terminal output mirroring to the UI."""
        self._stdout_original = sys.stdout
        self._stderr_original = sys.stderr
        sys.stdout = _TerminalTee(self._enqueue_terminal_line, self._stdout_original, "TERM")
        sys.stderr = _TerminalTee(self._enqueue_terminal_line, self._stderr_original, "ERR")
    
    def _refresh_ports(self):
        """Refresh the list of available COM ports every 1 second."""
        current_ports = self._get_serial_ports()
        combo_ports = list(self.port_combo['values'])
        
        # Update if the list has changed
        if current_ports != combo_ports:
            current_selection = self.port_combo.get()
            self.port_combo['values'] = current_ports
            
            # If current selection is no longer available, handle it
            if current_selection not in current_ports:
                if current_ports:
                    self.port_combo.current(0)
                else:
                    self.port_combo.set("")  # Clear selection when no ports available
        
        # Schedule the next refresh
        self.after(1000, self._refresh_ports)
    
    def show_plot(self):
        self.view_tabs.select(self.plot_container)
        self.plot_visible = True
    
    def show_log(self):
        self.view_tabs.select(self.log_container)
        self.plot_visible = False
        self.update_log()

    def _update_cond_unit(self):
        """Update conductivity unit display based on checkbox state"""
        self.cond_unit = self.cond_unit_options[1] if self.cond_unit_var.get() else self.cond_unit_options[0]
        self.cond_unit_lbl.config(text=self.cond_unit)
        # Update plot axis label
        self.ax.set_ylabel(f"Cond ({self.cond_unit})", color="#00d4ff", fontsize=9)
        self.canvas.draw_idle()
    
    def _update_axis_scales(self):
        """Dynamically adjust plot axis scales based on current data maximum values."""
        if not self.data:
            return
        
        # Get max values from current data
        max_cond = max([v['conductivity'] for _, v in self.data]) if self.data else 0
        max_level = max([v['liquid_level_mm'] for _, v in self.data]) if self.data else 0
        temps = [v['temperature_celsius'] for _, v in self.data] if self.data else []
        avg_temp = sum(temps) / len(temps) if temps else 25
        temp_range = max(temps) - min(temps) if temps and max(temps) > min(temps) else 0
        
        # Update conductivity scale - only scale UP, never down
        current_cond_limit = self.cond_scale_levels[self.cond_scale_idx]
        if max_cond > current_cond_limit and self.cond_scale_idx < len(self.cond_scale_levels) - 1:
            self.cond_scale_idx += 1
        self.ax.set_ylim(0, self.cond_scale_levels[self.cond_scale_idx])
        
        # Update level scale - only scale UP, never down
        current_level_limit = self.level_scale_levels[self.level_scale_idx]
        if max_level > current_level_limit and self.level_scale_idx < len(self.level_scale_levels) - 1:
            self.level_scale_idx += 1
        self.ax_d.set_ylim(0, self.level_scale_levels[self.level_scale_idx])
        
        # Update temperature scale dynamically - zoom in on actual range
        half_range = self.temp_scale_levels[self.temp_scale_idx] / 2
        # Scale up if data range exceeds current scale AND we have a wider tier available
        if temp_range > self.temp_scale_levels[self.temp_scale_idx] and self.temp_scale_idx < len(self.temp_scale_levels) - 1:
            self.temp_scale_idx += 1
            half_range = self.temp_scale_levels[self.temp_scale_idx] / 2
        # Center the view around the average temperature
        temp_min = avg_temp - half_range
        temp_max = avg_temp + half_range
        self.ax_t.set_ylim(temp_min, temp_max)

    def _on_view_tab_change(self, _event):
        selected = self.view_tabs.select()
        if selected == str(self.log_container):
            self.plot_visible = False
            self.update_log()
        else:
            self.plot_visible = True
    
    def add_log(self, tag, msg):
        ts = time.strftime("%H:%M:%S")
        self.log_queue.put((tag, f"[{ts}] {msg}"))

    def _log_text_tag(self, tag, msg):
        if tag == "SEND":
            return "send"
        if tag == "PARSED":
            return "parsed"
        if tag in ("ERR", "ERROR") or "Error" in msg:
            return "err"
        return "recv"

    def _append_log_line(self, tag, msg):
        self.log_text.config(state="normal")
        ttag = self._log_text_tag(tag, msg)
        self.log_text.insert("end", msg + "\n", ttag)
        if not self.plot_visible:
            self.log_text.see("end")
        self.log_text.config(state="disabled")
    
    def update_log(self):
        if not self.plot_visible:
            self.log_text.config(state="normal")
            self.log_text.delete("1.0", "end")
            for tag, msg in self.modbus_log:
                ttag = self._log_text_tag(tag, msg)
                self.log_text.insert("end", msg + "\n", ttag)
            self.log_text.see("end")
            self.log_text.config(state="disabled")
    
    def toggle_connection(self):
        if self.ser and self.ser.is_open:
            self.is_reading = False
            if self.read_thread:
                self.read_thread.join(timeout=2)
            self.ser.close()
            self.clear_plot()
            self.status_lbl.config(text="Disconnected", foreground="red")
            self.connect_btn.config(text="Connect")
            for btn in self.connection_dependent_buttons:
                btn.config(state="disabled")
            self._update_start_stop_buttons()
        else:
            port = self.port_combo.get()
            if not port:
                messagebox.showerror("Error", "Select a port")
                return
            try:
                self.ser = serial.Serial(port, BAUDRATE, timeout=TIMEOUT)
                self.clear_plot()
                self.status_lbl.config(text=f"Connected: {port}", foreground="green")
                self.connect_btn.config(text="Disconnect")
                for btn in self.connection_dependent_buttons:
                    btn.config(state="normal")
                self.add_log("INFO", f"Connected to {port}")
                self._update_calibration_buttons()
                self._update_start_stop_buttons()
            except Exception as e:
                messagebox.showerror("Error", f"Failed: {e}")
    
    def start_read(self):
        try:
            self.sample_period = float(self.sample_ent.get())
            self.plot_window_sec = float(self.window_ent.get())
        except:
            messagebox.showerror("Error", "Invalid values")
            return
        self.is_reading = True
        self._update_start_stop_buttons()
        self._update_calibration_buttons()
        self.read_thread = threading.Thread(target=self.read_loop, daemon=True)
        self.read_thread.start()
    
    def stop_read(self):
        self.is_reading = False
        self._update_start_stop_buttons()
        self._update_calibration_buttons()
    
    def read_loop(self):
        while self.is_reading:
            if self.ser and self.ser.is_open:
                data = ctd.get_measurements_fast(self.ser, log_callback=self.add_log)
                if data:
                    self.data_queue.put(data)
            time.sleep(self.sample_period)
    
    def process_queue(self):
        try:
            while not self.data_queue.empty():
                data = self.data_queue.get_nowait()
                now = time.time()
                self.data.append((now, data))
                
                # Trim old data
                cutoff = now - self.plot_window_sec
                while self.data and self.data[0][0] < cutoff:
                    self.data.popleft()
                
                # Update labels
                self.cond_lbl.config(text=f"{data['conductivity']:.1f}")
                self.temp_lbl.config(text=f"{data['temperature_celsius']:.1f}")
                self.level_lbl.config(text=f"{data['liquid_level_mm']:.1f}")

                self.add_log(
                    "PARSED",
                    (
                        "Parsed: "
                        f"Cond={data['conductivity']:.1f} µS, "
                        f"Temp={data['temperature_celsius']:.1f} °C, "
                        f"Level={data['liquid_level_mm']:.1f} mm"
                    )
                )
                
                # Log CSV
                if self.is_logging and self.csv_writer:
                    self.csv_writer.writerow([
                        datetime.now().isoformat(),
                        data['conductivity'],
                        data['temperature_celsius'],
                        data['liquid_level_mm']
                    ])
                
                # Update plot
                if self.plot_visible:
                    self.update_plot()

            while not self.log_queue.empty():
                tag, msg = self.log_queue.get_nowait()
                self.modbus_log.append((tag, msg))
                self._append_log_line(tag, msg)
        finally:
            self.after(100, self.process_queue)
    
    def update_plot(self):
        if not self.data:
            return
        t0 = self.data[0][0]
        x = [t - t0 for t, _ in self.data]
        c = [v['conductivity'] for _, v in self.data]
        tm = [v['temperature_celsius'] for _, v in self.data]
        d = [v['liquid_level_mm'] for _, v in self.data]
        
        self.line_c.set_data(x, c)
        self.line_t.set_data(x, tm)
        self.line_d.set_data(x, d)
        
        # Update axis scales dynamically based on data
        self._update_axis_scales()
        
        if x:
            self.ax.set_xlim(0, max(x) * 1.05)
        self.canvas.draw_idle()
    
    def clear_plot(self):
        self.data.clear()
        self.line_c.set_data([], [])
        self.line_t.set_data([], [])
        self.line_d.set_data([], [])
        self.canvas.draw_idle()
    
    def start_logging(self):
        fn = filedialog.asksaveasfilename(defaultextension=".csv")
        if not fn:
            return
        try:
            self.csv_file = open(fn, 'w', newline='')
            self.csv_writer = csv.writer(self.csv_file)
            self.csv_writer.writerow(['Timestamp', 'Conductivity', 'Temperature', 'Level'])
            self.is_logging = True
            self.log_status.config(text=f"Logging to {fn.split('/')[-1]}", foreground="green")
            self.add_log("INFO", f"Started logging")
            self._update_calibration_buttons()
        except Exception as e:
            messagebox.showerror("Error", str(e))
    
    def stop_logging(self):
        if self.csv_file:
            self.is_logging = False
            self.csv_file.close()
            self.log_status.config(text="", foreground="gray")
            self.add_log("INFO", "Stopped logging")
            self._update_calibration_buttons()
    
    def cal_cond_zero(self):
        if not self.ser:
            return
        if messagebox.askokcancel("Confirm", "Sensor in air, dry?"):
            success, msg = ctd.calibrate_cond_zero(self.ser)
            self.add_log("CAL", f"Cond Zero: {msg}")
            messagebox.showinfo("Result", msg)
    
    def cal_cond_slope(self):
        if not self.ser:
            return
        val = simpledialog.askinteger("Input", "Standard (µS):")
        if val:
            if messagebox.askokcancel("Confirm", f"Sensor in {val} µS solution?"):
                success, msg = ctd.calibrate_cond_single_point_slope(self.ser, val)
                self.add_log("CAL", f"Cond Slope {val}: {msg}")
                messagebox.showinfo("Result", msg)
    
    def cal_cond_multi(self):
        if not self.ser:
            return
        pt = simpledialog.askinteger("Point", "1-5:")
        if pt:
            val = simpledialog.askinteger("Value", f"Standard for point {pt} (µS):")
            if val:
                if messagebox.askokcancel("Confirm", f"Sensor in {val} µS solution?"):
                    success, msg = ctd.calibrate_cond_multi_point_slope(self.ser, pt, val)
                    self.add_log("CAL", f"Cond Multi {pt},{val}: {msg}")
                    messagebox.showinfo("Result", msg)
    
    def cal_level_zero(self):
        if not self.ser:
            return
        if messagebox.askokcancel("Confirm", "Sensor in air?"):
            success, msg = ctd.calibrate_level_zero(self.ser)
            self.add_log("CAL", f"Level Zero: {msg}")
            messagebox.showinfo("Result", msg)
    
    def cal_level_slope(self):
        if not self.ser:
            return
        val = simpledialog.askinteger("Input", "Known depth (mm):")
        if val:
            if messagebox.askokcancel("Confirm", f"Sensor at {val} mm?"):
                success, msg = ctd.calibrate_level_slope(self.ser, val)
                self.add_log("CAL", f"Level Slope {val}: {msg}")
                messagebox.showinfo("Result", msg)
    
    def cal_temp_offset(self):
        if not self.ser:
            return
        offset = simpledialog.askinteger("Input", "Offset (0.1°C units):\n(E.g., 10 = +1.0°C, -5 = -0.5°C):")
        if offset is not None:
            if messagebox.askokcancel("Confirm", f"Set temperature offset to {offset} (0.1°C units)?"):
                success, msg = ctd.calibrate_temperature_offset(self.ser, offset)
                self.add_log("CAL", f"Temp Offset {offset}: {msg}")
                messagebox.showinfo("Result", msg)
    
    def set_mode(self):
        if not self.ser:
            return
        mode = simpledialog.askinteger("Mode", "0=µS, 1=mS, 2=ppm, 3=ppt (0-3):")
        if mode is not None:
            success, msg = ctd.set_conductivity_mode(self.ser, mode)
            self.add_log("CONFIG", f"Mode {mode}: {msg}")
            messagebox.showinfo("Result", msg)
    
    def on_closing(self):
        self.is_reading = False
        if self.read_thread:
            self.read_thread.join(timeout=2)
        if self.csv_file:
            self.csv_file.close()
        if self.ser and self.ser.is_open:
            self.ser.close()
        sys.stdout = self._stdout_original
        sys.stderr = self._stderr_original
        self.destroy()


class _TerminalTee:
    def __init__(self, enqueue, stream, tag):
        self.enqueue = enqueue
        self.stream = stream
        self.tag = tag
        self._buffer = ""

    def write(self, message):
        if self.stream:
            self.stream.write(message)
        if not message:
            return
        self._buffer += message
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self.enqueue(self.tag, line)

    def flush(self):
        if self.stream:
            self.stream.flush()


if __name__ == "__main__":
    app = CTDApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()

