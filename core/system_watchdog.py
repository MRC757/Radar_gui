"""
System Watchdog
Monitors critical system components and raises alarms on failures
"""

from datetime import datetime, timedelta
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
import logging


class ComponentWatchdog:
    """Monitor a single system component"""
    
    def __init__(self, name, timeout_seconds):
        """
        Initialize component watchdog
        
        Args:
            name: Component name
            timeout_seconds: Timeout in seconds before alarm
        """
        self.name = name
        self.timeout = timedelta(seconds=timeout_seconds)
        self.last_update = None
        self.is_active = False
        self.alarm_raised = False
        
    def heartbeat(self):
        """Record heartbeat from component"""
        self.last_update = datetime.now()
        
        if not self.is_active:
            self.is_active = True
            
        if self.alarm_raised:
            self.alarm_raised = False
            
    def check(self):
        """
        Check if component is healthy
        
        Returns:
            True if healthy, False if timeout
        """
        if not self.is_active or self.last_update is None:
            return False
            
        elapsed = datetime.now() - self.last_update
        
        if elapsed > self.timeout:
            if not self.alarm_raised:
                self.alarm_raised = True
                return False
            return False
            
        return True
        
    def get_status(self):
        """Get component status"""
        return {
            'name': self.name,
            'active': self.is_active,
            'last_update': self.last_update.isoformat() if self.last_update else None,
            'alarm': self.alarm_raised,
            'timeout_seconds': self.timeout.total_seconds()
        }


class SystemWatchdog(QObject):
    """Monitor all critical system components"""
    
    # Signals
    component_timeout = pyqtSignal(str)  # Component name
    component_recovered = pyqtSignal(str)  # Component name
    system_health_update = pyqtSignal(dict)  # Health status
    
    def __init__(self):
        super().__init__()
        
        self.components = {}
        self.alarm_states = {}
        
        # Define critical components
        self._setup_components()
        
        # Check timer
        self.check_timer = QTimer()
        self.check_timer.timeout.connect(self._check_all)
        self.check_timer.start(1000)  # Check every second
        
        logging.info("System watchdog started")
        
    def _setup_components(self):
        """Setup watchdog for critical components"""
        # NMEA data should update at least every 5 seconds
        self.add_component('nmea_gps', timeout_seconds=5)
        self.add_component('nmea_heading', timeout_seconds=5)
        
        # Radar data should update at least every 2 seconds
        self.add_component('radar_data', timeout_seconds=2)
        
        # GUI display should update continuously
        self.add_component('display_update', timeout_seconds=2)
        
        # System health check
        self.add_component('system_health', timeout_seconds=10)
        
    def add_component(self, name, timeout_seconds):
        """Add a component to monitor"""
        self.components[name] = ComponentWatchdog(name, timeout_seconds)
        self.alarm_states[name] = False
        
    def heartbeat(self, component_name):
        """Record heartbeat from component"""
        if component_name in self.components:
            self.components[component_name].heartbeat()
        else:
            logging.warning(f"Watchdog heartbeat from unknown component: {component_name}")
            
    def _check_all(self):
        """Check all components"""
        health_status = {}
        
        for name, watchdog in self.components.items():
            is_healthy = watchdog.check()
            health_status[name] = watchdog.get_status()
            
            # Emit signals on state changes
            if not is_healthy and not self.alarm_states[name]:
                # Component just timed out
                self.alarm_states[name] = True
                self.component_timeout.emit(name)
                logging.error(f"Component timeout: {name}")
                
            elif is_healthy and self.alarm_states[name]:
                # Component recovered
                self.alarm_states[name] = False
                self.component_recovered.emit(name)
                logging.info(f"Component recovered: {name}")
                
        # Emit overall health status
        self.system_health_update.emit(health_status)
        
    def get_health_summary(self):
        """Get health summary of all components"""
        summary = {
            'timestamp': datetime.now().isoformat(),
            'components': {},
            'healthy_count': 0,
            'alarm_count': 0
        }
        
        for name, watchdog in self.components.items():
            status = watchdog.get_status()
            summary['components'][name] = status
            
            if not status['alarm']:
                summary['healthy_count'] += 1
            else:
                summary['alarm_count'] += 1
                
        summary['all_healthy'] = (summary['alarm_count'] == 0)
        
        return summary
        
    def reset_component(self, component_name):
        """Reset a component (clear alarm)"""
        if component_name in self.components:
            self.components[component_name].alarm_raised = False
            self.alarm_states[component_name] = False
            logging.info(f"Component reset: {component_name}")
