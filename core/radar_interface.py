"""
Radar Interface
Abstract base class for radar control and data acquisition
THIS IS WHERE THE RADAR SDK WILL BE INTEGRATED

To integrate a radar SDK:
1. Create a new class RadarSDKInterface(RadarInterface)
2. Implement all abstract methods using SDK calls
3. Replace MockRadarInterface with RadarSDKInterface in main_window.py
"""

import logging
from abc import ABCMeta, abstractmethod
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
import numpy as np
import random
import math

logger = logging.getLogger(__name__)


class _ABCQObjectMeta(ABCMeta, type(QObject)):
    """Combined metaclass for ABC + QObject."""
    pass


class RadarInterface(QObject, metaclass=_ABCQObjectMeta):
    """
    Abstract base class for radar interface

    SDK INTEGRATION POINT:
    Subclass this and implement all @abstractmethod functions
    using your radar SDK C/C++ library calls via ctypes
    """
    
    # Signal emitted when new radar data is available
    radar_data_updated = pyqtSignal(dict)

    # Signal emitted when the transmit state changes (True = transmitting, False = standby)
    # SDK INTEGRATION: emit this from your SDK callback when the radar confirms state change
    transmit_state_changed = pyqtSignal(bool)
    
    def __init__(self):
        super().__init__()
        
    @abstractmethod
    def start(self):
        """
        Start radar operation
        
        SDK Integration:
        - Initialize SDK
        - Connect to radar via Ethernet
        - Start data acquisition
        """
        pass
        
    @abstractmethod
    def stop(self):
        """
        Stop radar operation
        
        SDK Integration:
        - Stop data acquisition
        - Disconnect from radar
        - Cleanup SDK resources
        """
        pass
        
    @abstractmethod
    def set_range(self, range_nm):
        """
        Set radar range in nautical miles
        
        SDK Integration:
        - Call SDK function to set range
        - Example: radar_sdk.set_range(range_nm)
        """
        pass
        
    @abstractmethod
    def set_gain(self, gain_percent):
        """
        Set radar gain (0-100%)
        
        SDK Integration:
        - Call SDK function to set gain
        - Example: radar_sdk.set_gain(gain_percent)
        """
        pass
        
    @abstractmethod
    def set_video_mode(self, mode):
        """
        Set video mode: 'raw' or 'processed'

        SDK Integration:
        - Call SDK function to set video mode
        - Example: radar_sdk.set_video_mode(0=raw, 1=processed)
        """
        pass

    @abstractmethod
    def set_sea_clutter(self, value):
        """
        Set sea clutter rejection (0-100%)

        SDK Integration:
        - Call SDK function to set STC (Sensitivity Time Control)
        - Example: radar_sdk.set_sea_clutter(value)
        """
        pass

    @abstractmethod
    def set_rain_clutter(self, value):
        """
        Set rain clutter rejection / FTC (0-100%)

        SDK Integration:
        - Call SDK function to set FTC (Fast Time Constant)
        - Example: radar_sdk.set_rain_clutter(value)
        """
        pass

    @abstractmethod
    def set_transmit(self, transmitting: bool):
        """
        Command the radar to transmit or stand by.

        SDK INTEGRATION:
        - transmitting=True  → send the 'Transmit' command to the radar
        - transmitting=False → send the 'Standby' command to the radar
        - After the radar confirms the state change, emit transmit_state_changed(transmitting)
          so the GUI toggle stays in sync with the actual hardware state.

        Example (adjust to your SDK):
            if transmitting:
                self.sdk.radar_set_transmit()      # radar starts rotating & transmitting
            else:
                self.sdk.radar_set_standby()       # radar stops transmitting (motor may keep spinning)
            # Confirmation callback will call: self.transmit_state_changed.emit(transmitting)
        """
        pass

    @abstractmethod
    def get_radar_data(self):
        """
        Get current radar data
        
        SDK Integration:
        - Call SDK function to get radar video data
        - Return dict with:
          {
              'video': [{'azimuth': angle, 'range': meters, 'intensity': 0-1}, ...],
              'targets': [{'lat': lat, 'lon': lon, 'course': deg, 'speed': kts}, ...],
              'sweep_angle': current_sweep_position_degrees
          }
        """
        pass


