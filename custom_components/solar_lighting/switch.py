# TODO monkeypatch turn on / toggle.

import asyncio
import voluptuous as vol
import datetime
import homeassistant.helpers.config_validation as cv
import homeassistant.util.dt as dt_util
from homeassistant.helpers.sun import get_astral_location
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.util import slugify
from homeassistant.util.color import color_temperature_kelvin_to_mired

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_RGB_COLOR,
    ATTR_TRANSITION,
    ATTR_XY_COLOR,
)

from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_NAME,
    CONF_PLATFORM,
    SERVICE_TURN_ON,
    STATE_ON,
)

from . import DOMAIN

brightness = vol.All( vol.Coerce(int), vol.Range(min=1, max=100) )
colour_temp = vol.All( vol.Coerce(int), vol.Range(min=1000, max=10000) )

settings_schema = vol.Schema({
    vol.Optional("intercept_turn_on", default=True): cv.boolean,
    vol.Optional("update_delta", default=2): cv.positive_int,
    vol.Optional("brightness_adjust", default = True): cv.boolean,
    vol.Optional("brightness_min", default=5): brightness,
    vol.Optional("brightness_max", default=100): brightness,
    vol.Optional("temperature_adjust", default = True): cv.boolean,
    vol.Optional("temperature_min", default = 2500): colour_temp,
    vol.Optional("temperature_max", default = 5500): colour_temp,
    vol.Optional("brightness_k", default = 1.0): float,
    vol.Optional("brightness_x", default = 0.0): float,
    vol.Optional("temperature_k", default = 0.5): float,
    vol.Optional("temperature_x", default = 0.5): float,
    vol.Optional("sleep_brightness", default = 5): brightness,
    vol.Optional("sleep_temperature", default = 2000): colour_temp,
    vol.Optional("transition", default = 2): cv.positive_int
})

PLATFORM_SCHEMA = vol.All(
    vol.Schema({
        vol.Required(CONF_PLATFORM): "solar_lighting",
        vol.Optional(CONF_NAME, default="Solar Lighting"): cv.string,
        vol.Optional("update_interval", default = datetime.timedelta(minutes = 1)): cv.positive_time_period,
        vol.Optional("lights"): vol.Schema([
            vol.Any(
                # bare entity id or entity with settings on it
                cv.entity_id,
                vol.All(
                    vol.Schema({vol.Required(ATTR_ENTITY_ID): cv.entity_id,
                                vol.Optional("group"): cv.entity_ids}),
                    settings_schema
                )
            )
        ])
    }),
    settings_schema # toplevel global settings
)

def setup_platform(hass, config, add_devices, discovery_info = None):
    main_switch = MainSwitch(hass, config)
    sleep_switch = SleepSwitch(hass, config, main_switch)
    add_devices( [ main_switch, sleep_switch ] )
    return True

