"""End-to-end tests of the object model over the in-memory mock backend."""

from __future__ import annotations

from datetime import date, time

import pytest
from modbus_connection import (
    ClientClosedError,
    GatewayTargetError,
    IllegalDataAddressError,
)
from modbus_connection.mock import MockModbusConnection, MockModbusUnit

from trovis_modbus import (
    ControlCircuitRole,
    MonthDay,
    OperatingMode,
    SystemActivity,
    TemperatureRange,
    Trovis557x,
    TrovisWriteAccessError,
    Weekday,
)
from trovis_modbus.configurations.address_ranges import (
    COIL_RANGES,
    REGISTER_RANGES,
)

from .conftest import COILS, HOLDING


async def test_device_info(trovis: Trovis557x) -> None:
    await trovis.async_update()
    info = trovis.info
    assert info.manufacturer == "SAMSON"
    assert info.model == "TROVIS 5579"  # shaped inline by the property
    assert info.serial_number == "12345"
    assert info.firmware_version == "3.05"


async def test_sensors(trovis: Trovis557x) -> None:
    await trovis.async_update()
    assert trovis.sensors.af1 == pytest.approx(-5.0)  # signed, outdoor temperature
    assert trovis.sensors.vf1 == pytest.approx(30.0)  # unsigned, water in pipes
    assert trovis.sensors.rf1 == pytest.approx(20.0)
    assert trovis.sensors.sf1 == pytest.approx(45.0)
    assert trovis.sensors.sf2 is None  # NaN sentinel
    assert trovis.sensors.sf3 == pytest.approx(65.0)
    assert trovis.sensors.ae1 is None
    assert trovis.sensors.fg1 == pytest.approx(95.2)
    assert trovis.sensors.ae2 is None
    assert trovis.sensors.fg2 == pytest.approx(325.0)
    assert trovis.sensors.ae3 is None
    assert trovis.sensors.fg3 == pytest.approx(12.5)
    # The raw IMP register is read for supported models so it remains available
    # for diagnostics. CL139 decides whether IMP is exposed as a canonical sensor.
    assert trovis.sensors.pulse_rate == 240
    assert "pulse_rate" not in trovis.available_sensor_keys
    assert trovis.sensors.analog_input_voltage == pytest.approx(7.35)
    assert trovis.sensors.analog_input_current is None


async def test_clock(trovis: Trovis557x) -> None:
    await trovis.async_update()
    assert trovis.clock.time == time(14, 30)
    assert trovis.clock.date == date(2026, 6, 21)
    assert trovis.clock.datetime.isoformat() == "2026-06-21T14:30:00"


async def test_controller(trovis: Trovis557x) -> None:
    await trovis.async_update()
    assert trovis.controller.switch_top is OperatingMode.AUTOMATIC
    assert trovis.controller.max_flow_setpoint == pytest.approx(90.0)
    assert trovis.controller.summer_start == MonthDay(day=15, month=5)
    assert trovis.controller.summer_end == MonthDay(day=30, month=9)
    assert trovis.controller.temperature_monitoring_deviation == pytest.approx(5.0)
    assert trovis.controller.temperature_monitoring_window == 30
    assert trovis.controller.outdoor_temperature_input_range_start == pytest.approx(
        -20.0
    )
    assert trovis.controller.outdoor_temperature_input_range_end == pytest.approx(50.0)
    assert trovis.controller.summer_outdoor_temperature_average == pytest.approx(18.5)
    assert trovis.controller.glt_timeout_active is False


async def test_heating_circuit_reads(trovis: Trovis557x) -> None:
    await trovis.async_update()
    rk1 = trovis.rk1
    assert rk1.mode is OperatingMode.AUTOMATIC
    assert rk1.valve_setpoint == 42
    assert rk1.flow_setpoint == pytest.approx(55.0)
    assert rk1.room_setpoint_active == pytest.approx(21.0)
    assert rk1.pump_running is True
    assert rk1.day_active is True
    assert rk1.automatic is True