class MockRadarInterface(RadarInterface):
    """
    Mock radar interface for testing
    
    REMOVE THIS AND USE RadarSDKInterface WHEN SDK IS INTEGRATED
    
    This generates simulated radar data for development/testing
    """
    
    def __init__(self):
        super().__init__()
        self.running = False
        self.timer = QTimer()
        self.timer.timeout.connect(self._generate_data)

        # Radar settings
        self.range_nm = 12.0
        self.gain = 50
        self.sea_clutter = 0
        self.rain_clutter = 0
        self.video_mode = 'processed'
        self.transmitting = False
        
        # Simulated targets
        self.sim_targets = [
            {'lat': 37.001, 'lon': -76.301, 'course': 45, 'speed': 12},
            {'lat': 37.005, 'lon': -76.299, 'course': 180, 'speed': 8},
            {'lat': 36.999, 'lon': -76.305, 'course': 270, 'speed': 15},
        ]
        
        self.sweep_angle = 0
        
    def start(self):
        """Start mock radar"""
        logger.info("Mock Radar: Starting")
        self.running = True
        self.timer.start(100)  # 10 Hz update
        
    def stop(self):
        """Stop mock radar"""
        logger.info("Mock Radar: Stopping")
        self.running = False
        self.timer.stop()
        
    def set_range(self, range_nm):
        """Set radar range"""
        logger.info("Mock Radar: Set range to %s NM", range_nm)
        self.range_nm = range_nm
        
    def set_gain(self, gain_percent):
        """Set radar gain"""
        logger.info("Mock Radar: Set gain to %s%%", gain_percent)
        self.gain = gain_percent
        
    def set_video_mode(self, mode):
        """Set video mode"""
        logger.info("Mock Radar: Set video mode to %s", mode)
        self.video_mode = mode

    def set_sea_clutter(self, value):
        """Set sea clutter rejection"""
        self.sea_clutter = value

    def set_rain_clutter(self, value):
        """Set rain clutter rejection"""
        self.rain_clutter = value

    def set_transmit(self, transmitting: bool):
        """Mock standby/transmit — logs state change and emits confirmation signal."""
        self.transmitting = transmitting
        state = "TRANSMIT" if transmitting else "STANDBY"
        logger.info("Mock Radar: %s", state)
        # Simulate immediate hardware confirmation
        # SDK INTEGRATION: remove this line; instead emit from your SDK callback
        self.transmit_state_changed.emit(transmitting)
        
    def get_radar_data(self):
        """Get simulated radar data"""
        return self._generate_radar_data()
        
    def _generate_data(self):
        """Timer callback to generate and emit data"""
        data = self._generate_radar_data()
        self.radar_data_updated.emit(data)
        
    def _generate_radar_data(self):
        """Generate simulated radar data"""
        # Update sweep angle
        self.sweep_angle = (self.sweep_angle + 3) % 360
        
        # Generate video returns
        video_returns = []
        
        if self.video_mode == 'raw':
            # Generate more noise for raw mode
            num_returns = 500
        else:
            # Fewer, cleaner returns for processed mode
            num_returns = 200
            
        for _ in range(num_returns):
            azimuth = random.uniform(0, 360)
            range_m = random.uniform(0, self.range_nm * 1852)  # Convert NM to meters
            
            # Higher intensity near targets
            intensity = random.uniform(0.1, 0.3)
            
            # Check if near a target
            for target in self.sim_targets:
                target_azimuth = self._get_bearing(37.0, -76.3, 
                                                   target['lat'], target['lon'])
                target_range = self._get_distance(37.0, -76.3,
                                                 target['lat'], target['lon']) * 1852
                
                azimuth_diff = abs(azimuth - target_azimuth)
                if azimuth_diff > 180:
                    azimuth_diff = 360 - azimuth_diff
                    
                if azimuth_diff < 5 and abs(range_m - target_range) < 500:
                    intensity = random.uniform(0.7, 1.0)
                    
            video_returns.append({
                'azimuth': azimuth,
                'range': range_m,
                'intensity': intensity
            })
            
        # Generate target list (processed mode)
        targets = []
        for sim_target in self.sim_targets:
            # Add some jitter
            targets.append({
                'lat': sim_target['lat'] + random.uniform(-0.0001, 0.0001),
                'lon': sim_target['lon'] + random.uniform(-0.0001, 0.0001),
                'course': sim_target['course'] + random.uniform(-2, 2),
                'speed': sim_target['speed'] + random.uniform(-0.5, 0.5)
            })
            
        return {
            'video': video_returns,
            'targets': targets,
            'sweep_angle': self.sweep_angle
        }
        
    def _get_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance in nautical miles"""
        R = 3440.065
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(dlon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c
        
    def _get_bearing(self, lat1, lon1, lat2, lon2):
        """Calculate bearing in degrees"""
        dlon = math.radians(lon2 - lon1)
        lat1 = math.radians(lat1)
        lat2 = math.radians(lat2)
        
        y = math.sin(dlon) * math.cos(lat2)
        x = (math.cos(lat1) * math.sin(lat2) -
             math.sin(lat1) * math.cos(lat2) * math.cos(dlon))
        
        bearing = math.degrees(math.atan2(y, x))
        return (bearing + 360) % 360


# =============================================================================
# RADAR SDK INTEGRATION TEMPLATE
# =============================================================================
"""
Example of how to integrate a radar SDK:

