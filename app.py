import serial
import time
import sys
import threading
from flask import Flask, render_template, jsonify
from datetime import datetime

# Initialize Flask App34
app = Flask(__name__)

class GPSDevice:
    def __init__(self, port='/dev/serial0', baud=9600, timeout=1):
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.serial_conn = None
        self.current_data = {
            'timestamp': None,
            'latitude': None,
            'longitude': None,
            'altitude': 0.0,
            'satellites': 0,
            'speed_kmh': 0.0,
            'fix_quality': 0,  # 0=Invalid, 1=GPS, 2=DGPS
            'last_updated': None
        }

    def connect(self):
        """Establishes connection to the Serial Port."""
        try:
            self.serial_conn = serial.Serial(self.port, self.baud, timeout=self.timeout)
            print(f"[Success] Connected to GPS on {self.port}")
            return True
        except serial.SerialException as e:
            print(f"[Error] Could not connect to serial port: {e}")
            return False

    def _nmea_to_decimal(self, value, direction):
        """
        Converts NMEA DDMM.MMMM format to Decimal Degrees (DD.DDDD).
        """
        if not value or value == '':
            return None
        
        try:
            # Locate decimal point to split Degrees and Minutes
            # NMEA format: DDDMM.MMMM
            if '.' in value:
                decimal_pos = value.find('.')
                # Minutes start 2 digits before the decimal
                split_idx = decimal_pos - 2
                
                degrees = float(value[:split_idx])
                minutes = float(value[split_idx:])
            else:
                return None

            decimal_degrees = degrees + (minutes / 60)

            # Southern and Western coordinates are negative
            if direction in ['S', 'W']:
                decimal_degrees = -decimal_degrees

            return decimal_degrees
        except ValueError:
            return None

    def update(self):
        """Reads serial buffer and updates internal state."""
        if not self.serial_conn:
            return

        try:
            if self.serial_conn.in_waiting > 0:
                # Read line and decode
                line = self.serial_conn.readline().decode('utf-8', errors='ignore').strip()
                
                # Debug: Print raw data to console
                print(f"Raw GPS Data: {line}")
                
                if line.startswith('$GPGGA'):
                    self._parse_gpgga(line)
                elif line.startswith('$GPRMC'):
                    self._parse_gprmc(line)
                    
        except OSError:
            print("Serial IO Error. Reconnecting...")
            try:
                self.serial_conn.close()
            except:
                pass
            time.sleep(1)
            self.connect()
        except Exception as e:
            # print(f"Error parsing line: {e}") # Optional debugging
            pass

    def _parse_gpgga(self, line):
        """Parses Global Positioning System Fix Data."""
        parts = line.split(',')
        if len(parts) < 10: 
            return

        # parts[6] is Fix Quality
        # DEBUG MODE: Commented out validation to see data even without a fix
        # if parts[6] == '0':
        #     self.current_data['fix_quality'] = 0
        #     return
        
        try:
            self.current_data['fix_quality'] = int(parts[6])
            self.current_data['satellites'] = int(parts[7])
            self.current_data['altitude'] = float(parts[9]) if parts[9] else 0.0
            
            # Parse Coords if we haven't got them from RMC yet or just to update
            lat = self._nmea_to_decimal(parts[2], parts[3])
            lon = self._nmea_to_decimal(parts[4], parts[5])
            
            if lat and lon:
                self.current_data['latitude'] = lat
                self.current_data['longitude'] = lon
                self.current_data['last_updated'] = time.time()
                
        except ValueError:
            pass

    def _parse_gprmc(self, line):
        """Parses Recommended Minimum Specific GPS/Transit Data."""
        parts = line.split(',')
        if len(parts) < 10:
            return

        # parts[2] is Status: A=Active, V=Void
        # DEBUG MODE: Commented out validation to see data even without a fix
        # if parts[2] != 'A':
        #     return

        try:
            # Parse Coords
            lat = self._nmea_to_decimal(parts[3], parts[4])
            lon = self._nmea_to_decimal(parts[5], parts[6])
            
            if lat and lon:
                self.current_data['latitude'] = lat
                self.current_data['longitude'] = lon

            # Speed (Knots to Km/h)
            knots = float(parts[7]) if parts[7] else 0.0
            self.current_data['speed_kmh'] = knots * 1.852

            # Date/Time Parsing
            # Time: HHMMSS.SS, Date: DDMMYY
            time_str = parts[1]
            date_str = parts[9]
            
            if len(time_str) >= 6 and len(date_str) == 6:
                # Format: YYYY-MM-DD HH:MM:SS
                dt_format = f"20{date_str[4:6]}-{date_str[2:4]}-{date_str[0:2]} {time_str[0:2]}:{time_str[2:4]}:{time_str[4:6]}"
                self.current_data['timestamp'] = dt_format

            self.current_data['last_updated'] = time.time()

        except ValueError:
            pass

    def get_data(self):
        """Returns the current data dictionary."""
        return self.current_data

# --- Flask Routes ---
@app.route('/')
def index():
    # Looks for index.html in the 'templates' folder
    return render_template('index.html')

@app.route('/data')
def get_gps_data():
    return jsonify(gps.get_data())

def start_background_loop(gps_instance):
    """Function to run in a separate thread to keep reading GPS data."""
    while True:
        gps_instance.update()
        # Small sleep to prevent CPU hogging, but fast enough for serial
        time.sleep(0.1)

# --- Main Execution ---
if __name__ == "__main__":
    # --- CONFIGURATION ---
    # Linux/Raspberry Pi: '/dev/serial0' or '/dev/ttyUSB0'
    # Windows: 'COM3', 'COM4', etc.
    SERIAL_PORT = '/dev/serial0' 
    BAUD_RATE = 9600
    
    gps = GPSDevice(port=SERIAL_PORT, baud=BAUD_RATE)
    
    print("--- GPS DASHBOARD SERVER ---")
    
    # Attempt connection
    if gps.connect():
        # 1. Start GPS reading in a background thread
        print("Starting GPS background thread...")
        gps_thread = threading.Thread(target=start_background_loop, args=(gps,), daemon=True)
        gps_thread.start()
        
        # 2. Start Flask Web Server
        print("Starting Web Server...")
        print("View the dashboard at: http://localhost:5000")
        
        # debug=False is important when using threads to avoid reloader issues
        # host='0.0.0.0' allows access from other devices on the network
        app.run(host='0.0.0.0', port=5000, debug=False)
    else:
        print("Failed to initialize GPS. Please check connections and port permissions.")