async def test_circuit_offset_pattern(trovis: Trovis557x) -> None:
    """Circuit 2 reads its own (+200) registers."""
    await trovis.async_update()
    assert trovis.rk2.flow_setpoint == pytest.approx(48.0)
    assert trovis.rk1.flow_setpoint == pytest.approx(55.0)


async def test_heating_curve(trovis: Trovis557x) -> None:
    await trovis.async_update()
    curve = trovis.rk1.heating_curve()
    assert curve is not None and len(curve) == 41
    # day active, room 21, slope 1.2, offset 0, clamp [20, 80]
    assert curve[-1] == pytest.approx(26.4)  # outdoor temperature +20 °C
    assert trovis.rk1.heating_curve("night") is not None


async def test_domestic_hot_water(trovis: Trovis557x) -> None:
    await trovis.async_update()
    rk4 = trovis.rk4
    assert rk4.setpoint_day == pytest.approx(50.0)
    assert rk4.setpoint_active == pytest.approx(50.0)
    assert rk4.active_charging_setpoint == pytest.approx(67.0)
    assert rk4.disinfection_weekday is Weekday.WEDNESDAY
    assert rk4.disinfection_start == time(19, 0)
    assert rk4.disinfection_stop == time(21, 0)
    assert rk4.day_temperature_range == TemperatureRange(50.0, 55.0)
    assert rk4.night_temperature_range == TemperatureRange(45.0, 50.0)
    assert rk4.automatic is True
    assert rk4.storage_tank_charging_pump_running is True


async def test_combined_activity(trovis: Trovis557x) -> None:
    await trovis.async_update()
    assert trovis.system_activity is SystemActivity.HEATING_AND_DOMESTIC_HOT_WATER


async def test_independent_component_update(trovis: Trovis557x) -> None:
    """A sub-system refreshes on its own, without the rest."""
    await trovis.rk4.async_update()
    assert trovis.rk4.setpoint_day == pytest.approx(50.0)
    assert trovis.rk1.flow_setpoint is None  # not updated yet


async def test_full_update_consolidates_reads(
    trovis: Trovis557x, unit: MockModbusUnit
) -> None:
    """A full device update pools all sub-systems into a few block reads."""
    field_count = sum(len(c.readable_field_names) for c in trovis.components)
    await trovis.async_update()

    # Many fields collapse into a small number of range-aware block reads — far
    # fewer than the field count, and well under a naive per-field strategy.
    assert len(unit.read_events) < field_count // 4

    # The exact number of blocks may change when manufacturer ranges or the
    # planner improve. The stable safety guarantee is the configured max_span.
    assert all(event.count <= 50 for event in unit.read_events)


async def test_full_update_never_reads_across_an_unreadable_gap(
    trovis: Trovis557x, unit: MockModbusUnit
) -> None:
    """Every block stays inside the controller's readable ranges (no NAK risk)."""
    await trovis.async_update()

    ranges = {"holding": REGISTER_RANGES, "coil": COIL_RANGES}
    for event in unit.read_events:
        declared = ranges[event.register_type]
        covered = range(event.address, event.address + event.count)
        assert all(
            any(low <= address <= high for low, high in declared) for address in covered
        ), (
            f"{event.register_type} block {covered.start}..{covered.stop - 1} "
            "crosses an unreadable gap"
        )
    # Addresses 7-8 (between ranges [0,6] and [9,40]) are never read — the low
    # registers split there instead of being merged into one 0..26 block.
    read = {
        event.address + i
        for event in unit.read_events
        if event.register_type == "holding"
        for i in range(event.count)
    }
    assert 7 not in read and 8 not in read


async def test_consolidated_reads_decode_correctly(unit: MockModbusUnit) -> None:
    """Adjacent physical sensor registers decode to the right sensor inputs."""
    # Flow sensors VF1/VF2/VF3 are at adjacent addresses 12/13/14 — fetched in
    # one block, then decoded on the central Sensors component.
    unit.holding.update({12: 300, 13: 310, 14: 320})
    device = Trovis557x(unit)

    await device.async_update()

    assert device.sensors.vf1 == pytest.approx(30.0)
    assert device.sensors.vf2 == pytest.approx(31.0)
    assert device.sensors.vf3 == pytest.approx(32.0)