import ctypes

class RadarSDKInterface(RadarInterface):
    def __init__(self, dll_path):
        super().__init__()

        # Load radar SDK DLL
        self.sdk = ctypes.CDLL(dll_path)

        # Define function signatures
        # Example (adjust to match your actual SDK):
        self.sdk.radar_init.argtypes = []
        self.sdk.radar_init.restype = ctypes.c_int

        self.sdk.radar_connect.argtypes = [ctypes.c_char_p, ctypes.c_int]
        self.sdk.radar_connect.restype = ctypes.c_int

        self.sdk.radar_set_range.argtypes = [ctypes.c_float]
        self.sdk.radar_set_range.restype = ctypes.c_int

        # Add more function definitions...

    def start(self):
        # Initialize SDK
        result = self.sdk.radar_init()
        if result != 0:
            raise Exception(f"Failed to initialize SDK: {result}")

        # Connect to radar
        ip = b"192.168.1.100"  # Radar IP address
        port = 10001  # Radar port
        result = self.sdk.radar_connect(ip, port)
        if result != 0:
            raise Exception(f"Failed to connect to radar: {result}")

        # Start acquisition
        self.timer = QTimer()
        self.timer.timeout.connect(self._fetch_radar_data)
        self.timer.start(100)  # 10 Hz

    def stop(self):
        self.timer.stop()
        self.sdk.radar_disconnect()
        self.sdk.radar_cleanup()

    def set_range(self, range_nm):
        self.sdk.radar_set_range(ctypes.c_float(range_nm))

    def set_gain(self, gain_percent):
        self.sdk.radar_set_gain(ctypes.c_int(gain_percent))

    def set_video_mode(self, mode):
        mode_code = 0 if mode == 'raw' else 1
        self.sdk.radar_set_video_mode(ctypes.c_int(mode_code))
        
    def get_radar_data(self):
        # Call SDK to get data
        # Parse and return in expected format
        pass
        
    def _fetch_radar_data(self):
        data = self.get_radar_data()
        self.radar_data_updated.emit(data)
"""
