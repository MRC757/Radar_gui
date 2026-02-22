"""
Test Scenarios
Automated test scenarios for CPA/TCPA validation and system testing
"""

import logging
import math
from dataclasses import dataclass
from typing import List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ScenarioTarget:
    """Target definition for test scenario"""
    name: str
    lat: float
    lon: float
    course: float
    speed: float


@dataclass
class TestScenario:
    """Complete test scenario"""
    name: str
    description: str
    own_ship: ScenarioTarget
    targets: List[ScenarioTarget]
    expected_results: dict  # Expected CPA/TCPA values


class RadarTestScenarios:
    """Collection of test scenarios for validation"""
    
    @staticmethod
    def crossing_scenario():
        """
        Classic crossing situation
        Target crosses ahead of own ship from port to starboard
        """
        own_ship = ScenarioTarget(
            name="Own Ship",
            lat=37.0,
            lon=-76.3,
            course=90,  # Heading East
            speed=10    # 10 knots
        )
        
        target = ScenarioTarget(
            name="Crossing Target",
            lat=37.05,      # 3 NM north
            lon=-76.35,     # Slightly west
            course=180,     # Heading South
            speed=12        # 12 knots
        )
        
        return TestScenario(
            name="Crossing Scenario",
            description="Target crossing ahead from port to starboard",
            own_ship=own_ship,
            targets=[target],
            expected_results={
                'cpa_nm': 0.8,      # Expected CPA ~0.8 NM
                'tcpa_min': 12.0,   # Expected TCPA ~12 minutes
                'risk_level': 'warning'
            }
        )
    
    @staticmethod
    def head_on_scenario():
        """
        Head-on situation
        Target approaching directly
        """
        own_ship = ScenarioTarget(
            name="Own Ship",
            lat=37.0,
            lon=-76.3,
            course=0,   # Heading North
            speed=10
        )
        
        target = ScenarioTarget(
            name="Head-On Target",
            lat=37.1,   # 6 NM north
            lon=-76.3,  # Same longitude
            course=180, # Heading South (toward us)
            speed=15
        )
        
        return TestScenario(
            name="Head-On Scenario",
            description="Target approaching head-on",
            own_ship=own_ship,
            targets=[target],
            expected_results={
                'cpa_nm': 0.0,      # Direct collision course
                'tcpa_min': 14.4,   # 6 NM / 25 knots = 0.24 hr = 14.4 min
                'risk_level': 'critical'
            }
        )
    
    @staticmethod
    def overtaking_scenario():
        """
        Overtaking situation
        Own ship overtaking slower target ahead
        """
        own_ship = ScenarioTarget(
            name="Own Ship",
            lat=37.0,
            lon=-76.3,
            course=45,  # Heading NE
            speed=15
        )
        
        target = ScenarioTarget(
            name="Slow Target",
            lat=37.05,   # Ahead
            lon=-76.25,  # Ahead
            course=45,   # Same course
            speed=8      # Slower
        )
        
        return TestScenario(
            name="Overtaking Scenario",
            description="Own ship overtaking slower target",
            own_ship=own_ship,
            targets=[target],
            expected_results={
                'cpa_nm': 0.0,      # On same track
                'tcpa_min': 42.0,   # Time to catch up
                'risk_level': 'caution'
            }
        )
    
    @staticmethod
    def safe_passing_scenario():
        """
        Safe passing situation
        Target passing at safe distance
        """
        own_ship = ScenarioTarget(
            name="Own Ship",
            lat=37.0,
            lon=-76.3,
            course=90,  # Heading East
            speed=10
        )
        
        target = ScenarioTarget(
            name="Passing Target",
            lat=37.1,    # 6 NM north
            lon=-76.35,  # Slightly west
            course=90,   # Same heading
            speed=12     # Slightly faster
        )
        
        return TestScenario(
            name="Safe Passing",
            description="Target passing at safe distance",
            own_ship=own_ship,
            targets=[target],
            expected_results={
                'cpa_nm': 6.0,      # Maintains 6 NM separation
                'tcpa_min': float('inf'),  # No CPA event
                'risk_level': 'safe'
            }
        )
    
    @staticmethod
    def multiple_targets_scenario():
        """
        Multiple targets requiring prioritization
        """
        own_ship = ScenarioTarget(
            name="Own Ship",
            lat=37.0,
            lon=-76.3,
            course=0,   # Heading North
            speed=10
        )
        
        # Critical target - head on
        target1 = ScenarioTarget(
            name="Critical Target",
            lat=37.05,
            lon=-76.3,
            course=180,
            speed=15
        )
        
        # Warning target - crossing
        target2 = ScenarioTarget(
            name="Warning Target",
            lat=37.03,
            lon=-76.32,
            course=90,
            speed=12
        )
        
        # Safe target - passing
        target3 = ScenarioTarget(
            name="Safe Target",
            lat=37.1,
            lon=-76.2,
            course=0,
            speed=8
        )
        
        return TestScenario(
            name="Multiple Targets",
            description="Multiple targets requiring threat prioritization",
            own_ship=own_ship,
            targets=[target1, target2, target3],
            expected_results={
                'highest_threat': 'Critical Target',
                'threat_count': 2
            }
        )
    
    @staticmethod
    def get_all_scenarios():
        """Get all test scenarios"""
        return [
            RadarTestScenarios.crossing_scenario(),
            RadarTestScenarios.head_on_scenario(),
            RadarTestScenarios.overtaking_scenario(),
            RadarTestScenarios.safe_passing_scenario(),
            RadarTestScenarios.multiple_targets_scenario()
        ]