async def test_a_refused_block_reports_which_block_was_refused(
    trovis: Trovis557x, unit: MockModbusUnit
) -> None:
    """A controller refusing a planned block names the block, not just the code."""
    # VF1, in the middle of the pooled sensor block rather than at its start.
    unit.fail_read(12, IllegalDataAddressError())

    with pytest.raises(IllegalDataAddressError) as refusal:
        await trovis.async_update()

    block = refusal.value.block
    assert block is not None
    assert block.space == "holding"
    assert block.address <= 12 < block.address + block.count
    # The update applied nothing, so no sub-system holds a half-read value.
    assert trovis.sensors.vf1 is None
    assert trovis.rk1.flow_setpoint is None


async def test_update_survives_a_dropped_connection() -> None:
    """A dropped link heals on the next update — the device is not rebuilt."""
    connection = MockModbusConnection()
    unit = connection.for_unit(1)
    unit.holding.update(HOLDING)
    unit.coils.update(COILS)
    device = Trovis557x(unit)
    await device.async_update()
    assert device.rk1.flow_setpoint == pytest.approx(55.0)

    lost: list[int] = []
    connection.on_connection_lost(lambda: lost.append(1))
    connection.simulate_connection_lost()
    assert lost == [1]

    # The same device and unit handles keep working; the request reconnects.
    await device.async_update()
    assert device.rk1.flow_setpoint == pytest.approx(55.0)


async def test_update_survives_a_recycled_connection() -> None:
    """disconnect() recycles a stuck link; the device keeps its handles."""
    connection = MockModbusConnection()
    unit = connection.for_unit(1)
    unit.holding.update(HOLDING)
    unit.coils.update(COILS)
    device = Trovis557x(unit)
    await device.async_update()

    lost: list[int] = []
    connection.on_connection_lost(lambda: lost.append(1))
    await connection.disconnect()

    await device.async_update()
    assert device.rk1.flow_setpoint == pytest.approx(55.0)
    # The owner tore the link down; nothing was lost.
    assert lost == []


async def test_update_after_close_raises() -> None:
    """Closing is the owner's permanent end of the connection, not a drop."""
    connection = MockModbusConnection()
    unit = connection.for_unit(1)
    unit.holding.update(HOLDING)
    device = Trovis557x(unit)
    await connection.close()

    with pytest.raises(ClientClosedError):
        await device.async_update()


async def test_update_listener(trovis: Trovis557x) -> None:
    calls: list[int] = []
    unsubscribe = trovis.rk4.add_update_listener(lambda: calls.append(1))
    await trovis.rk4.async_update()
    await trovis.rk4.async_update()
    assert len(calls) == 2
    unsubscribe()
    await trovis.rk4.async_update()
    assert len(calls) == 2  # no longer notified


async def test_write_roundtrip(trovis: Trovis557x) -> None:
    await trovis.async_update()
    await trovis.async_enable_writing()
    await trovis.rk1.set_room_setpoint_day(21.5)
    await trovis.rk4.set_setpoint(52.0)
    await trovis.rk1.async_update()
    await trovis.rk4.async_update()
    assert trovis.rk1.room_setpoint_day == pytest.approx(21.5)
    assert trovis.rk4.setpoint_day == pytest.approx(52.0)


async def test_write_rejects_readonly(trovis: Trovis557x) -> None:
    with pytest.raises(AttributeError):
        await trovis.rk1.write("flow_setpoint", 50.0)


