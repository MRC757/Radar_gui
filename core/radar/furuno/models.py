"""
Furuno radar sensor models supported by the Furuno Sensor SDK.

Model list taken from Furuno's public Sensor SDK pages
(furuno.com/en/support/sdk, furunousa.com/en/sdk).

!! VERIFY every value below against the SDK documentation or, better, the
!! SDK's own capability query once you have it.  Max ranges come from
!! Furuno product literature; spoke/sample counts and ARPA limits are
!! placeholders until confirmed from the SDK header / manual.
"""

from __future__ import annotations

from ..types import RadarCapabilities

# Furuno-style range ladder (NM).  Each model uses the entries up to its max.
_FURUNO_RANGE_LADDER = [
    0.0625, 0.125, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0,
    12.0, 16.0, 24.0, 32.0, 36.0, 48.0, 64.0, 72.0, 96.0,
]


def _ranges_up_to(max_nm: float):
    return [r for r in _FURUNO_RANGE_LADDER if r <= max_nm]


# model -> (max range NM, has Doppler "Target Analyzer", description)
_MODEL_TABLE = {
    'DRS2D-NXT':  (24.0, True,  'Solid-state radome (25 W)'),
    'DRS4D-NXT':  (36.0, True,  'Solid-state radome (25 W)'),
    'DRS6A-NXT':  (72.0, True,  'Solid-state X-band open array'),
    'DRS12A-NXT': (96.0, True,  'Solid-state X-band open array'),
    'DRS25A-NXT': (96.0, True,  'Solid-state X-band open array'),
    'DRS4DL+':    (36.0, False, 'Radome (discontinued)'),
    'FAR3230':    (96.0, False, 'Commercial S-band radar'),
}

SUPPORTED_MODELS = list(_MODEL_TABLE.keys())


def capabilities_for(model: str) -> RadarCapabilities:
    """Default capabilities for a Furuno model (see VERIFY note above)."""
    max_nm, doppler, _desc = _MODEL_TABLE.get(model, (36.0, False, ''))
    return RadarCapabilities(
        model=f'Furuno {model}',
        ranges_nm=_ranges_up_to(max_nm),
        spokes_per_revolution=2048,      # VERIFY from SDK
        max_samples_per_spoke=1024,      # VERIFY from SDK
        gain_range=(0, 100),             # VERIFY: SDK may use 0-255 or similar
        supports_auto_gain=True,
        supports_auto_sea=True,
        supports_auto_rain=True,
        supports_interference_rejection=True,
        supports_target_expansion=True,
        supports_arpa=True,
        max_arpa_targets=100,            # VERIFY from SDK
        supports_doppler=doppler,
        supports_blind_sectors=True,     # listed for FAR3230; VERIFY for DRS
        requires_heading_input=True,     # ARPA needs heading
        requires_position_input=False,
        extra_controls=['heave_correction', 'split_range'] if model != 'DRS4DL+' else [],
    )
