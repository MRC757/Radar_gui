"""
Plugin System
Extensible architecture for adding features without modifying core code
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, List
import importlib
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class RadarPlugin(ABC):
    """Base class for radar system plugins"""
    
    def __init__(self):
        self.name = "Unnamed Plugin"
        self.version = "1.0.0"
        self.description = ""
        self.enabled = True
        
    @abstractmethod
    def initialize(self, radar_system):
        """
        Initialize plugin with radar system reference
        
        Args:
            radar_system: Reference to main radar system
        """
        pass
        
    @abstractmethod
    def process_radar_data(self, radar_data):
        """
        Process radar data
        
        Args:
            radar_data: Dictionary with radar video data
            
        Returns:
            Modified radar_data or None
        """
        pass
        
    def process_nmea_data(self, nmea_sentence, source):
        """
        Process NMEA data (optional)
        
        Args:
            nmea_sentence: NMEA sentence string
            source: Source name
        """
        pass
        
    def process_tracks(self, radar_tracks, ais_tracks):
        """
        Process track data (optional)
        
        Args:
            radar_tracks: List of radar tracks
            ais_tracks: List of AIS tracks
        """
        pass
        
    def get_menu_items(self):
        """
        Get menu items to add to application menu
        
        Returns:
            List of (menu_name, action_name, callback) tuples
        """
        return []
        
    def get_config_widget(self):
        """
        Get configuration widget for plugin
        
        Returns:
            QWidget for plugin configuration or None
        """
        return None
        
    def shutdown(self):
        """Cleanup on plugin shutdown"""
        pass


class PluginManager:
    """Manage radar system plugins"""
    
    def __init__(self, plugin_dir='plugins'):
        """
        Initialize plugin manager
        
        Args:
            plugin_dir: Directory containing plugins
        """
        self.plugin_dir = Path(plugin_dir)
        self.plugins: Dict[str, RadarPlugin] = {}
        self.radar_system = None
        
        # Create plugin directory if it doesn't exist
        self.plugin_dir.mkdir(exist_ok=True)
        
    def set_radar_system(self, radar_system):
        """Set reference to radar system"""
        self.radar_system = radar_system
        
    def discover_plugins(self):
        """Discover available plugins in plugin directory"""
        discovered = []
        
        if not self.plugin_dir.exists():
            return discovered
            
        # Look for Python files in plugin directory
        for file_path in self.plugin_dir.glob('*.py'):
            if file_path.stem.startswith('_'):
                continue
                
            try:
                # Import module
                module_name = file_path.stem
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Look for RadarPlugin subclasses
                for item_name in dir(module):
                    item = getattr(module, item_name)
                    
                    if (isinstance(item, type) and 
                        issubclass(item, RadarPlugin) and 
                        item is not RadarPlugin):
                        
                        discovered.append({
                            'name': item_name,
                            'module': module_name,
                            'class': item,
                            'path': str(file_path)
                        })
                        
            except Exception as e:
                logger.error("Error discovering plugin %s: %s", file_path, e)
                
        return discovered
        
    def load_plugin(self, plugin_class):
        """
        Load and initialize a plugin
        
        Args:
            plugin_class: Plugin class to instantiate
            
        Returns:
            Plugin instance or None on error
        """
        try:
            plugin = plugin_class()
            
            if self.radar_system:
                plugin.initialize(self.radar_system)
                
            self.plugins[plugin.name] = plugin
            logger.info("Loaded plugin: %s v%s", plugin.name, plugin.version)
            
            return plugin
            
        except Exception as e:
            logger.error("Error loading plugin: %s", e)
            return None
            
    def unload_plugin(self, plugin_name):
        """Unload a plugin"""
        if plugin_name in self.plugins:
            plugin = self.plugins[plugin_name]
            plugin.shutdown()
            del self.plugins[plugin_name]
            logger.info("Unloaded plugin: %s", plugin_name)
            
    def process_radar_data(self, radar_data):
        """Pass radar data through all enabled plugins"""
        for plugin in self.plugins.values():
            if plugin.enabled:
                result = plugin.process_radar_data(radar_data)
                if result is not None:
                    radar_data = result
                    
        return radar_data
        
    def process_nmea_data(self, nmea_sentence, source):
        """Pass NMEA data through all enabled plugins"""
        for plugin in self.plugins.values():
            if plugin.enabled:
                plugin.process_nmea_data(nmea_sentence, source)
                
    def process_tracks(self, radar_tracks, ais_tracks):
        """Pass track data through all enabled plugins"""
        for plugin in self.plugins.values():
            if plugin.enabled:
                plugin.process_tracks(radar_tracks, ais_tracks)
                
    def get_all_menu_items(self):
        """Get menu items from all plugins"""
        menu_items = []
        for plugin in self.plugins.values():
            if plugin.enabled:
                menu_items.extend(plugin.get_menu_items())
        return menu_items
        
    def get_plugin_list(self):
        """Get list of loaded plugins"""
        return [
            {
                'name': plugin.name,
                'version': plugin.version,
                'description': plugin.description,
                'enabled': plugin.enabled
            }
            for plugin in self.plugins.values()
        ]


# Example plugin implementations

class RecordingPlugin(RadarPlugin):
    """Example: Record all data to disk"""
    
    def __init__(self):
        super().__init__()
        self.name = "Data Recording"
        self.version = "1.0.0"
        self.description = "Record all radar and NMEA data"
        self.recording = False
        self.output_file = None
        
    def initialize(self, radar_system):
        """Initialize recording plugin"""
        pass
        
    def process_radar_data(self, radar_data):
        """Record radar data"""
        if self.recording and self.output_file:
            # Write to file
            pass
        return radar_data  # Pass through unchanged
        
    def start_recording(self, filename):
        """Start recording"""
        self.output_file = open(filename, 'w')
        self.recording = True
        
    def stop_recording(self):
        """Stop recording"""
        if self.output_file:
            self.output_file.close()
        self.recording = False
        
    def shutdown(self):
        """Cleanup"""
        self.stop_recording()


class TargetClassificationPlugin(RadarPlugin):
    """Example: AI-based target classification"""
    
    def __init__(self):
        super().__init__()
        self.name = "Target Classification"
        self.version = "1.0.0"
        self.description = "Classify targets using ML"
        
    def initialize(self, radar_system):
        """Initialize ML model"""
        # Load ML model here
        pass
        
    def process_radar_data(self, radar_data):
        """Classify targets in radar data"""
        # Run ML classification
        # Add classification results to targets
        return radar_data
        
    def process_tracks(self, radar_tracks, ais_tracks):
        """Classify tracks"""
        # Could classify track patterns
        # (fishing vessel, cargo ship, small craft, etc.)
        pass


class WeatherOverlayPlugin(RadarPlugin):
    """Example: Weather radar overlay"""
    
    def __init__(self):
        super().__init__()
        self.name = "Weather Overlay"
        self.version = "1.0.0"
        self.description = "Overlay weather radar data"
        self.weather_data = None
        
    def initialize(self, radar_system):
        """Initialize weather data source"""
        # Connect to weather data source
        pass
        
    def process_radar_data(self, radar_data):
        """Add weather overlay to radar data"""
        if self.weather_data:
            # Merge weather data with radar data
            pass
        return radar_data
        
    def get_menu_items(self):
        """Add weather menu items"""
        return [
            ("View", "Show Weather", self.toggle_weather),
            ("Settings", "Weather Source...", self.configure_weather)
        ]
        
    def toggle_weather(self):
        """Toggle weather overlay"""
        self.enabled = not self.enabled
        
    def configure_weather(self):
        """Open weather configuration dialog"""
        pass
