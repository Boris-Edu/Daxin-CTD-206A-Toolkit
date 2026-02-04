#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

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

if __name__ == "__main__":
    # Change this filename to match your data source
    plot_sensor_response('sensor_log.csv')