class ScenarioRunner:
    """Run test scenarios and validate results"""
    
    def __init__(self, cpa_calculator):
        """
        Initialize scenario runner
        
        Args:
            cpa_calculator: CPA calculator instance
        """
        self.cpa_calculator = cpa_calculator
        self.results = []
        
    def run_scenario(self, scenario):
        """
        Run a test scenario
        
        Returns:
            dict with results
        """
        results = {
            'scenario_name': scenario.name,
            'targets': []
        }
        
        # Convert scenario targets to format expected by calculator
        own_ship = {
            'lat': scenario.own_ship.lat,
            'lon': scenario.own_ship.lon,
            'course': scenario.own_ship.course,
            'speed': scenario.own_ship.speed
        }
        
        for target in scenario.targets:
            target_data = {
                'lat': target.lat,
                'lon': target.lon,
                'course': target.course,
                'speed': target.speed
            }
            
            # Calculate CPA/TCPA
            cpa_result = self.cpa_calculator.calculate(own_ship, target_data)
            
            # Assess risk
            risk_level = self.cpa_calculator.assess_collision_risk(cpa_result)
            
            results['targets'].append({
                'name': target.name,
                'cpa_nm': cpa_result.cpa_distance,
                'tcpa_min': cpa_result.tcpa_minutes,
                'risk_level': risk_level,
                'bearing_at_cpa': cpa_result.bearing_at_cpa,
                'current_range': cpa_result.range_at_cpa
            })
            
        self.results.append(results)
        return results
        
    def validate_scenario(self, scenario):
        """
        Run scenario and validate against expected results
        
        Returns:
            tuple (passed, results, errors)
        """
        results = self.run_scenario(scenario)
        errors = []
        
        expected = scenario.expected_results
        
        # Validate results
        if 'cpa_nm' in expected:
            actual_cpa = results['targets'][0]['cpa_nm']
            expected_cpa = expected['cpa_nm']
            
            # Allow 20% tolerance
            tolerance = expected_cpa * 0.2
            if abs(actual_cpa - expected_cpa) > tolerance:
                errors.append(
                    f"CPA mismatch: expected {expected_cpa:.2f}, got {actual_cpa:.2f}"
                )
                
        if 'tcpa_min' in expected:
            actual_tcpa = results['targets'][0]['tcpa_min']
            expected_tcpa = expected['tcpa_min']
            
            # Special handling for infinity
            if math.isinf(expected_tcpa) and not math.isinf(actual_tcpa):
                errors.append(
                    f"TCPA mismatch: expected infinite, got {actual_tcpa:.2f}"
                )
            elif not math.isinf(expected_tcpa):
                tolerance = expected_tcpa * 0.2
                if abs(actual_tcpa - expected_tcpa) > tolerance:
                    errors.append(
                        f"TCPA mismatch: expected {expected_tcpa:.2f}, got {actual_tcpa:.2f}"
                    )
                    
        passed = len(errors) == 0
        
        return passed, results, errors
        
    def run_all_scenarios(self):
        """Run all test scenarios"""
        scenarios = RadarTestScenarios.get_all_scenarios()
        
        all_passed = True
        summary = []
        
        for scenario in scenarios:
            passed, results, errors = self.validate_scenario(scenario)
            
            summary.append({
                'name': scenario.name,
                'passed': passed,
                'errors': errors,
                'results': results
            })
            
            if not passed:
                all_passed = False
                
        return all_passed, summary
        
    def print_summary(self, summary):
        """Print test summary"""
        logger.info("=" * 60)
        logger.info("Test Scenario Results")
        logger.info("=" * 60)

        for test in summary:
            status = "PASS" if test['passed'] else "FAIL"
            logger.info("%s: %s", test['name'], status)

            if not test['passed']:
                logger.info("  Errors:")
                for error in test['errors']:
                    logger.info("    - %s", error)

            logger.info("  Results:")
            for target in test['results']['targets']:
                logger.info("    %s:", target['name'])
                logger.info("      CPA: %.2f NM", target['cpa_nm'])
                logger.info("      TCPA: %.2f min", target['tcpa_min'])
                logger.info("      Risk: %s", target['risk_level'])

        logger.info("=" * 60)
