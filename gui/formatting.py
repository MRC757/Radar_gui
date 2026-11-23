"""
Display formatting for values that may be unavailable.

AIS can report SOG/COG as "not available", and CPA/TCPA are not computed for
such targets, so these values can be None.  A missing value is shown as
'---' (never as 0, which would look like a real reading).
"""

import math

NA = '---'


def fmt(value, spec='.1f', suffix='', na=NA):
    """Format a number, or return `na` if it is None / NaN / infinite."""
    if value is None:
        return na
    try:
        if math.isnan(value) or math.isinf(value):
            return na
    except TypeError:
        return na
    return f"{value:{spec}}{suffix}"


def fmt_course(track, spec='05.1f', suffix='°'):
    if not track.get('course_valid', track.get('course') is not None):
        return NA
    return fmt(track.get('course'), spec, suffix)


def fmt_speed(track, spec='.1f', suffix=' kts'):
    if not track.get('speed_valid', track.get('speed') is not None):
        return NA
    return fmt(track.get('speed'), spec, suffix)


def fmt_tcpa(tcpa, suffix=' min'):
    """TCPA: negative means the CPA has already passed."""
    if tcpa is None or (isinstance(tcpa, float) and (math.isnan(tcpa) or math.isinf(tcpa))):
        return NA
    if tcpa < 0:
        return f"passed {abs(tcpa):.1f}{suffix} ago"
    return f"{tcpa:.1f}{suffix}"
