/**
 * TTN V3 Payload Decoder for a CTD-206A Sensor connected via a Dragino RS485-LS node.
 *
 * This is a comprehensive decoder that handles multiple uplink types based on the FPort:
 * - FPort 2: Handles the main data uplink.
 * - If length is 17 bytes: Decodes the wrapped CTD-206A sensor reading.
 * - Otherwise: Decodes a standard Dragino status message (battery/trigger).
 * - FPort 5: Decodes device configuration and firmware information.
 * 
 * Measurement modes:
 *   Mode 0:
 *     - Conductivity reported in µS/cm
 *   Mode 1:
 *     - Conductivity reported in mS/cm
 *     - Values are converted to µS/cm in this decoder to maintain consistency
 *   Mode 12:
 *     - Native units are preserved and exposed as conductivity_mS_cm
 *
 * To avoid ambiguity and improve reproducibility, unit conversions are handled
 * explicitly using a switch-case structure in the Sensor Data Parsing section,
 * and decoded variable names encode their physical units.
 */

measurement_mode = 1;

 /**
 * @param {Object} input - An object containing the payload bytes and fPort.
 * @returns {Object} - An object with the decoded data or errors.
 */
 
 /**
 * Calculates the Modbus CRC-16.
 * @param {Array<number>} buffer - An array of bytes.
 * @returns {number} - The 16-bit CRC value.
 */

 
function modbusCRC(buffer) {
  var crc = 0xFFFF;
  for (var pos = 0; pos < buffer.length; pos++) {
    crc ^= buffer[pos];
    for (var i = 8; i !== 0; i--) {
      if ((crc & 0x0001) !== 0) {
        crc >>= 1;
        crc ^= 0xA001;
      } else {
        crc >>= 1;
      }
    }
  }
  return crc;
}

function decodeUplink(input) {
    var bytes = input.bytes;
    var fPort = input.fPort;
    var decoded = {};

    if (fPort === 2) {
        // This is the main data port. Check length to determine message type.
        if (bytes.length === 17) {
            // This is the 17-byte wrapped sensor data payload
            decoded.BatV = ((bytes[0] << 8 | bytes[1]) & 0x7FFF) / 1000;
            
           // --- Modbus CRC Check ---
            // 1. Reconstruct the Modbus data part: 0x01030C + 12 sensor bytes [bytes 3-14]
            var sensor_bytes_for_crc = bytes.slice(3, 15);
            var modbus_data_part = [0x01, 0x03, 0x0C].concat(Array.from(sensor_bytes_for_crc));
      
            // 2. Calculate the expected CRC
            var calculated_crc = modbusCRC(modbus_data_part);
      
            // 3. Extract the received CRC (bytes 15 and 16, low-byte first)
            var received_crc = (bytes[16] << 8) | bytes[15];
      
            // 4. Add the CRC check variable to the output
            if (calculated_crc === received_crc) {
              decoded.modbus_crc_check = "PASS";
            } else {
              decoded.modbus_crc_check = "FAIL";
              decoded.modbus_crc_calculated_hex = '0x' + calculated_crc.toString(16).toUpperCase().padStart(4, '0');
              decoded.modbus_crc_received_hex = '0x' + received_crc.toString(16).toUpperCase().padStart(4, '0');
            }
            // --- END Modbus CRC Check ---

            var sensor_data_bytes = bytes.slice(3, 15);
            var registers = [];
            for (var i = 0; i < sensor_data_bytes.length; i += 2) {
                registers.push((sensor_data_bytes[i] << 8) | sensor_data_bytes[i + 1]);
            }
            
            // --- Sensor Data Parsing ---

                        // Conductivity is treated as an unsigned value.
            var conductivity_raw = registers[0];
            var conductivity_decimals = registers[1];


            switch (measurement_mode) {

            case 0:
                // Mode 0: conductivity reported in µS/cm (default)
                decoded.conductivity_uS_cm =
                conductivity_raw / Math.pow(10, conductivity_decimals);
                break;

            case 1:
                // Mode 1: conductivity reported in mS/cm → convert to µS/cm
                decoded.conductivity_uS_cm =
                (conductivity_raw * 1000) / Math.pow(10, conductivity_decimals);
                break;

            case 12:
                // Mode 2: preserve native mS/cm output
                decoded.conductivity_mS_cm =
                conductivity_raw / Math.pow(10, conductivity_decimals);
                break;

            default:
                // Unknown / unsupported measurement mode
                decoded.conductivity_error = "Unsupported measurement mode";
                break;
            }
            
            // Temperature logic
            var temp_c_raw = registers[2];
            var temp_c_decimals = registers[3];
            if (temp_c_raw & 0x8000) { temp_c_raw -= 0x10000; } // Keep sign check for temp
            decoded.temperature_celsius = temp_c_raw / Math.pow(10, temp_c_decimals);

            decoded.temperature_fahrenheit = (decoded.temperature_celsius * 9 / 5) + 32;

            // Liquid level logic
            var liquid_level_raw = registers[4];
            var liquid_level_decimals = registers[5];
            if (liquid_level_raw & 0x8000) { liquid_level_raw -= 0x10000; } // Keep sign check for level
            decoded.liquid_level_mm = liquid_level_raw / Math.pow(10, liquid_level_decimals);

        } else {
            // Standard Dragino status message
            decoded.EXTI_Trigger = (bytes[0] & 0x80) ? "TRUE" : "FALSE";
            decoded.BatV = ((bytes[0] << 8 | bytes[1]) & 0x7FFF) / 1000;
            decoded.Payver = bytes[2];
            decoded.Node_type = "RS485-BL";
        }
    } else if (fPort === 5) {
        // Configuration port
        var freq_band;
        if (bytes[0] === 0x01) freq_band = "EU868";
        else if (bytes[0] === 0x02) freq_band = "US915";
        else if (bytes[0] === 0x03) freq_band = "IN865";
        else if (bytes[0] === 0x04) freq_band = "AU915";
        else if (bytes[0] === 0x05) freq_band = "KZ865";
        else if (bytes[0] === 0x06) freq_band = "RU864";
        else if (bytes[0] === 0x07) freq_band = "AS923";
        else if (bytes[0] === 0x08) freq_band = "AS923_1";
        else if (bytes[0] === 0x09) freq_band = "AS923_2";
        else if (bytes[0] === 0x0A) freq_band = "AS923_3";
        else if (bytes[0] === 0x0F) freq_band = "AS923_4";
        else if (bytes[0] === 0x0B) freq_band = "CN470";
        else if (bytes[0] === 0x0C) freq_band = "EU433";
        else if (bytes[0] === 0x0D) freq_band = "KR920";
        else if (bytes[0] === 0x0E) freq_band = "MA869";

        var sub_band = (bytes[1] === 0xff) ? "NULL" : bytes[1];
        
        decoded.FIRMWARE_VERSION = (bytes[2] & 0x0f) + '.' + (bytes[3] >> 4 & 0x0f) + '.' + (bytes[3] & 0x0f);
        decoded.FREQUENCY_BAND = freq_band;
        decoded.SUB_BAND = sub_band;
        decoded.TDC_sec = bytes[4] << 16 | bytes[5] << 8 | bytes[6];
    } else {
        return {
            errors: ["Unknown FPort: " + fPort]
        };
    }

    return {
        data: decoded
    };
}

/**
 * Fallback decoder for TTN V2.
 */
function Decoder(bytes, fPort) {
    var decoded = decodeUplink({ bytes: bytes, fPort: fPort });
    return decoded.data || {};
}
