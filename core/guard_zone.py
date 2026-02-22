"""
Guard Zone Module
Configurable guard zones for intrusion detection and alarms
"""

import math
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class GuardZone:
    """Guard zone definition"""
    name: str
    start_angle: float  # Degrees (0 = North)
    end_angle: float    # Degrees
    inner_range: float  # Nautical miles
    outer_range: float  # Nautical miles
    enabled: bool = True
    alarm_on_entry: bool = True
    alarm_on_exit: bool = False
    
    def contains_point(self, bearing, range_nm):
        """
        Check if a point (bearing, range) is inside the guard zone
        
        Args:
            bearing: Bearing in degrees (0-360)
            range_nm: Range in nautical miles
            
        Returns:
            True if point is inside guard zone
        """
        if not self.enabled:
            return False
        
        # Check range
        if not (self.inner_range <= range_nm <= self.outer_range):
            return False
        
        # Check bearing (handle wrap-around at 360/0)
        if self.start_angle <= self.end_angle:
            # Normal case: zone doesn't cross 360/0 boundary
            in_sector = self.start_angle <= bearing <= self.end_angle
        else:
            # Zone crosses 360/0 boundary
            in_sector = (bearing >= self.start_angle) or (bearing <= self.end_angle)
        
        return in_sector
    
    def get_boundary_points(self, num_points=50):
        """
        Get points along guard zone boundary for display
        
        Returns:
            List of (bearing, range) tuples
        """
        points = []
        
        # Calculate angular span
        if self.start_angle <= self.end_angle:
            angle_span = self.end_angle - self.start_angle
        else:
            angle_span = (360 - self.start_angle) + self.end_angle
        
        # Generate points along the arc
        for i in range(num_points + 1):
            fraction = i / num_points
            angle = (self.start_angle + fraction * angle_span) % 360
            
            # Add point at outer range
            points.append((angle, self.outer_range))
        
        # Add points along the sides
        # Right side
        for range_val in [self.outer_range, self.inner_range]:
            points.append((self.end_angle, range_val))
        
        # Return arc at inner range
        for i in range(num_points + 1):
            fraction = 1 - (i / num_points)
            angle = (self.start_angle + fraction * angle_span) % 360
            
            # Add point at inner range
            points.append((angle, self.inner_range))
        
        # Left side back to start
        points.append((self.start_angle, self.outer_range))
        
        return points


class GuardZoneManager:
    """Manage multiple guard zones and intrusion detection"""
    
    def __init__(self):
        self.zones: List[GuardZone] = []
        self.intrusions = {}  # zone_name -> set of target_ids
        self.alarm_history = []  # List of (timestamp, zone_name, target_id, event_type)
        
    def add_zone(self, zone: GuardZone):
        """Add a guard zone"""
        self.zones.append(zone)
        self.intrusions[zone.name] = set()
        
    def remove_zone(self, zone_name: str):
        """Remove a guard zone by name"""
        self.zones = [z for z in self.zones if z.name != zone_name]
        if zone_name in self.intrusions:
            del self.intrusions[zone_name]
            
    def get_zone(self, zone_name: str) -> GuardZone:
        """Get zone by name"""
        for zone in self.zones:
            if zone.name == zone_name:
                return zone
        return None
        
    def check_target(self, target_id, bearing, range_nm):
        """
        Check if target is in any guard zone
        
        Args:
            target_id: Unique target identifier
            bearing: Target bearing in degrees
            range_nm: Target range in nautical miles
            
        Returns:
            List of zone names that contain this target
        """
        from datetime import datetime
        
        zones_containing_target = []
        
        for zone in self.zones:
            if not zone.enabled:
                continue
                
            is_inside = zone.contains_point(bearing, range_nm)
            was_inside = target_id in self.intrusions[zone.name]
            
            if is_inside and not was_inside:
                # Entry event
                self.intrusions[zone.name].add(target_id)
                zones_containing_target.append(zone.name)
                
                if zone.alarm_on_entry:
                    self.alarm_history.append((
                        datetime.now(),
                        zone.name,
                        target_id,
                        'entry'
                    ))
                    
            elif not is_inside and was_inside:
                # Exit event
                self.intrusions[zone.name].remove(target_id)
                
                if zone.alarm_on_exit:
                    self.alarm_history.append((
                        datetime.now(),
                        zone.name,
                        target_id,
                        'exit'
                    ))
                    
            elif is_inside:
                # Still inside
                zones_containing_target.append(zone.name)
        
        return zones_containing_target
        
    def get_intrusions(self, zone_name: str):
        """Get set of target IDs currently in a zone"""
        return self.intrusions.get(zone_name, set())
        
    def clear_target(self, target_id):
        """Remove target from all zones (e.g., when track is lost)"""
        for zone_name in self.intrusions:
            self.intrusions[zone_name].discard(target_id)
            
    def get_recent_alarms(self, limit=10):
        """Get recent alarm events"""
        return self.alarm_history[-limit:]
        
    def create_default_zones(self):
        """Create some default guard zones"""
        # Bow sector guard zone
        self.add_zone(GuardZone(
            name="Bow Sector",
            start_angle=330,
            end_angle=30,
            inner_range=0.0,
            outer_range=3.0,
            enabled=True,
            alarm_on_entry=True
        ))
        
        # Port bow quarter
        self.add_zone(GuardZone(
            name="Port Bow",
            start_angle=270,
            end_angle=330,
            inner_range=0.0,
            outer_range=2.0,
            enabled=True,
            alarm_on_entry=True
        ))
        
        # Starboard bow quarter
        self.add_zone(GuardZone(
            name="Starboard Bow",
            start_angle=30,
            end_angle=90,
            inner_range=0.0,
            outer_range=2.0,
            enabled=True,
            alarm_on_entry=True
        ))


def calculate_target_bearing_range(own_lat, own_lon, target_lat, target_lon):
    """
    Calculate bearing and range from own ship to target
    
    Returns:
        bearing (degrees), range (nautical miles)
    """
    # Convert to radians
    lat1 = math.radians(own_lat)
    lon1 = math.radians(own_lon)
    lat2 = math.radians(target_lat)
    lon2 = math.radians(target_lon)
    
    # Calculate bearing
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = (math.cos(lat1) * math.sin(lat2) -
         math.sin(lat1) * math.cos(lat2) * math.cos(dlon))
    
    bearing_rad = math.atan2(y, x)
    bearing = (math.degrees(bearing_rad) + 360) % 360
    
    # Calculate range using Haversine formula
    dlat = lat2 - lat1
    a = (math.sin(dlat/2)**2 +
         math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    # Earth radius in nautical miles
    R = 3440.065
    range_nm = R * c
    
    return bearing, range_nm
