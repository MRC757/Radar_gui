"""
Kalman Filter for Track Smoothing
Provides smooth, accurate target tracking with velocity estimation
"""

import numpy as np


class KalmanTrackFilter:
    """
    Kalman filter for 2D target tracking
    
    State vector: [x, y, vx, vy]
    - x, y: position in meters
    - vx, vy: velocity in m/s
    """
    
    def __init__(self, dt=1.0, process_noise=1.0, measurement_noise=50.0):
        """
        Initialize Kalman filter
        
        Args:
            dt: Time step in seconds
            process_noise: Process noise standard deviation
            measurement_noise: Measurement noise standard deviation (meters)
        """
        self.dt = dt
        self._q = process_noise ** 2

        # State vector [x, y, vx, vy]
        self.x = np.zeros(4)
        
        # State covariance matrix
        self.P = np.eye(4) * 1000  # High initial uncertainty
        
        # State transition / process noise (constant velocity model)
        self._set_dt(dt)
        
        # Measurement matrix (we measure position only)
        self.H = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0]
        ])
        

        # Measurement noise covariance
        r = measurement_noise ** 2
        self.R = np.array([
            [r, 0],
            [0, r]
        ])
        
        self.initialized = False
        
    def initialize(self, x, y, vx=0, vy=0):
        """Initialize filter with position and velocity"""
        self.x = np.array([x, y, vx, vy])
        self.initialized = True
        
    def _set_dt(self, dt):
        """Rebuild F and Q for a time step of dt seconds."""
        self.dt = dt
        q = self._q
        self.F = np.array([
            [1, 0, dt, 0],
            [0, 1, 0, dt],
            [0, 0, 1, 0],
            [0, 0, 0, 1]
        ])
        self.Q = np.array([
            [q*dt**4/4, 0, q*dt**3/2, 0],
            [0, q*dt**4/4, 0, q*dt**3/2],
            [q*dt**3/2, 0, q*dt**2, 0],
            [0, q*dt**3/2, 0, q*dt**2]
        ])

    def predict(self, dt=None):
        """Predict the state dt seconds ahead.

        Pass the ACTUAL time since the previous update — measurements do not
        arrive at a fixed rate, and a wrong dt scales the velocity estimate
        (and therefore speed, course and CPA) by the same error.
        """
        if dt is not None and dt > 0 and dt != self.dt:
            self._set_dt(dt)
        # Predict state
        self.x = self.F @ self.x
        
        # Predict covariance
        self.P = self.F @ self.P @ self.F.T + self.Q
        
        return self.x[:2]  # Return predicted position
        
    def update(self, measurement):
        """
        Update filter with new measurement
        
        Args:
            measurement: [x, y] position measurement
            
        Returns:
            Filtered position [x, y]
        """
        z = np.array(measurement)
        
        # Innovation (measurement residual)
        y = z - self.H @ self.x
        
        # Innovation covariance
        S = self.H @ self.P @ self.H.T + self.R
        
        # Kalman gain
        K = self.P @ self.H.T @ np.linalg.inv(S)
        
        # Update state
        self.x = self.x + K @ y
        
        # Update covariance
        I = np.eye(4)
        self.P = (I - K @ self.H) @ self.P
        
        return self.x[:2]  # Return filtered position
        
    def get_velocity(self):
        """Get estimated velocity [vx, vy] in m/s"""
        return self.x[2:4]
        
    def get_speed_and_course(self):
        """
        Get speed and course from velocity estimate
        
        Returns:
            speed (knots), course (degrees)
        """
        vx, vy = self.x[2:4]
        
        # Speed in m/s
        speed_ms = np.sqrt(vx**2 + vy**2)
        
        # Convert to knots
        speed_knots = speed_ms / 0.514444
        
        # Course in degrees (0 = North, 90 = East)
        course_rad = np.arctan2(vx, vy)
        course_deg = np.degrees(course_rad)
        
        # Normalize to 0-360
        if course_deg < 0:
            course_deg += 360
            
        return speed_knots, course_deg


class AlphaBetaFilter:
    """
    Simple Alpha-Beta filter for track smoothing
    Lighter weight alternative to Kalman filter
    """
    
    def __init__(self, alpha=0.5, beta=0.1, dt=1.0):
        """
        Initialize Alpha-Beta filter
        
        Args:
            alpha: Position smoothing factor (0-1)
            beta: Velocity smoothing factor (0-1)
            dt: Time step in seconds
        """
        self.alpha = alpha
        self.beta = beta
        self.dt = dt
        
        self.x = 0
        self.y = 0
        self.vx = 0
        self.vy = 0
        
        self.initialized = False
        
    def initialize(self, x, y):
        """Initialize filter with position"""
        self.x = x
        self.y = y
        self.initialized = True
        
    def update(self, measured_x, measured_y):
        """
        Update filter with new measurement
        
        Returns:
            Filtered position [x, y]
        """
        if not self.initialized:
            self.initialize(measured_x, measured_y)
            return [self.x, self.y]
        
        # Predict
        predicted_x = self.x + self.vx * self.dt
        predicted_y = self.y + self.vy * self.dt
        
        # Residuals
        rx = measured_x - predicted_x
        ry = measured_y - predicted_y
        
        # Update position
        self.x = predicted_x + self.alpha * rx
        self.y = predicted_y + self.alpha * ry
        
        # Update velocity
        self.vx = self.vx + (self.beta / self.dt) * rx
        self.vy = self.vy + (self.beta / self.dt) * ry
        
        return [self.x, self.y]
        
    def get_velocity(self):
        """Get estimated velocity [vx, vy] in m/s"""
        return [self.vx, self.vy]
        
    def get_speed_and_course(self):
        """Get speed (knots) and course (degrees)"""
        speed_ms = np.sqrt(self.vx**2 + self.vy**2)
        speed_knots = speed_ms / 0.514444
        
        course_rad = np.arctan2(self.vx, self.vy)
        course_deg = np.degrees(course_rad)
        
        if course_deg < 0:
            course_deg += 360
            
        return speed_knots, course_deg
