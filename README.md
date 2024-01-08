# Solar Lighting Integration

This is yet another integration which changes lights over time.

See also

- [flux](https://www.home-assistant.io/integrations/flux/), builtin to HA
- [circadian lighting](https://github.com/claytonjn/hass-circadian_lighting) custom component
- [adaptive lighting](https://github.com/basnijholt/adaptive-lighting) custom component

I've borrowed code / inspiration from the last two liberally. They're very good but don't do what I want and are too complicated for me to edit.

# Why?

I use zigbee groups to control sets of lights at once, but also want to control them independently.

The other integrations cannot be told to control groups and their members, as they will turn lights in the group on if any group member is on.

This means sending lots of simultaneous zigbee messages when the brightness / temperature changes, which doesn't work well in my network. Sometimes lights miss their message, or they change visibly out of sync.

My integration is aware of zigbee groups, and uses this to send as few zigbee messages as possible. If every member of a group is on and being controlled, messages will go to the group. Turn on commands to the group can also be rewritten.

# Config

``` yaml
- switch:
    - platform: solar_lighting
      update_interval: 60 # seconds, or other time formats allowed
      brightness_update_delta: 2 # when brightness out by this much update the light
      brightness_adjust: true # whether to control brightness
      brightness_min: 25 # min brightness
      brightness_max: 255 # max brightness
      brightness_k: 30 # rate at which brightness changes around dawn/dusk
      brightness_x: 0.0 # positive values move transition into the day, negative into the night.

      temperature_update_delta: 100 # when temperature (K) out by this much update
      temperature_adjust: true
      temperature_min: 2200 # kelvin
      temperature_max: 4000
      temperature_k: 22.0 # like the brightness parameters
      temperature_x: 0.04

      sleep: true # create a sleep mode switch
      sleep_brightness: 25
      sleep_temperature: 2200

      # transition when updating brightness
      transition: 2

      # lights to use
      lights:
        - light.some_light # a light
        - entity_id: light.some_group # a zigbee group
          group: light.x, light.y, light.z # members of group
        - entity_id: light.q
          temperature_min: 3000 # special min temperature for this light
```

All the toplevel parameters except `sleep` and `update_interval` can be overridden by putting them within a light, like `light.q` in the example.

# Behaviour

- Lights are updated every `update_interval`; if the target brightness / temperature is more than one of the `_delta` parameters out of sync then we will try and update the light.
- When updating, the target state of all lights is computed; if every light in a group has the same target state, the group is controlled instead of its lights
  - If one group contains another, the largest controllable group is used
  - Partially overlapping groups, you're on your own
- If you change the brightness of temperature of a light manually, that attribute of the light is not controlled until you turn it off and on again, or turn the solar lighting switch off and on again.
- When service `light.turn_on` is called on controlled lights, if the service call sets brightness or temperature the light is manually controlled.
  Otherwise, the service call is rewritten to include brightness and temperature.
  
  This only works for simple cases.
- I assume all lights have the IKEA tradfri transition temperature / brightness bug (can't change them simultaneously), because all my lights do; so a light update will first update temperature then brightness.
  
# TODO

- Factor out the zigbee stuff into an automatic zigbee group optimiser
- Factor out the ikea brightness hack to wrangle all calls to tradfri bulbs
- Autodetect zigbee groups' members somehow
