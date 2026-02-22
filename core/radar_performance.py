"""
Radar Performance Analyzer
Monitor radar RF performance, detect interference, analyze SNR
Leveraging RF engineering expertise for radar diagnostics
"""

import numpy as np
from collections import deque
import math


class RadarPerformanceAnalyzer:
    """Analyze radar RF performance"""
    
    def __init__(self, history_size=100):
        """
        Initialize analyzer
        
        Args:
            history_size: Number of samples to keep for analysis
        """
        self.history_size = history_size
        
        # History buffers
        self.noise_floor_history = deque(maxlen=history_size)
        self.snr_history = deque(maxlen=history_size)
        self.return_count_history = deque(maxlen=history_size)
        
        # Interference detection
        self.interference_detected = False
        self.interference_pattern = None
        
        # Performance thresholds
        self.noise_floor_threshold = 0.15  # Above this indicates high noise
        self.min_snr_db = 10.0  # Minimum acceptable SNR
        
    def analyze_radar_video(self, radar_returns):
        """
        Analyze radar video data
        
        Args:
            radar_returns: List of radar returns with intensity values
            
        Returns:
            dict with performance metrics
        """
        if not radar_returns:
            return None
            
        intensities = np.array([r['intensity'] for r in radar_returns])
        
        # Calculate noise floor
        noise_floor = self._calculate_noise_floor(intensities)
        self.noise_floor_history.append(noise_floor)
        
        # Detect targets (strong returns)
        target_threshold = noise_floor + 0.2
        target_returns = intensities[intensities > target_threshold]
        
        # Calculate SNR
        if len(target_returns) > 0:
            signal_power = np.mean(target_returns)
            noise_power = noise_floor
            
            if noise_power > 0:
                snr_db = 10 * np.log10(signal_power / noise_power)
                self.snr_history.append(snr_db)
            else:
                snr_db = float('inf')
        else:
            snr_db = 0
            
        # Record return count
        self.return_count_history.append(len(radar_returns))
        
        # Detect interference
        interference_detected = self._detect_interference(radar_returns)
        
        # Performance assessment
        performance = self._assess_performance(noise_floor, snr_db)
        
        return {
            'noise_floor': noise_floor,
            'noise_floor_avg': np.mean(self.noise_floor_history),
            'snr_db': snr_db,
            'snr_avg': np.mean(self.snr_history) if self.snr_history else 0,
            'target_count': len(target_returns),
            'total_returns': len(radar_returns),
            'interference_detected': interference_detected,
            'performance_level': performance,
            'noise_level': 'high' if noise_floor > self.noise_floor_threshold else 'normal',
            'snr_acceptable': snr_db > self.min_snr_db
        }
        
    def _calculate_noise_floor(self, intensities):
        """
        Calculate noise floor from intensity data
        Uses lower percentile to avoid target contamination
        """
        if len(intensities) == 0:
            return 0.0
            
        # Use 20th percentile as noise floor estimate
        # This avoids contamination from strong returns
        noise_floor = np.percentile(intensities, 20)
        
        return float(noise_floor)
        
    def _detect_interference(self, radar_returns):
        """
        Detect RF interference patterns
        
        Interference indicators:
        - Periodic patterns in azimuth
        - Unusual spectral content
        - Sudden spikes in return count
        """
        if len(radar_returns) < 50:
            return False
            
        # Check for sudden spike in return count
        avg_count = np.mean(self.return_count_history) if self.return_count_history else 0
        current_count = len(radar_returns)
        
        if avg_count > 0 and current_count > avg_count * 3:
            # Sudden increase - possible interference
            self.interference_detected = True
            self.interference_pattern = 'sudden_spike'
            return True
            
        # Check for periodic patterns in azimuth
        azimuths = [r['azimuth'] for r in radar_returns]
        if self._detect_periodic_pattern(azimuths):
            self.interference_detected = True
            self.interference_pattern = 'periodic_azimuth'
            return True
            
        self.interference_detected = False
        self.interference_pattern = None
        return False
        
    def _detect_periodic_pattern(self, azimuths):
        """
        Detect periodic patterns in azimuth distribution
        Uses simple binning approach
        """
        if len(azimuths) < 50:
            return False
            
        # Bin azimuths into 36 bins (10 degrees each)
        bins = np.zeros(36)
        for az in azimuths:
            bin_idx = int(az / 10) % 36
            bins[bin_idx] += 1
            
        # Check for uniform distribution (expected) vs periodic (interference)
        expected_per_bin = len(azimuths) / 36
        
        # Calculate variance
        variance = np.var(bins)
        
        # High variance indicates non-uniform distribution (possible interference)
        threshold_variance = expected_per_bin * 5
        
        return variance > threshold_variance
        
    def _assess_performance(self, noise_floor, snr_db):
        """
        Assess overall radar performance
        
        Returns:
            'excellent', 'good', 'fair', or 'poor'
        """
        # Excellent: Low noise, high SNR
        if noise_floor < 0.1 and snr_db > 20:
            return 'excellent'
            
        # Good: Normal noise, good SNR
        if noise_floor < 0.15 and snr_db > 15:
            return 'good'
            
        # Fair: Moderate noise or SNR
        if noise_floor < 0.2 and snr_db > 10:
            return 'fair'
            
        # Poor: High noise or low SNR
        return 'poor'
        
    def calculate_range_performance(self, radar_returns, range_bins=10):
        """
        Analyze performance as function of range
        Detects range-dependent issues (rain, sea clutter, etc.)
        
        Returns:
            dict with range-binned performance
        """
        if not radar_returns:
            return None
            
        # Find max range
        max_range = max([r['range'] for r in radar_returns])
        bin_size = max_range / range_bins
        
        # Initialize bins
        range_bins_data = [[] for _ in range(range_bins)]
        
        # Bin returns by range
        for ret in radar_returns:
            bin_idx = min(int(ret['range'] / bin_size), range_bins - 1)
            range_bins_data[bin_idx].append(ret['intensity'])
            
        # Calculate statistics per bin
        range_performance = []
        for i, bin_data in enumerate(range_bins_data):
            if bin_data:
                range_start = i * bin_size
                range_end = (i + 1) * bin_size
                
                range_performance.append({
                    'range_start': range_start,
                    'range_end': range_end,
                    'mean_intensity': np.mean(bin_data),
                    'max_intensity': np.max(bin_data),
                    'return_count': len(bin_data)
                })
                
        return range_performance
        
    def estimate_sea_clutter_level(self, radar_returns):
        """
        Estimate sea clutter level
        High weak returns at close range indicate sea clutter
        """
        # Get returns within 1 NM (1852 meters)
        close_returns = [r for r in radar_returns if r['range'] < 1852]
        
        if not close_returns:
            return 'none'
            
        # Check intensity distribution
        intensities = [r['intensity'] for r in close_returns]
        mean_intensity = np.mean(intensities)
        
        # High number of weak returns = sea clutter
        if len(close_returns) > 100 and mean_intensity < 0.3:
            return 'high'
        elif len(close_returns) > 50 and mean_intensity < 0.4:
            return 'moderate'
        else:
            return 'low'
            
    def detect_rain_clutter(self, radar_returns):
        """
        Detect rain clutter
        Distributed weak returns across range indicate rain
        """
        if not radar_returns:
            return 'none'
            
        # Calculate return density across range
        intensities = np.array([r['intensity'] for r in radar_returns])
        
        # Rain shows as distributed weak returns
        weak_returns = intensities[intensities < 0.4]
        
        # Calculate percentage of weak returns
        weak_percentage = len(weak_returns) / len(intensities) if len(intensities) > 0 else 0
        
        if weak_percentage > 0.5:
            return 'heavy'
        elif weak_percentage > 0.3:
            return 'moderate'
        elif weak_percentage > 0.1:
            return 'light'
        else:
            return 'none'
            
    def get_performance_summary(self):
        """Get summary of radar performance metrics"""
        return {
            'noise_floor_avg': np.mean(self.noise_floor_history) if self.noise_floor_history else 0,
            'noise_floor_std': np.std(self.noise_floor_history) if self.noise_floor_history else 0,
            'snr_avg_db': np.mean(self.snr_history) if self.snr_history else 0,
            'snr_std_db': np.std(self.snr_history) if self.snr_history else 0,
            'snr_min_db': min(self.snr_history) if self.snr_history else 0,
            'interference_detected': self.interference_detected,
            'interference_pattern': self.interference_pattern,
            'samples_analyzed': len(self.noise_floor_history)
        }
