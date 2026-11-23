"""
Performance Monitor
Track system performance metrics (FPS, CPU, memory, data rates)
"""

import time
import psutil
from collections import deque
from PyQt6.QtCore import QObject, pyqtSignal, QTimer


class PerformanceMonitor(QObject):
    """Monitor system performance metrics"""
    
    # Signal with performance metrics
    metrics_updated = pyqtSignal(dict)
    
    def __init__(self, history_size=60):
        super().__init__()
        
        self.history_size = history_size
        
        # Metrics history (last N samples)
        self.fps_history = deque(maxlen=history_size)
        self.cpu_history = deque(maxlen=history_size)
        self.memory_history = deque(maxlen=history_size)
        self.nmea_rate_history = deque(maxlen=history_size)
        self.radar_rate_history = deque(maxlen=history_size)
        
        # Frame counting for FPS
        self.frame_count = 0
        self.last_frame_time = time.time()
        self.current_fps = 0
        
        # Data rate counting
        self.nmea_count = 0
        self.radar_count = 0
        self.last_rate_time = time.time()
        self.current_nmea_rate = 0
        self.current_radar_rate = 0
        
        # Process handle for CPU/memory monitoring
        self.process = psutil.Process()
        
        # Update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_metrics)
        self.update_timer.start(1000)  # Update every second
        
    def record_frame(self):
        """Record a display frame (for FPS calculation)"""
        self.frame_count += 1
        
    def record_nmea_packet(self):
        """Record an NMEA packet (for rate calculation)"""
        self.nmea_count += 1
        
    def record_radar_update(self):
        """Record a radar update (for rate calculation)"""
        self.radar_count += 1
        
    def _update_metrics(self):
        """Calculate and emit performance metrics"""
        current_time = time.time()
        
        # Calculate FPS
        time_delta = current_time - self.last_frame_time
        if time_delta > 0:
            self.current_fps = self.frame_count / time_delta
            self.fps_history.append(self.current_fps)
        
        self.frame_count = 0
        self.last_frame_time = current_time
        
        # Calculate data rates
        rate_delta = current_time - self.last_rate_time
        if rate_delta > 0:
            self.current_nmea_rate = self.nmea_count / rate_delta
            self.current_radar_rate = self.radar_count / rate_delta
            
            self.nmea_rate_history.append(self.current_nmea_rate)
            self.radar_rate_history.append(self.current_radar_rate)
        
        self.nmea_count = 0
        self.radar_count = 0
        self.last_rate_time = current_time
        
        # Get CPU and memory usage
        try:
            cpu_percent = self.process.cpu_percent()
            memory_mb = self.process.memory_info().rss / 1024 / 1024
            
            self.cpu_history.append(cpu_percent)
            self.memory_history.append(memory_mb)
        except Exception:   # psutil unavailable / access denied
            cpu_percent = 0
            memory_mb = 0
        
        # Prepare metrics dictionary
        metrics = {
            'fps': self.current_fps,
            'fps_avg': sum(self.fps_history) / len(self.fps_history) if self.fps_history else 0,
            'cpu_percent': cpu_percent,
            'cpu_avg': sum(self.cpu_history) / len(self.cpu_history) if self.cpu_history else 0,
            'memory_mb': memory_mb,
            'memory_avg': sum(self.memory_history) / len(self.memory_history) if self.memory_history else 0,
            'nmea_rate': self.current_nmea_rate,
            'nmea_rate_avg': sum(self.nmea_rate_history) / len(self.nmea_rate_history) if self.nmea_rate_history else 0,
            'radar_rate': self.current_radar_rate,
            'radar_rate_avg': sum(self.radar_rate_history) / len(self.radar_rate_history) if self.radar_rate_history else 0,
            'timestamp': time.time()
        }
        
        # Emit metrics
        self.metrics_updated.emit(metrics)
        
    def get_current_metrics(self):
        """Get current performance metrics"""
        return {
            'fps': self.current_fps,
            'cpu_percent': self.cpu_history[-1] if self.cpu_history else 0,
            'memory_mb': self.memory_history[-1] if self.memory_history else 0,
            'nmea_rate': self.current_nmea_rate,
            'radar_rate': self.current_radar_rate
        }
        
    def get_statistics(self):
        """Get performance statistics"""
        def calc_stats(history):
            if not history:
                return {'min': 0, 'max': 0, 'avg': 0}
            return {
                'min': min(history),
                'max': max(history),
                'avg': sum(history) / len(history)
            }
        
        return {
            'fps': calc_stats(self.fps_history),
            'cpu': calc_stats(self.cpu_history),
            'memory': calc_stats(self.memory_history),
            'nmea_rate': calc_stats(self.nmea_rate_history),
            'radar_rate': calc_stats(self.radar_rate_history)
        }


class PerformanceMetricsOverlay:
    """Helper class to format performance metrics for display"""
    
    @staticmethod
    def format_metrics(metrics):
        """Format metrics as display string"""
        lines = []
        
        lines.append(f"FPS: {metrics['fps']:.1f} (avg: {metrics['fps_avg']:.1f})")
        lines.append(f"CPU: {metrics['cpu_percent']:.1f}% (avg: {metrics['cpu_avg']:.1f}%)")
        lines.append(f"MEM: {metrics['memory_mb']:.1f} MB (avg: {metrics['memory_avg']:.1f} MB)")
        lines.append(f"NMEA: {metrics['nmea_rate']:.1f} Hz (avg: {metrics['nmea_rate_avg']:.1f} Hz)")
        lines.append(f"RADAR: {metrics['radar_rate']:.1f} Hz (avg: {metrics['radar_rate_avg']:.1f} Hz)")
        
        return '\n'.join(lines)
        
    @staticmethod
    def get_color_for_fps(fps):
        """Get color based on FPS (for visual indication)"""
        if fps >= 15:
            return (0, 255, 0)  # Green - good
        elif fps >= 10:
            return (255, 255, 0)  # Yellow - acceptable
        else:
            return (255, 0, 0)  # Red - poor
            
    @staticmethod
    def get_color_for_cpu(cpu_percent):
        """Get color based on CPU usage"""
        if cpu_percent < 50:
            return (0, 255, 0)  # Green - good
        elif cpu_percent < 80:
            return (255, 255, 0)  # Yellow - acceptable
        else:
            return (255, 0, 0)  # Red - high
