"""
Radar Data Logger
Comprehensive logging for radar, NMEA, and system events
Enables replay, debugging, and incident investigation
"""

import os
import json
import gzip
from datetime import datetime
from pathlib import Path
import threading


class RadarDataLogger:
    """Log all radar and navigation data"""
    
    def __init__(self, log_dir='radar_logs', compress=True):
        """
        Initialize data logger
        
        Args:
            log_dir: Directory for log files
            compress: Use gzip compression for logs
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        self.compress = compress
        self.session_start = datetime.now()
        
        # Create session directory
        session_name = self.session_start.strftime('%Y%m%d_%H%M%S')
        self.session_dir = self.log_dir / session_name
        self.session_dir.mkdir(exist_ok=True)
        
        # File handles
        self.nmea_file = None
        self.radar_file = None
        self.event_file = None
        self.track_file = None
        
        # Buffers for batch writing
        self.nmea_buffer = []
        self.radar_buffer = []
        self.event_buffer = []
        self.track_buffer = []
        
        self.buffer_size = 100  # Write every N entries
        
        # Thread lock for thread-safe logging
        self.lock = threading.Lock()
        
        # Open log files
        self._open_files()
        
        # Log session start
        self.log_event('session_start', {
            'timestamp': self.session_start.isoformat(),
            'session_dir': str(self.session_dir)
        })
        
    def _open_files(self):
        """Open log files"""
        ext = '.json.gz' if self.compress else '.json'
        
        nmea_path = self.session_dir / f'nmea{ext}'
        radar_path = self.session_dir / f'radar{ext}'
        event_path = self.session_dir / f'events{ext}'
        track_path = self.session_dir / f'tracks{ext}'
        
        if self.compress:
            self.nmea_file = gzip.open(nmea_path, 'wt')
            self.radar_file = gzip.open(radar_path, 'wt')
            self.event_file = gzip.open(event_path, 'wt')
            self.track_file = gzip.open(track_path, 'wt')
        else:
            self.nmea_file = open(nmea_path, 'w')
            self.radar_file = open(radar_path, 'w')
            self.event_file = open(event_path, 'w')
            self.track_file = open(track_path, 'w')
            
    def log_nmea(self, sentence, source_name):
        """
        Log NMEA sentence
        
        Args:
            sentence: NMEA sentence string
            source_name: Source name
        """
        with self.lock:
            entry = {
                'timestamp': datetime.now().isoformat(),
                'source': source_name,
                'sentence': sentence
            }
            
            self.nmea_buffer.append(entry)
            
            if len(self.nmea_buffer) >= self.buffer_size:
                self._flush_nmea()
                
    def log_radar_data(self, radar_data):
        """
        Log radar data
        
        Args:
            radar_data: Dictionary with radar returns
        """
        with self.lock:
            entry = {
                'timestamp': datetime.now().isoformat(),
                'data': radar_data
            }
            
            self.radar_buffer.append(entry)
            
            if len(self.radar_buffer) >= self.buffer_size:
                self._flush_radar()
                
    def log_event(self, event_type, data):
        """
        Log system event
        
        Args:
            event_type: Type of event (e.g., 'alarm', 'config_change')
            data: Event data dictionary
        """
        with self.lock:
            entry = {
                'timestamp': datetime.now().isoformat(),
                'type': event_type,
                'data': data
            }
            
            self.event_buffer.append(entry)
            
            if len(self.event_buffer) >= self.buffer_size:
                self._flush_events()
                
    def log_tracks(self, radar_tracks, ais_tracks):
        """
        Log track data
        
        Args:
            radar_tracks: List of radar track dictionaries
            ais_tracks: List of AIS track dictionaries
        """
        with self.lock:
            entry = {
                'timestamp': datetime.now().isoformat(),
                'radar_tracks': radar_tracks,
                'ais_tracks': ais_tracks
            }
            
            self.track_buffer.append(entry)
            
            if len(self.track_buffer) >= self.buffer_size:
                self._flush_tracks()
                
    def _flush_nmea(self):
        """Flush NMEA buffer to file"""
        if self.nmea_buffer and self.nmea_file:
            for entry in self.nmea_buffer:
                self.nmea_file.write(json.dumps(entry) + '\n')
            self.nmea_file.flush()
            self.nmea_buffer.clear()
            
    def _flush_radar(self):
        """Flush radar buffer to file"""
        if self.radar_buffer and self.radar_file:
            for entry in self.radar_buffer:
                self.radar_file.write(json.dumps(entry) + '\n')
            self.radar_file.flush()
            self.radar_buffer.clear()
            
    def _flush_events(self):
        """Flush event buffer to file"""
        if self.event_buffer and self.event_file:
            for entry in self.event_buffer:
                self.event_file.write(json.dumps(entry) + '\n')
            self.event_file.flush()
            self.event_buffer.clear()
            
    def _flush_tracks(self):
        """Flush track buffer to file"""
        if self.track_buffer and self.track_file:
            for entry in self.track_buffer:
                self.track_file.write(json.dumps(entry) + '\n')
            self.track_file.flush()
            self.track_buffer.clear()
            
    def flush_all(self):
        """Flush all buffers"""
        with self.lock:
            self._flush_nmea()
            self._flush_radar()
            self._flush_events()
            self._flush_tracks()
            
    def close(self):
        """Close all log files"""
        self.log_event('session_end', {
            'timestamp': datetime.now().isoformat(),
            'duration_seconds': (datetime.now() - self.session_start).total_seconds()
        })
        
        # Flush remaining data
        self.flush_all()
        
        # Close files
        if self.nmea_file:
            self.nmea_file.close()
        if self.radar_file:
            self.radar_file.close()
        if self.event_file:
            self.event_file.close()
        if self.track_file:
            self.track_file.close()
            
    def get_session_info(self):
        """Get information about current session"""
        return {
            'session_dir': str(self.session_dir),
            'start_time': self.session_start.isoformat(),
            'duration_seconds': (datetime.now() - self.session_start).total_seconds(),
            'nmea_entries': len(self.nmea_buffer),
            'radar_entries': len(self.radar_buffer),
            'event_entries': len(self.event_buffer),
            'track_entries': len(self.track_buffer)
        }


class LogReplayer:
    """Replay logged data for debugging and analysis"""
    
    def __init__(self, session_dir):
        """
        Initialize log replayer
        
        Args:
            session_dir: Path to session directory
        """
        self.session_dir = Path(session_dir)
        
        if not self.session_dir.exists():
            raise ValueError(f"Session directory not found: {session_dir}")
            
        # Detect file format (compressed or not)
        self.compressed = (self.session_dir / 'nmea.json.gz').exists()
        
    def replay_nmea(self, callback):
        """
        Replay NMEA data
        
        Args:
            callback: Function to call with each NMEA entry
                     callback(timestamp, source, sentence)
        """
        ext = '.json.gz' if self.compressed else '.json'
        nmea_path = self.session_dir / f'nmea{ext}'
        
        if not nmea_path.exists():
            return
            
        open_func = gzip.open if self.compressed else open
        
        with open_func(nmea_path, 'rt') as f:
            for line in f:
                entry = json.loads(line)
                callback(
                    entry['timestamp'],
                    entry['source'],
                    entry['sentence']
                )
                
    def replay_radar(self, callback):
        """
        Replay radar data
        
        Args:
            callback: Function to call with each radar entry
                     callback(timestamp, radar_data)
        """
        ext = '.json.gz' if self.compressed else '.json'
        radar_path = self.session_dir / f'radar{ext}'
        
        if not radar_path.exists():
            return
            
        open_func = gzip.open if self.compressed else open
        
        with open_func(radar_path, 'rt') as f:
            for line in f:
                entry = json.loads(line)
                callback(
                    entry['timestamp'],
                    entry['data']
                )
                
    def replay_events(self, callback):
        """
        Replay system events
        
        Args:
            callback: Function to call with each event
                     callback(timestamp, event_type, data)
        """
        ext = '.json.gz' if self.compressed else '.json'
        event_path = self.session_dir / f'events{ext}'
        
        if not event_path.exists():
            return
            
        open_func = gzip.open if self.compressed else open
        
        with open_func(event_path, 'rt') as f:
            for line in f:
                entry = json.loads(line)
                callback(
                    entry['timestamp'],
                    entry['type'],
                    entry['data']
                )
                
    def get_session_summary(self):
        """Get summary of logged session"""
        summary = {
            'session_dir': str(self.session_dir),
            'nmea_count': 0,
            'radar_count': 0,
            'event_count': 0,
            'track_count': 0,
            'start_time': None,
            'end_time': None
        }
        
        # Count entries and get time range
        ext = '.json.gz' if self.compressed else '.json'
        open_func = gzip.open if self.compressed else open
        
        for file_name, count_key in [
            ('nmea', 'nmea_count'),
            ('radar', 'radar_count'),
            ('events', 'event_count'),
            ('tracks', 'track_count')
        ]:
            file_path = self.session_dir / f'{file_name}{ext}'
            if file_path.exists():
                with open_func(file_path, 'rt') as f:
                    for line in f:
                        entry = json.loads(line)
                        summary[count_key] += 1
                        
                        # Update time range
                        ts = entry['timestamp']
                        if summary['start_time'] is None or ts < summary['start_time']:
                            summary['start_time'] = ts
                        if summary['end_time'] is None or ts > summary['end_time']:
                            summary['end_time'] = ts
                            
        return summary