async def test_mode_write_releases_override_coil(
    trovis: Trovis557x, unit: MockModbusUnit
) -> None:
    """Setting the mode first releases the Ebene coil (0 = remote control)."""
    await trovis.async_enable_writing()
    await unit.write_coil(88, True)  # start "autonomous" (controller-controlled)
    await trovis.rk1.set_mode(OperatingMode.DAY)

    # Override coil 88 (EBNBetrArtRk1) released to 0, then mode register written.
    assert (await unit.read_coils(88, 1))[0] is False
    assert (await unit.read_holding_registers(105, 1))[0] == int(OperatingMode.DAY)


async def test_circuit2_mode_uses_strided_override(
    trovis: Trovis557x, unit: MockModbusUnit
) -> None:
    """Circuit 2's override coil follows the +2 stride (90, not 88)."""
    await unit.write_coil(90, True)
    await trovis.rk2.set_mode(OperatingMode.NIGHT)
    assert (await unit.read_coils(90, 1))[0] is False
    assert (await unit.read_holding_registers(107, 1))[0] == int(OperatingMode.NIGHT)


async def test_write_access_enable_disable(
    trovis: Trovis557x, unit: MockModbusUnit
) -> None:
    assert await trovis.async_read_writing_enabled() is False

    await trovis.async_enable_writing()
    assert await trovis.async_read_writing_enabled() is True
    assert (await unit.read_holding_registers(144, 1))[0] == 1732

    await trovis.async_disable_writing()
    assert await trovis.async_read_writing_enabled() is False
    assert (await unit.read_holding_registers(144, 1))[0] == 0


async def test_write_refreshes_access_code(
    trovis: Trovis557x, unit: MockModbusUnit
) -> None:
    """The public write path refreshes HR40145 before writing the datapoint."""
    assert await trovis.async_read_writing_enabled() is False

    await trovis.rk1.set_room_setpoint_day(21.5)

    assert (await unit.read_holding_registers(144, 1))[0] == 1732
    assert (await unit.read_holding_registers(1002, 1))[0] == 215


async def test_write_access_reports_a_device_that_answers_nothing(
    trovis: Trovis557x, unit: MockModbusUnit
) -> None:
    """Every HR40145 path reports a refusal as a TROVIS write-access failure."""
    # A gateway that answers for itself while the controller behind it does not
    # — the usual failure of a TROVIS on an RTU-over-TCP bridge.
    unit.fail_requests(GatewayTargetError())

    with pytest.raises(TrovisWriteAccessError):
        await trovis.async_read_writing_enabled()
    with pytest.raises(TrovisWriteAccessError):
        await trovis.async_enable_writing()
    with pytest.raises(TrovisWriteAccessError):
        await trovis.async_disable_writing()
    # The public datapoint write refreshes the access code first, so it fails
    # there rather than reaching the register it was asked to write.
    with pytest.raises(TrovisWriteAccessError):
        await trovis.rk1.set_room_setpoint_day(21.5)
    assert trovis.writing_enabled is False


