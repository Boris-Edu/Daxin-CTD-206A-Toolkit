{\rtf1\ansi\ansicpg1252\cocoartf2867
\cocoatextscaling0\cocoaplatform0{\fonttbl\f0\fswiss\fcharset0 Helvetica;}
{\colortbl;\red255\green255\blue255;}
{\*\expandedcolortbl;;}
\margl1440\margr1440\vieww11520\viewh8400\viewkind0
\pard\tx720\tx1440\tx2160\tx2880\tx3600\tx4320\tx5040\tx5760\tx6480\tx7200\tx7920\tx8640\pardirnatural\partightenfactor0

\f0\fs24 \cf0 # CTD-206A Sensor Toolkit\
\
Python utilities for reading, logging, and calibrating the CTD-206A Conductivity, Temperature, and Depth sensor via Modbus RTU.\
\
## Files\
\
1.  **`ctd_control.py`**: \
    * Reads live data from the sensor.\
    * Logs data to CSV.\
    * Performs single-point and multi-point calibration.\
2.  **`visualize_response.py`**:\
    * Visualizes response time and steady-state values from generated CSV logs.\
\
## Setup\
\
1. Install dependencies:\
   ```bash\
   pip install -r requirements.txt}