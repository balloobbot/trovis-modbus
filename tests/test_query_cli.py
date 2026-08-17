"""Light tests for the script/query.py CLI (no real backend needed)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from modbus_connection.cli_helper import field_rows
from modbus_connection.mock import MockModbusUnit

from trovis_modbus import MonthDay, Trovis557x

from .conftest import COILS, HOLDING

_SPEC = importlib.util.spec_from_file_location(
    "trovis_query", Path(__file__).resolve().parents[1] / "script" / "query.py"
)
assert _SPEC and _SPEC.loader
query = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(query)


def test_month_day_renders_as_day_dot_month() -> None:
    """The dump prints values with str(), so MonthDay carries its own format."""
    assert str(MonthDay(day=15, month=5)) == "15.05"


def test_parse_args_tcp() -> None:
    args = query._parse_args(["tcp", "1.2.3.4", "--unit", "246"])
    assert args.transport == "tcp"
    assert args.host == "1.2.3.4"
    assert args.unit == 246
    assert args.port == 502
    assert args.framer == "rtu"  # RTU-over-TCP default for Trovis gateways


def test_parse_args_serial() -> None:
    args = query._parse_args(["serial", "/dev/ttyUSB0", "--unit", "1"])
    assert args.transport == "serial"
    assert args.device == "/dev/ttyUSB0"
    assert args.unit == 1
    assert args.baudrate == 19200  # Trovis serial default


def test_values_lists_every_subsystem_field(mock_modbus_unit: MockModbusUnit) -> None:
    """Each sub-system's public fields are enumerated, methods excluded."""
    device = Trovis557x(mock_modbus_unit)

    circuit_rows = field_rows(device.rk1)
    circuit_names = {name for name, _value in circuit_rows}

    assert {"mode", "pump_running", "room_setpoint_active"} <= circuit_names
    assert "flow_temperature" not in circuit_names
    assert "return_temperature" not in circuit_names
    assert "room_temperature" not in circuit_names

    function_rows = field_rows(device.functions)
    function_names = {name for name, _value in function_rows}
    assert {
        "input_01_is_binary",
        "input_02_is_binary",
        "input_17_is_binary",
        "pulse_input_enabled",
        "analog_setpoint_correction_enabled",
    } <= function_names

    parameter_rows = field_rows(device.parameters)
    parameter_names = {name for name, _value in parameter_rows}
    assert {
        "analog_input_selection",
        "validated_analog_input_selection",
        "selected_analog_inputs",
        "storage_tank_charging_pump_sensor_input",
        "validated_storage_tank_charging_pump_sensor_input",
    } <= parameter_names

    sensor_rows = field_rows(device.sensors)
    sensor_names = {name for name, _value in sensor_rows}

    assert {
        "af1",
        "af2",
        "vf1",
        "vf2",
        "vf3",
        "vf4",
        "ruef1",
        "ruef2",
        "ruef3",
        "rf1",
        "rf2",
        "rf3",
        "sf1",
        "sf2",
        "sf3",
        "fg1",
        "fg2",
        "fg3",
        "analog_input_voltage",
    } <= sensor_names
    # field_rows() lists what the component serves, so a logical view this
    # model's read layout excludes is left out rather than shown empty.
    unsupported_sensor_views = {
        "ae1",
        "ae2",
        "ae3",
        "analog_input_current",
    }
    assert unsupported_sensor_views.isdisjoint(sensor_names)
    assert unsupported_sensor_views.isdisjoint(device.sensors.readable_field_names)
    assert {
        "af1",
        "af2",
        "vf1",
        "vf2",
        "vf3",
        "vf4",
        "ruef1",
        "ruef2",
        "ruef3",
        "rf1",
        "rf2",
        "rf3",
        "sf1",
        "sf2",
        "sf3",
        "fg1",
        "fg2",
        "fg3",
        "analog_input_voltage",
        "pulse_rate",
    } <= device.sensors.readable_field_names

    # Methods / private helpers are not data rows.
    assert "heating_curve" not in circuit_names
    assert "async_update" not in circuit_names
    assert all(not n.startswith("_") for n in circuit_names)
    assert all(not n.startswith("_") for n in sensor_names)


def test_print_runs(
    capsys: pytest.CaptureFixture[str], mock_modbus_unit: MockModbusUnit
) -> None:
    device = Trovis557x(mock_modbus_unit)
    query._print(device)
    out = capsys.readouterr().out
    assert "Device" in out
    assert "Functions" in out
    assert "Parameters" in out
    assert "Sensor variants" in out
    assert "sf3 / fg3 / pulse_rate: unresolved" in out
    assert "Rk1 - Control circuit 1" in out
    assert "Rk4 - Domestic hot water" in out
    assert "Rk1 - Buffer tank extension" not in out
    assert "Solar circuit" not in out


async def test_print_includes_solar_only_for_solar_systems(
    capsys: pytest.CaptureFixture[str], mock_modbus_unit: MockModbusUnit
) -> None:
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.holding[1] = 23  # Anlage 2.3 includes solar.
    mock_modbus_unit.coils.update(COILS)
    device = Trovis557x(mock_modbus_unit)
    await device.async_update()

    query._print(device)
    out = capsys.readouterr().out

    assert "Solar circuit" in out
    assert "pump_on_temperature_difference" in out
    assert "operating_hours" in out


async def test_print_includes_buffer_tank_only_for_buffer_tank_systems(
    capsys: pytest.CaptureFixture[str], mock_modbus_unit: MockModbusUnit
) -> None:
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.holding[1] = 161  # Anlage 16.1
    mock_modbus_unit.holding[1099] = 0  # AUTO
    mock_modbus_unit.holding[1100] = 0  # AUTO
    mock_modbus_unit.holding[1101] = 60  # 6.0 K
    mock_modbus_unit.holding[1102] = 10  # factor 1.0
    mock_modbus_unit.holding[1103] = 4  # charging
    mock_modbus_unit.coils.update(COILS)
    device = Trovis557x(mock_modbus_unit)
    await device.async_update()

    query._print(device)
    out = capsys.readouterr().out

    assert "Rk1 - Buffer tank extension" in out
    assert "minimum_charging_setpoint" in out
    assert "charging_pump_lag_factor" in out
    assert "status" in out