async def test_5576_anlage_2_1_exposes_rk1_and_rk4(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.coils.update(COILS)
    device = Trovis557x(
        mock_modbus_unit,
        model=5576,
    )
    await device.async_update()
    assert device.control_circuit_indices == (1, 4)


async def test_5576_anlage_2_1_exposes_rk_roles(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.coils.update(COILS)
    device = Trovis557x(
        mock_modbus_unit,
        model=5576,
    )

    await device.async_update()

    assert device.configuration_definition is not None
    assert device.configuration_definition.display_code == "2.1"
    assert device.configuration_supported_by_model is True
    assert device.control_circuit_indices == (1, 4)
    assert device.control_circuit_role(1) is ControlCircuitRole.HEATING
    assert device.control_circuit_role(2) is ControlCircuitRole.UNUSED
    assert device.control_circuit_role(3) is ControlCircuitRole.UNUSED
    assert device.control_circuit_role(4) is ControlCircuitRole.DOMESTIC_HOT_WATER
    assert device.has_rk4 is True


def test_device_exposes_only_rk_slot_names(mock_modbus_unit: MockModbusUnit) -> None:
    device = Trovis557x(mock_modbus_unit, model=5579)

    assert device.rk1 is device.control_circuits[0]
    assert device.rk2 is device.control_circuits[1]
    assert device.rk3 is device.control_circuits[2]
    assert device.rk4 is not None
    for legacy_name in ("hk1", "hk2", "hk3", "ww", "heating_circuits"):
        assert not hasattr(device, legacy_name)


async def test_control_circuit_roles_are_clipped_to_model_capacity(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.holding[1] = 61  # Anlage 6.1 uses Rk1 through Rk3.
    mock_modbus_unit.coils.update(COILS)
    device = Trovis557x(
        mock_modbus_unit,
        model=5576,
    )

    await device.async_update()

    assert device.configuration_definition is not None
    assert device.configuration_definition.display_code == "6.1"
    assert device.configuration_supported_by_model is False
    assert device.control_circuit_indices == (1, 2, 4)
    assert device.control_circuit_role(3) is ControlCircuitRole.UNUSED


async def test_5579_anlage_5_1_exposes_precontrol_and_heating_roles(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.holding[1] = 51
    mock_modbus_unit.coils.update(COILS)
    device = Trovis557x(
        mock_modbus_unit,
        model=5579,
    )

    await device.async_update()

    assert device.control_circuit_indices == (1, 2, 3, 4)
    assert device.control_circuit_role(1) is ControlCircuitRole.PRECONTROL
    assert device.control_circuit_role(2) is ControlCircuitRole.HEATING
    assert device.control_circuit_role(3) is ControlCircuitRole.HEATING
    assert device.control_circuit_role(4) is ControlCircuitRole.DOMESTIC_HOT_WATER
    assert device.room_heating_circuit_indices == (2, 3)
    assert device.has_rk4 is True


async def test_5578_anlage_16_1_exposes_buffer_tank_role(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.holding[1] = 161
    mock_modbus_unit.coils.update(COILS)
    device = Trovis557x(
        mock_modbus_unit,
        model=5578,
    )

    await device.async_update()

    assert device.control_circuit_indices == (1, 2)
    assert device.control_circuit_role(1) is ControlCircuitRole.BUFFER_TANK
    assert device.has_buffer_tank_circuit is True
    assert device.has_buffer_tank_charging_parameters is True
    assert device.buffer_tank in device.components
    assert device.control_circuit_role(2) is ControlCircuitRole.HEATING
    assert device.room_heating_circuit_indices == (2,)
    assert device.has_rk4 is False


async def test_solar_capability_follows_hydronic_system(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.coils.update(COILS)
    device = Trovis557x(mock_modbus_unit, model=5579)

    await device.async_update()
    assert device.configuration_definition is not None
    assert device.configuration_definition.display_code == "2.1"
    assert device.has_solar is False

    mock_modbus_unit.holding[1] = 23  # Anlage 2.3 includes solar.
    await device.async_update()
    assert device.configuration_definition is not None
    assert device.configuration_definition.display_code == "2.3"
    assert device.has_solar is True
    assert device.solar.pump_on_temperature_difference == pytest.approx(10.0)
    assert device.solar.pump_off_temperature_difference == pytest.approx(3.0)
    assert device.solar.maximum_storage_temperature == pytest.approx(80.0)
    assert device.solar.operating_hours == 1234
    assert device.solar.pump_running is True


async def test_non_buffer_system_does_not_enable_buffer_tank_circuit(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.holding[1] = 21  # Anlage 2.1
    mock_modbus_unit.coils.update(COILS)

    device = Trovis557x(mock_modbus_unit, model=5579)
    await device.async_update()

    assert device.has_buffer_tank_circuit is False
    assert device.has_buffer_tank_charging_parameters is False


async def test_fixed_loading_buffer_system_omits_pa1_p16_to_p19_capability(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.holding[1] = 141  # Anlage 14.1
    mock_modbus_unit.coils.update(COILS)

    device = Trovis557x(mock_modbus_unit, model=5576)
    await device.async_update()

    assert device.has_buffer_tank_circuit is True
    assert device.has_buffer_tank_charging_parameters is False