class MainSwitch(SwitchEntity, RestoreEntity):
    def __init__(self, hass, config):
        self.hass = hass
        self._name = config.get("name")
        self._entity_id = f"switch.solar_lighting_{slugify(self._name)}"
        self._sleep_mode = None
        self._state = None
        self._lights = []
        self._groups = []
        self._update_interval = config.get("update_interval")
        self._expected_brightness = {}
        self._expected_temperature = {}
        
        self._manual_brightness = set()
        self._manual_temperature = set()
        self._sleep_brightness = config.get("sleep_brightness")
        self._sleep_temperature = color_temperature_kelvin_to_mired(config.get("sleep_temperature"))
        
        for light in config.get("lights", []):
            if isinstance(light, str):
                light = {**config, ATTR_ENTITY_ID: light}
            else:
                light = {**config, **light}
            if light.get("group"):
                self._groups.append(light)
            else:
                self._lights.append(light)

    @property
    def icon(self):
        return "mdi:theme-light-dark"
        
    @property
    def entity_id(self):
        return self._entity_id

    @property
    def name(self):
        return self._name

    @property
    def is_on(self):
        return self._state

    async def update_lights(self):
        if not(self._state) return
        sunrise, noon, sunset, now = get_times(self.hass)

        target_state = {}
        needs_update = set()

        for light in self._lights:
            entity_id = light.get(ATTR_ENTITY_ID)
            state = self.hass.states.get(entity_id)

            if state and state.state == STATE_ON:
                tmax = color_temperature_kelvin_to_mired(light.get("temperature_max"))
                tmin = color_temperature_kelvin_to_mired(light.get("temperature_min"))
                tp = 100 / (tmax - tmin)
                
                update = {}
                cur_brightness = state.attributes.get(ATTR_BRIGHTNESS)
                cur_temperature = state.attributes.get(ATTR_COLOR_TEMP)
                
                ex_brightness = self._expected_brightness.get(entity_id, cur_brightness)
                ex_temperature = self._expected_temperature.get(entity_id, cur_temperature)
                
                delta = light.get("update_delta")

                if abs(ex_brightness - cur_brightness) > delta:
                    self._manual_brightness.add(entity_id)
                if abs(ex_temperature - cur_temperature) * tp > delta:
                    self._manual_temperature.add(entity_id)
                
                if entity_id not in self._manual_brightness and \
                   light.get("brightness_adjust"):
                    if self._sleep_mode:
                        brightness = self.sleep_brightness
                    else:
                        brightness = evaluate_curve(now, sunrise, noon, sunset,
                                                    light.get("brightness_k"),
                                                    light.get("brightness_x"),
                                                    light.get("brightness_min"),
                                                    light.get("brightness_max"))
                    update[ATTR_BRIGHTNESS] = brightness
                    cur = state.attributes.get(ATTR_BRIGHTNESS, None)
                    if not(cur) or abs(cur - brightness) > delta:
                        needs_update.add(entity_id)

                if entity_id not in self._manual_temperature and \
                   light.get("temperature_adjust"):
                    if self._sleep_mode:
                        temperature = self._sleep_temperature
                    else:
                        temperature = evaluate_curve(now, sunrise, noon, sunset,
                                                     light.get("temperature_k"),
                                                     light.get("temperature_x"),
                                                     tmin, tmax)
                    update[ATTR_COLOR_TEMP] = temperature
                    cur = state.attributes.get(ATTR_COLOR_TEMP, None)
                    if not(cur) or abs(cur - temperature) * tp > delta:
                        needs_update.add(entity_id)

                if entity_id in needs_update:
                    update[ATTR_TRANSITION] = light.get("transition", 0)
                    target_state[light] = update
            else:
                self._manual_brightness.discard(entity_id)
                self._manual_temperature.discard(entity_id)
                self._expected_brightness.pop(entity_id, None)
                self._expected_temperature.pop(entity_id, None)

        # Process groups. Nested groups are not handled.
        for group in self._groups:
            members = group.get("group")
            member_needs_update = False
            for e in members:
                if e in needs_update:
                    member_needs_update = True
                    break

            if member_needs_update:
                targets = [target_state.get(e, None) for e in members]
                if all_equal(targets):
                    # remove from target_state
                    for e in members:
                        target_state.pop(e, None)
                    if targets[0]:
                        target_state[group.get(ATTR_ENTITY_ID)] = targets[0]

        # OK, target_state now contains groups as well
        # so we can issue our update commands, and then set expectations
        turn_ons = []
        for (entity_id, state) in target_state.items():
            state[ATTR_ENTITY_ID] = entity_id

            turn_ons.append(
                self.hass.async_create_task(
                    self.hass.services.async_call(
                        LIGHT_DOMAIN, SERVICE_TURN_ON, state
                    )
                )
            )
            if ATTR_BRIGHTNESS in state:
                self._expected_brightness[entity_id] = state[ATTR_BRIGHTNESS]
            if ATTR_COLOR_TEMP in state:
                self._expected_temperature[entity_id] = state[ATTR_COLOR_TEMP]
        if turn_ons:
            await asyncio.wait(turn_ons)

    async def async_added_to_hass(self):
        self.async_on_remove(
            async_track_time_interval(self.hass, self.update_lights, self._update_interval)
        )
        
        if self._state is not None: return
        state = await self.async_get_last_state()
        self._state = state and state.state == STATE_ON
    
    async def async_set_sleep_mode(self, sleep_mode):
        if self._sleep_mode != sleep_mode:
            self._sleep_mode = sleep_mode
            self.clear_overrides_and_expectations()
            await self.update_lights()

    def clear_overrides_and_expectations():
        self._expected_temperature = {}
        self._expected_brightness = {}
        self._manual_temperature = set()
        self._manual_brightness = set()
            
    async def async_turn_on(self, **kwargs):
        self._state = True
        self.clear_overrides_and_expectations()
        await self.update_lights()

    async def async_turn_off(self, **kwargs):
        self._state = False
        self.clear_overrides_and_expectations()
        
class SleepSwitch(SwitchEntity, RestoreEntity):
    # an auxiliary switch which really just pokes the main switch in the brain
    def __init__(self, hass, config, main_switch):
        self.hass = hass
        self._main_switch = main_switch
        self._name = main_switch.name + " Sleep"
        self._entity_id = main_switch.entity_id + "_sleep"
        self._state = None

    @property
    def icon(self):
        return "mdi:theme-light-dark"
        
    @property
    def entity_id(self):
        return self._entity_id

    @property
    def name(self):
        return self._name

    @property
    def is_on(self):
        return self._state

    async def async_added_to_hass(self):
        if self._state is not None: return
        state = await self.async_get_last_state()
        self._state = state and state.state == STATE_ON
        await self._main_switch.async_set_sleep_mode(self._state)

    async def async_turn_on(self, **kwargs):
        self._state = True
        await self._main_switch.async_set_sleep_mode(self._state)

    async def async_turn_off(self, **kwargs):
        self._state = False
        await self._main_switch.async_set_sleep_mode(self._state)

def get_times(hass):
    now = dt_util.utcnow() #await self.hass.async_add_executor_job(dt_util.utcnow)
    loc, _ = get_astral_location(hass)
    today = now.replace(hour = 0, minute = 0, second = 0)
    sunrise = loc.sunrise(today)
    sunset = loc.sunset(today)
    noon = loc.solar_noon(today)

    sunrise = (sunrise.hour + sunrise.minute / 60) / 24
    sunset = (sunset.hour + sunset.minute / 60) / 24
    noon = (noon.hour + noon.minute / 60) / 24
    now = (now.hour + now.minute / 60) / 24

    return (sunrise, noon, sunset, now)

def evaluate_curve(now, sunrise, noon, sunset, k, x, minimum, maximum):
    if now < noon:
        x = (1+tanh(k*(now - (sunrise + x))))/2
    else:
        x = (1+tanh(k*(sunset - (now + x))))/2
    return minimum + (maximum - minimum) * x

def all_equal(xs):
    if xs:
        x0 = xs[0]
        for x in xs:
            if x != x0: return False
    return True
