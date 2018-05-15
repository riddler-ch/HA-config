"""
Support for Worx Landroid mower, based on https://home-assistant.io/components/sensor.worxlandroid/
"""
import logging
import asyncio

import aiohttp
import async_timeout

import voluptuous as vol

import homeassistant.helpers.config_validation as cv

from homeassistant.helpers.entity import Entity
from homeassistant.components.switch import (PLATFORM_SCHEMA)
from homeassistant.const import (CONF_HOST, CONF_PIN, CONF_TIMEOUT)
from homeassistant.helpers.aiohttp_client import (async_get_clientsession)

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'sensor'

DEFAULT_NAME = 'Worx Landroid'

CONF_ALLOW_UNREACHABLE = 'allow_unreachable'

DEFAULT_TIMEOUT = 5

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_PIN):
        vol.All(vol.Coerce(int), vol.Range(min=0000, max=9999)),
    vol.Optional(CONF_ALLOW_UNREACHABLE, default=True): cv.boolean,
    vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): cv.positive_int,
})

ERROR_STATE = [
    'blade-blocked',
    'repositioning-error',
    'wire-bounced',
    'blade-blocked',
    'outside-wire',
    'mower-lifted',
    'alarm-6',
    'upside-down',
    'alarm-8',
    'collision-sensor-blocked',
    'mower-tilted',
    'charge-error',
    'battery-error'
]


@asyncio.coroutine
def async_setup_platform(hass, config, async_add_devices,
                         discovery_info=None):
    """Set up the Worx Landroid sensors."""
    for typ in ('battery_percentage', 'battery_voltage', 'state', 'rain'):
        async_add_devices([WorxLandroidSensor(typ, config)])


class WorxLandroidSensor(Entity):
    """Implementation of a Worx Landroid sensor."""

    def __init__(self, sensor, config):
        """Initialize a Worx Landroid sensor."""
        self._state = None
        self.sensor = sensor
        self.host = config.get(CONF_HOST)
        self.pin = config.get(CONF_PIN)
        self.timeout = config.get(CONF_TIMEOUT)
        self.allow_unreachable = config.get(CONF_ALLOW_UNREACHABLE)
        self.url = 'http://{}/jsonDebug.cgi'.format(self.host)

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'worxlandroid-{}'.format(self.sensor)

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of the sensor."""
        if self.sensor == 'battery_percentage':
            return '%'
        elif self.sensor == 'battery_voltage':
            return 'V'
        return None

    @asyncio.coroutine
    def async_update(self):
        """Update the sensor data from the mower."""
        connection_error = False

        try:
            session = async_get_clientsession(self.hass)
            with async_timeout.timeout(self.timeout, loop=self.hass.loop):
                auth = aiohttp.helpers.BasicAuth('admin', self.pin)
                mower_response = yield from session.get(self.url, auth=auth)
        except (asyncio.TimeoutError, aiohttp.ClientError):
            if self.allow_unreachable is False:
                _LOGGER.error("Error connecting to mower at %s", self.url)

            connection_error = True

        # connection error
        if connection_error is True and self.allow_unreachable is False:
            if self.sensor == 'error':
                self._state = 'yes'
            elif self.sensor == 'state':
                self._state = 'connection-error'

        # connection success
        elif connection_error is False:
            # set the expected content type to be text/html
            # since the mover incorrectly returns it...
            data = yield from mower_response.json(content_type='text/html')

            # sensor battery percentage
            if self.sensor == 'battery_percentage':
                self._state = data['landroid']['battery']['percentage']

            # sensor battery voltage
            if self.sensor == 'battery_voltage':
                self._state = data['landroid']['battery']['voltage']

            # rain
            if self.sensor == 'rain':
                self._state = data['landroid']['rainSensor']

            # sensor error
            elif self.sensor == 'error':
                self._state = 'no' if self.get_error(data) is None else 'yes'

            # sensor state
            elif self.sensor == 'state':
                self._state = data['landroid']['state']

        else:
            if self.sensor == 'error':
                self._state = 'no'

