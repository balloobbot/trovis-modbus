"""The top-level Trovis557x device object."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from modbus_connection import ModbusConnectionError, ModbusError, ModbusTimeoutError
from modbus_connection.model import Component

from .addresses import register_address
from .configurations.address_ranges import (
    control_circuit_count,
    ranges_for_model,
)
from .configurations.hydronic_systems import (
    ConfigurationDefinition,
    ConfigurationTopology,
    get_configuration_definition,
)
from .configurations.sensor_variants import (
    SensorVariantResolution,
    SensorVariantStatus,
    resolve_sensor_variants,
)
from .configurations.settings import Functions, Parameters
from .configurations.trovis_models import get_model_definition_for_reported_model
from .data_model import (
    DEFAULT_WRITE_ACCESS_CODE,
    async_disable_writing,
    async_enable_writing,
    async_read_writing_enabled,
)
from .device_info import DeviceInformation
from .enums import (
    ControlCircuitRole,
    HeatingCircuitControlMode,
    SystemActivity,
)
from .subsystems import (
    BufferTankCircuit,
    Clock,
    Controller,
    DomesticHotWater,
    HeatingCircuit,
    Sensors,
    SolarCircuit,
)

if TYPE_CHECKING:
    from modbus_connection import ModbusUnit

# What the controller measures and controls, in read order.
_READINGS = (
    "info",
    "controller",
    "clock",
    "sensors",
    "rk1",
    "rk2",
    "rk3",
    "rk4",
    "buffer_tank",
    "solar",
)

# What the controller was configured with: the CO/F selectors and the PA values
# the library interprets the rest with. They change when someone reconfigures
# the controller, not on their own.
_SETTINGS = ("functions", "parameters")

# Rk slots the model may not have; the rest are polled on every model.
_CIRCUIT_SLOTS = ("rk1", "rk2", "rk3")


@dataclass(frozen=True)
class UpdateReport:
    """What one poll refreshed, by the device's subsystem attribute names.

    A failed subsystem kept its previous values and did not notify; the error
    that failed it rides along. A dead link is never in here — the update
    raises ``ModbusConnectionError`` instead of reporting partial silence. A
    report names only what the method it came from polls.
    """

    updated: set[str]
    failed: dict[str, ModbusError]

    @property
    def complete(self) -> bool:
        """Whether every polled subsystem refreshed."""
        return not self.failed


@dataclass(frozen=True)
class TrovisProbe:
    """Result of the safe setup probe."""

    model: int
    detected_sensors: tuple[str, ...]

    @property
    def model_name(self) -> str:
        """Return the user-facing model name."""
        return f"Trovis {self.model}"


class Trovis557x:
    """A Samson TROVIS 557x heating controller."""

    def __init__(
        self,
        unit: ModbusUnit,
        *,
        model: int = 5578,
        detected_sensors: Iterable[str] = (),
    ) -> None:
        self._unit = unit
        self.model = model
        self.model_definition = get_model_definition_for_reported_model(model)

        # Probe results may contain several descriptor views of the same raw
        # register. Keep only logical sensor keys supported by this model. This
        # also sanitizes existing config entries created before ModelDefinition
        # became the authoritative model filter.
        self.probed_sensors = frozenset(detected_sensors)
        self.detected_sensors = frozenset(
            sensor_key
            for sensor_key in self.probed_sensors
            if self.model_definition.supports_sensor(sensor_key)
        )
        self.unsupported_detected_sensors = self.probed_sensors - self.detected_sensors

        self.info = DeviceInformation(unit)
        self.controller = Controller(unit)
        self.clock = Clock(unit)
        self.functions = Functions(unit)
        self.parameters = Parameters(unit)
        self.sensors = Sensors(unit)

        self.rk1 = HeatingCircuit(unit, index=1)
        self.rk2 = HeatingCircuit(unit, index=2)
        self.rk3 = HeatingCircuit(unit, index=3)

        self.rk4 = DomesticHotWater(unit)
        self.buffer_tank = BufferTankCircuit(unit)
        self.solar = SolarCircuit(unit)
        self._writing_enabled = False

        all_components = (
            self.info,
            self.controller,
            self.clock,
            self.functions,
            self.parameters,
            self.sensors,
            self.rk1,
            self.rk2,
            self.rk3,
            self.rk4,
            self.buffer_tank,
            self.solar,
        )

        register_ranges, coil_ranges = ranges_for_model(model)
        for component in all_components:
            component.configure_readable_ranges(register_ranges, coil_ranges)

        # Ranges describe address availability. ModelDefinition additionally
        # limits logical sensor views that may share one readable register.
        self.sensors.configure_readable_fields(self.model_definition.sensor_keys)

        circuit_count = control_circuit_count(model)
        self._control_circuits = (
            self.rk1,
            self.rk2,
            self.rk3,
        )[:circuit_count]

        absent = frozenset(_CIRCUIT_SLOTS[circuit_count:])
        self._readings = [name for name in _READINGS if name not in absent]
        self._settings = list(_SETTINGS)
        self._polled = [*self._readings, *self._settings]

    @classmethod
    async def async_probe(cls, unit: ModbusUnit) -> TrovisProbe:
        """Read only safe identity and sensor data for setup."""
        model = int(
            (
                await unit.read_holding_registers(
                    register_address(40001),
                    1,
                )
            )[0]
        )

        register_ranges, coil_ranges = ranges_for_model(model)
        model_definition = get_model_definition_for_reported_model(model)

        sensors = Sensors(unit)
        sensors.configure_readable_ranges(register_ranges, coil_ranges)
        sensors.configure_readable_fields(model_definition.sensor_keys)
        await sensors.async_update()

        detected_sensors = tuple(
            sensor_key
            for sensor_key in sensors.detected_sensor_names
            if model_definition.supports_sensor(sensor_key)
        )

        return TrovisProbe(
            model=model,
            detected_sensors=detected_sensors,
        )

    @property
    def control_circuits(self) -> tuple[HeatingCircuit, ...]:
        """Return the built-in Rk1-Rk3 control circuits for this model."""
        return self._control_circuits

    @property
    def configuration_definition(self) -> ConfigurationDefinition | None:
        """Return the known hydronic definition reported by the controller."""
        system_code = self.info.system_code
        if system_code is None:
            return None

        try:
            return get_configuration_definition(round(system_code * 10))
        except KeyError:
            return None

    @property
    def configuration_topology(self) -> ConfigurationTopology | None:
        """Return the known hydronic topology reported by the controller."""
        definition = self.configuration_definition
        return definition.topology if definition is not None else None

    @property
    def configuration_supported_by_model(self) -> bool | None:
        """Return whether the reported system code is documented for this model."""
        definition = self.configuration_definition
        if definition is None:
            return None
        return definition.supports_model(self.model_definition.model)

    def control_circuit_role(self, index: int) -> ControlCircuitRole:
        """Return the role of technical slot Rk1 through Rk4."""
        if not 1 <= index <= 4:
            raise ValueError("control circuit index must be in range 1..4")

        if index <= 3 and index > len(self._control_circuits):
            return ControlCircuitRole.UNUSED

        topology = self.configuration_topology
        if topology is not None:
            return topology.control_circuit_role(index)

        if index <= len(self._control_circuits):
            return ControlCircuitRole.HEATING
        if index == 4:
            return ControlCircuitRole.DOMESTIC_HOT_WATER
        return ControlCircuitRole.UNUSED

    @property
    def control_circuit_indices(self) -> tuple[int, ...]:
        """Return technical Rk slots enabled by model and hydronic topology."""
        return tuple(
            index
            for index in range(1, 5)
            if self.control_circuit_role(index) is not ControlCircuitRole.UNUSED
        )

    @property
    def room_heating_circuit_indices(self) -> tuple[int, ...]:
        """Return Rk1-Rk3 slots whose hydronic role is room heating."""
        return tuple(
            index
            for index in range(1, len(self._control_circuits) + 1)
            if self.control_circuit_role(index) is ControlCircuitRole.HEATING
        )

    def heating_circuit_uses_outdoor_sensor(self, index: int) -> bool | None:
        """Return whether one active Rk1-Rk3 slot uses weather compensation.

        ``True`` means COx -> F02 is active and the heating-curve parameters
        apply. ``False`` means fixed set point control. ``None`` keeps callers
        conservative if the selector is unavailable or not readable.
        """
        if not 1 <= index <= len(self._control_circuits):
            raise ValueError(f"Rk{index} is not available on this controller")
        return self.functions.heating_circuit_uses_outdoor_sensor(index)

    def heating_circuit_uses_four_point_characteristic(
        self,
        index: int,
    ) -> bool | None:
        """Return whether one active Rk1-Rk3 slot uses a four-point curve.

        The selector is relevant only when COx -> F02 enables weather
        compensation. ``False`` selects the gradient characteristic, ``True``
        selects the four-point characteristic and ``None`` keeps callers on
        the established gradient-characteristic fallback.
        """
        if not 1 <= index <= len(self._control_circuits):
            raise ValueError(f"Rk{index} is not available on this controller")
        return self.functions.heating_circuit_uses_four_point_characteristic(index)

    def heating_circuit_operating_mode(
        self,
        index: int,
    ) -> HeatingCircuitControlMode | None:
        """Return the active setpoint-generation mode for one heating circuit.

        COx -> F02 disables weather compensation and selects fixed set point
        control. With weather compensation active, COx -> F11 selects the
        four-point characteristic; an unavailable F11 selector retains the
        established gradient-characteristic fallback.
        """
        uses_outdoor_sensor = self.heating_circuit_uses_outdoor_sensor(index)
        if uses_outdoor_sensor is None:
            return None
        if not uses_outdoor_sensor:
            return HeatingCircuitControlMode.FIXED_SETPOINT
        if self.heating_circuit_uses_four_point_characteristic(index) is True:
            return HeatingCircuitControlMode.FOUR_POINT
        return HeatingCircuitControlMode.HEATING_CURVE

    @property
    def has_rk4(self) -> bool:
        """Return whether Rk4/WW is present or retained as safe fallback."""
        return self.control_circuit_role(4) is ControlCircuitRole.DOMESTIC_HOT_WATER

    @property
    def has_buffer_tank_circuit(self) -> bool:
        """Return whether Rk1 is assigned the buffer-tank circuit role."""
        return self.control_circuit_role(1) is ControlCircuitRole.BUFFER_TANK

    @property
    def has_buffer_tank_charging_parameters(self) -> bool:
        """Return whether PA1 P16-P19 apply to this model/system pair."""
        definition = self.configuration_definition
        if definition is None or not self.has_buffer_tank_circuit:
            return False
        return definition.supports_buffer_tank_charging_parameters(
            self.model_definition.model
        )

    @property
    def has_solar(self) -> bool:
        """Return whether the selected hydronic system contains a solar circuit."""
        topology = self.configuration_topology
        return topology.solar if topology is not None else False

    @property
    def components(self) -> tuple[Component, ...]:
        """Return every actively polled subsystem."""
        return tuple(getattr(self, name) for name in self._polled)

    @property
    def sensor_variant_resolution(self) -> SensorVariantResolution:
        """Return the current configuration-only sensor-variant diagnosis."""
        return resolve_sensor_variants(
            self.model_definition,
            self.functions,
            self.parameters,
        )

    @property
    def canonical_sensor_keys(self) -> frozenset[str]:
        """Return model-supported sensor keys with an unambiguous role.

        Fixed sensors and conclusively resolved variants are included.
        Inactive and unresolved variants are excluded without guessing from
        their values.
        """
        return frozenset(self.sensor_variant_resolution.canonical_sensor_keys)

    @property
    def available_sensor_keys(self) -> frozenset[str]:
        """Return detected sensors that are safe to expose as normal entities."""
        resolution = self.sensor_variant_resolution

        unresolved_single_role_keys = frozenset(
            result.variant_sensor_keys[0]
            for result in resolution.variants
            if result.status is SensorVariantStatus.UNRESOLVED
            and len(result.variant_sensor_keys) == 1
        )

        return self.detected_sensors & (
            frozenset(resolution.canonical_sensor_keys) | unresolved_single_role_keys
        )

    @property
    def unresolved_detected_sensor_keys(self) -> frozenset[str]:
        """Return detected role-specific views kept only for diagnostics."""
        return self.detected_sensors & frozenset(
            self.sensor_variant_resolution.unresolved_sensor_keys
        )

    @property
    def inactive_detected_sensor_keys(self) -> frozenset[str]:
        """Return detected views whose input is configured for non-sensor use."""
        return self.detected_sensors & frozenset(
            self.sensor_variant_resolution.inactive_sensor_keys
        )

    @property
    def system_activity(self) -> SystemActivity | None:
        """Return combined heating and WW system activity from pump states."""
        heating_states = tuple(
            circuit.pump_running for circuit in self.control_circuits
        )
        ww_state = self.rk4.storage_tank_charging_pump_running

        if all(state is None for state in (*heating_states, ww_state)):
            return None

        heating = any(state is True for state in heating_states)
        ww_active = ww_state is True
        if heating and ww_active:
            return SystemActivity.HEATING_AND_DOMESTIC_HOT_WATER
        if heating:
            return SystemActivity.HEATING
        if ww_active:
            return SystemActivity.DOMESTIC_HOT_WATER
        return SystemActivity.IDLE

    @property
    def writing_enabled(self) -> bool:
        """Whether writing is enabled by the integration safety switch."""
        return self._writing_enabled

    async def async_update_readings(self) -> UpdateReport:
        """Refresh what the controller measures and controls.

        Sensor inputs, control-circuit operating values, pump and valve states,
        faults and the clock — everything that moves on its own.

        The configuration this library interprets those with is *not* in here,
        so a caller polling readings alone must call
        :meth:`async_update_settings` at least once first: without it the
        sensor-variant resolution and the heating-circuit control modes have
        nothing to read and stay ``None``.
        """
        return await self._async_poll(self._readings, UpdateReport(set(), {}))

    async def async_update_settings(self) -> UpdateReport:
        """Refresh what the controller was configured with: CO/F and PA values.

        These change when someone reconfigures the controller, not on their
        own, so a caller polls them rarely — and again after a reconfiguration.
        """
        return await self._async_poll(self._settings, UpdateReport(set(), {}))

    async def async_update(self) -> UpdateReport:
        """Refresh readings and settings together, in one report.

        For a caller that does not want to schedule the two apart.
        """
        report = await self.async_update_readings()
        return await self._async_poll(self._settings, report)

    async def _async_poll(
        self,
        names: list[str],
        report: UpdateReport,
    ) -> UpdateReport:
        """Read each subsystem on its own, adding what happened to ``report``.

        Subsystems are read independently: one whose block the controller
        refuses or answers too slowly keeps its previous values while the rest
        still refresh. Listeners fire only after every subsystem of this poll
        has been tried, and only on the ones that refreshed. A failure of the
        link itself raises ``ModbusConnectionError`` instead of reporting, and
        a timeout with nothing answered yet raises rather than walk a silent
        controller subsystem by subsystem.
        """
        for name in names:
            component: Component = getattr(self, name)
            try:
                await component.async_update(notify=False)
            except ModbusConnectionError:
                raise
            except ModbusTimeoutError as err:
                if not report.updated and not report.failed:
                    raise  # the first block timed out: assume the rest do too
                report.failed[name] = err
            except ModbusError as err:
                report.failed[name] = err
            else:
                report.updated.add(name)
        for name in names:
            if name in report.updated:
                fresh: Component = getattr(self, name)
                fresh.notify()
        return report

    async def async_read_raw(self) -> dict[str, dict[int, int | bool]]:
        """Every register this device reads, undecoded, for diagnostics.

        The polled subsystems are the whole map: identity sits in ``info``,
        which the poll reads like any other subsystem, and ``async_probe``
        reads nothing beyond ``info`` and ``sensors``.

        A dump is not a poll, so it refreshes the fields without notifying.
        """
        raw: dict[str, dict[int, int | bool]] = {}
        for component in self.components:
            for space, values in (await component.async_read_raw(notify=False)).items():
                raw.setdefault(space, {}).update(values)
        return raw

    async def async_read_writing_enabled(self) -> bool:
        """Read the current write-enabled state directly from the controller."""
        return await async_read_writing_enabled(self._unit)

    async def async_enable_writing(
        self,
        access_code: int = DEFAULT_WRITE_ACCESS_CODE,
    ) -> None:
        """Enable TROVIS writing globally."""
        await async_enable_writing(self._unit, access_code)
        self._writing_enabled = True

    async def async_disable_writing(self) -> None:
        """Disable TROVIS writing globally."""
        try:
            await async_disable_writing(self._unit)
        finally:
            self._writing_enabled = False
