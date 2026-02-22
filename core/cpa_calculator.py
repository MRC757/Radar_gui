"""
CPA/TCPA Calculation Module
Closest Point of Approach and Time to CPA calculations for collision avoidance
Implements COLREGS-compliant threat assessment
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class CPAResult:
    """Result of CPA/TCPA calculation"""
    cpa_distance: float  # Nautical miles
    tcpa_minutes: float  # Minutes
    bearing_at_cpa: float  # Degrees
    range_at_cpa: float  # Nautical miles
    relative_bearing: float  # Degrees
    is_threat: bool  # True if CPA/TCPA below thresholds


class CPACalculator:
    """Calculate CPA/TCPA for target tracking"""
    
    def __init__(self, cpa_threshold_nm=2.0, tcpa_threshold_min=12.0):
        """
        Initialize CPA calculator

        Args:
            cpa_threshold_nm: CPA distance threshold for threat assessment (NM)
            tcpa_threshold_min: TCPA time threshold for threat assessment (minutes)
        """
        self.cpa_threshold = cpa_threshold_nm
        self.tcpa_threshold = tcpa_threshold_min

        # Risk-tier thresholds (configurable)
        self.critical_cpa = 0.5   # NM
        self.critical_tcpa = 6.0  # minutes
        self.warning_cpa = 1.0
        self.warning_tcpa = 12.0
        self.caution_cpa = 2.0
        self.caution_tcpa = 20.0
        
    def calculate(self, own_ship, target):
        """
        Calculate CPA and TCPA between own ship and target
        
        Args:
            own_ship: dict with keys: lat, lon, course, speed
            target: dict with keys: lat, lon, course, speed
            
        Returns:
            CPAResult object with all calculated values
        """
        # Convert positions to local coordinates (meters)
        own_x, own_y = 0, 0  # Own ship at origin
        target_x, target_y = self._latlon_to_meters(
            own_ship['lat'], own_ship['lon'],
            target['lat'], target['lon']
        )
        
        # Convert velocities to m/s (from knots)
        own_vx, own_vy = self._velocity_components(
            own_ship['course'], own_ship['speed']
        )
        target_vx, target_vy = self._velocity_components(
            target['course'], target['speed']
        )
        
        # Relative velocity (target relative to own ship)
        rel_vx = target_vx - own_vx
        rel_vy = target_vy - own_vy
        
        # Relative position
        rel_x = target_x - own_x
        rel_y = target_y - own_y
        
        # Calculate TCPA using relative motion
        # TCPA = -dot(rel_pos, rel_vel) / dot(rel_vel, rel_vel)
        rel_speed_squared = rel_vx**2 + rel_vy**2
        
        if rel_speed_squared < 1e-6:  # Nearly stationary relative motion
            # Target moving with us - no CPA event
            current_distance = math.sqrt(rel_x**2 + rel_y**2) / 1852.0  # to NM
            return CPAResult(
                cpa_distance=current_distance,
                tcpa_minutes=float('inf'),
                bearing_at_cpa=0,
                range_at_cpa=current_distance,
                relative_bearing=self._calculate_bearing(rel_x, rel_y),
                is_threat=False
            )
        
        # Time to CPA (seconds)
        tcpa_seconds = -(rel_x * rel_vx + rel_y * rel_vy) / rel_speed_squared
        
        # If TCPA is negative, CPA is in the past
        if tcpa_seconds < 0:
            # Already past CPA - threat is receding
            current_distance = math.sqrt(rel_x**2 + rel_y**2) / 1852.0
            return CPAResult(
                cpa_distance=current_distance,
                tcpa_minutes=-tcpa_seconds / 60.0,  # Negative TCPA
                bearing_at_cpa=0,
                range_at_cpa=current_distance,
                relative_bearing=self._calculate_bearing(rel_x, rel_y),
                is_threat=False
            )
        
        # Position at CPA
        cpa_x = rel_x + rel_vx * tcpa_seconds
        cpa_y = rel_y + rel_vy * tcpa_seconds
        
        # CPA distance
        cpa_distance_meters = math.sqrt(cpa_x**2 + cpa_y**2)
        cpa_distance_nm = cpa_distance_meters / 1852.0
        
        # Convert TCPA to minutes
        tcpa_minutes = tcpa_seconds / 60.0
        
        # Calculate bearing at CPA
        bearing_at_cpa = self._calculate_bearing(cpa_x, cpa_y)
        
        # Current range to target
        current_range = math.sqrt(rel_x**2 + rel_y**2) / 1852.0
        
        # Relative bearing to target
        relative_bearing = self._calculate_bearing(rel_x, rel_y)
        
        # Threat assessment
        is_threat = (cpa_distance_nm < self.cpa_threshold and 
                    tcpa_minutes < self.tcpa_threshold and
                    tcpa_minutes > 0)
        
        return CPAResult(
            cpa_distance=cpa_distance_nm,
            tcpa_minutes=tcpa_minutes,
            bearing_at_cpa=bearing_at_cpa,
            range_at_cpa=current_range,
            relative_bearing=relative_bearing,
            is_threat=is_threat
        )
    
    def _latlon_to_meters(self, own_lat, own_lon, target_lat, target_lon):
        """
        Convert lat/lon to local meters (flat Earth approximation)
        Accurate for distances < 100 NM
        """
        # Difference in degrees
        dlat = target_lat - own_lat
        dlon = target_lon - own_lon
        
        # Convert to meters
        # 1 degree latitude ≈ 111,120 meters
        # 1 degree longitude = 111,120 * cos(latitude) meters
        meters_per_degree_lat = 111120.0
        meters_per_degree_lon = 111120.0 * math.cos(math.radians(own_lat))
        
        x = dlon * meters_per_degree_lon
        y = dlat * meters_per_degree_lat
        
        return x, y
    
    def _velocity_components(self, course, speed_knots):
        """
        Convert course/speed to velocity components
        
        Args:
            course: Course in degrees (0 = North, 90 = East)
            speed_knots: Speed in knots
            
        Returns:
            vx, vy in meters/second
        """
        # Convert speed to m/s (1 knot = 0.514444 m/s)
        speed_ms = speed_knots * 0.514444
        
        # Convert course to radians
        course_rad = math.radians(course)
        
        # Calculate components (course is from North, clockwise)
        vx = speed_ms * math.sin(course_rad)  # East component
        vy = speed_ms * math.cos(course_rad)  # North component
        
        return vx, vy
    
    def _calculate_bearing(self, x, y):
        """
        Calculate bearing from origin to point (x, y)
        
        Returns:
            Bearing in degrees (0-360, 0 = North)
        """
        bearing_rad = math.atan2(x, y)
        bearing_deg = math.degrees(bearing_rad)
        
        # Normalize to 0-360
        if bearing_deg < 0:
            bearing_deg += 360
            
        return bearing_deg
    
    def assess_collision_risk(self, cpa_result):
        """
        Assess collision risk level based on CPA/TCPA

        Returns:
            'critical', 'warning', 'caution', or 'safe'
        """
        if not cpa_result.is_threat:
            return 'safe'

        if (cpa_result.cpa_distance < self.critical_cpa
                and cpa_result.tcpa_minutes < self.critical_tcpa):
            return 'critical'

        if (cpa_result.cpa_distance < self.warning_cpa
                and cpa_result.tcpa_minutes < self.warning_tcpa):
            return 'warning'

        if (cpa_result.cpa_distance < self.caution_cpa
                and cpa_result.tcpa_minutes < self.caution_tcpa):
            return 'caution'

        return 'safe'
    
    def calculate_bow_crossing_range(self, own_ship, target, cpa_result):
        """
        Calculate bow crossing range (BCR)
        Distance at which target will cross own ship's bow
        
        Returns:
            BCR in nautical miles, or None if no bow crossing
        """
        # Calculate relative bearing
        rel_bearing = cpa_result.relative_bearing
        
        # Check if target is crossing bow (relative bearing 0-90 or 270-360)
        if not (0 <= rel_bearing <= 90 or 270 <= rel_bearing <= 360):
            return None
        
        # Calculate intersection with own ship's course line
        # This is a simplified calculation
        # Full implementation would use vector intersection
        
        # For now, return approximate value based on geometry
        if cpa_result.tcpa_minutes > 0:
            # Distance own ship will travel to CPA
            own_distance = own_ship['speed'] * (cpa_result.tcpa_minutes / 60.0)
            return own_distance
        
        return None


def calculate_intercept(own_ship, target):
    """
    Calculate course, speed, and time to intercept a moving target.

    Args:
        own_ship: dict with lat, lon, course, speed (knots)
        target: dict with lat, lon, course, speed (knots)

    Returns:
        dict with intercept_course, intercept_speed_min, intercept_time,
        intercept_lat, intercept_lon, feasible
    """
    # Convert positions to local meters (own ship at origin)
    meters_per_deg_lat = 111120.0
    meters_per_deg_lon = 111120.0 * math.cos(math.radians(own_ship['lat']))

    dx = (target['lon'] - own_ship['lon']) * meters_per_deg_lon
    dy = (target['lat'] - own_ship['lat']) * meters_per_deg_lat

    # Target velocity in m/s
    tgt_spd_ms = target['speed'] * 0.514444
    tgt_rad = math.radians(target['course'])
    tvx = tgt_spd_ms * math.sin(tgt_rad)
    tvy = tgt_spd_ms * math.cos(tgt_rad)

    # Own ship speed in m/s
    own_spd_ms = own_ship['speed'] * 0.514444

    # Solve for intercept time using quadratic:
    # |P_target(t) - P_own|^2 = (own_spd * t)^2
    # (dx + tvx*t)^2 + (dy + tvy*t)^2 = (own_spd*t)^2
    # (tvx^2 + tvy^2 - own_spd^2)*t^2 + 2*(dx*tvx + dy*tvy)*t + (dx^2 + dy^2) = 0
    a = tvx**2 + tvy**2 - own_spd_ms**2
    b = 2.0 * (dx * tvx + dy * tvy)
    c = dx**2 + dy**2

    feasible = False
    intercept_time_s = None
    intercept_course = 0.0
    intercept_lat = 0.0
    intercept_lon = 0.0

    discriminant = b**2 - 4 * a * c

    if abs(a) < 1e-10:
        # Linear case: own speed equals target speed
        if abs(b) > 1e-10:
            t = -c / b
            if t > 0:
                intercept_time_s = t
                feasible = True
    elif discriminant >= 0:
        sqrt_d = math.sqrt(discriminant)
        t1 = (-b - sqrt_d) / (2 * a)
        t2 = (-b + sqrt_d) / (2 * a)
        # Pick smallest positive time
        candidates = [t for t in (t1, t2) if t > 1.0]
        if candidates:
            intercept_time_s = min(candidates)
            feasible = True

    # Calculate minimum speed to intercept (search over time)
    min_speed_kts = None
    best_t_for_min = None
    for t_try in range(10, 7200, 10):  # 10s to 2 hours
        t_s = float(t_try)
        ix = dx + tvx * t_s
        iy = dy + tvy * t_s
        dist_m = math.sqrt(ix**2 + iy**2)
        req_spd_ms = dist_m / t_s
        req_spd_kts = req_spd_ms / 0.514444
        if min_speed_kts is None or req_spd_kts < min_speed_kts:
            min_speed_kts = req_spd_kts
            best_t_for_min = t_s

    if intercept_time_s is not None and feasible:
        # Intercept position
        ix = dx + tvx * intercept_time_s
        iy = dy + tvy * intercept_time_s
        intercept_lat = own_ship['lat'] + iy / meters_per_deg_lat
        intercept_lon = own_ship['lon'] + ix / meters_per_deg_lon
        # Course to steer
        intercept_course = math.degrees(math.atan2(ix, iy)) % 360
    elif best_t_for_min is not None:
        # Use the minimum-speed time for course estimate
        ix = dx + tvx * best_t_for_min
        iy = dy + tvy * best_t_for_min
        intercept_lat = own_ship['lat'] + iy / meters_per_deg_lat
        intercept_lon = own_ship['lon'] + ix / meters_per_deg_lon
        intercept_course = math.degrees(math.atan2(ix, iy)) % 360

    return {
        'intercept_course': round(intercept_course, 1),
        'intercept_speed_min': round(min_speed_kts, 1) if min_speed_kts else 0.0,
        'intercept_time': round(intercept_time_s / 60.0, 1) if intercept_time_s else None,
        'intercept_lat': intercept_lat,
        'intercept_lon': intercept_lon,
        'feasible': feasible,
    }


class ThreatAssessor:
    """Assess collision threats and generate alarms"""
    
    def __init__(self):
        self.cpa_calculator = CPACalculator()
        self.active_threats = {}  # target_id -> threat_level
        
    def assess_target(self, target_id, own_ship, target):
        """
        Assess single target for collision threat
        
        Returns:
            dict with threat assessment
        """
        cpa_result = self.cpa_calculator.calculate(own_ship, target)
        risk_level = self.cpa_calculator.assess_collision_risk(cpa_result)
        bcr = self.cpa_calculator.calculate_bow_crossing_range(own_ship, target, cpa_result)
        
        # Update active threats
        if risk_level in ['critical', 'warning', 'caution']:
            self.active_threats[target_id] = risk_level
        elif target_id in self.active_threats:
            del self.active_threats[target_id]
        
        return {
            'target_id': target_id,
            'cpa': cpa_result.cpa_distance,
            'tcpa': cpa_result.tcpa_minutes,
            'bearing_at_cpa': cpa_result.bearing_at_cpa,
            'current_range': cpa_result.range_at_cpa,
            'relative_bearing': cpa_result.relative_bearing,
            'risk_level': risk_level,
            'is_threat': cpa_result.is_threat,
            'bow_crossing_range': bcr
        }
    
    def get_highest_threat(self):
        """Get the highest priority threat"""
        if not self.active_threats:
            return None
        
        # Priority: critical > warning > caution
        priority = {'critical': 3, 'warning': 2, 'caution': 1}
        
        highest_threat = max(
            self.active_threats.items(),
            key=lambda x: priority.get(x[1], 0)
        )
        
        return highest_threat
