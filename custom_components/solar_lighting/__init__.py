"""
Solar lighting component for HA

Borrowed details from Circadian Lighting and Adaptive Lighting.

Reason for existence is

- Circadian lighting doesn't monkey-patch on/off or have take-over control
- Adaptive lighting is unreliable for me and I don't want to debug it
- I want take over control for brightness but not colour
- I want to be able to adapt some switches only when switched on, and some over time
  without setting up lots of identical configurations
"""
DOMAIN = "solar_lighting"

async def async_setup(hass, config) -> bool:
    return True
