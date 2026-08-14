"""One failing block must not take the rest of the poll with it.

A TROVIS answers some blocks slowly and refuses others outright depending on
model, hydronic system and sensor assignment. The poll reads each sub-system on
its own so that a single failure costs that sub-system's values and nothing
else.
"""

from __future__ import annotations

import pytest
from modbus_connection import (
    ModbusConnectionError,
    ModbusTimeoutError,
)
from modbus_connection.mock import MockModbusUnit

from trovis_modbus import Trovis557x

from .conftest import COILS, HOLDING


async def test_a_failed_subsystem_leaves_the_rest_fresh(
    trovis: Trovis557x, unit: MockModbusUnit
) -> None:
    await trovis.async_update()
    before = trovis.sensors.vf1

    unit.holding[12] = 400  # VF1 changes on the controller
    unit.holding[999] = 600  # so does the Rk1 flow setpoint
    unit.fail_read(12, ModbusTimeoutError("slow sensor block"))
    report = await trovis.async_update()

    assert not report.complete
    assert set(report.failed) == {"sensors"}
    assert isinstance(report.failed["sensors"], ModbusTimeoutError)
    assert "rk1" in report.updated
    assert trovis.sensors.vf1 == before
    assert trovis.rk1.flow_setpoint == pytest.approx(60.0)


async def test_listeners_fire_at_the_end_and_only_for_fresh_subsystems(
    trovis: Trovis557x, unit: MockModbusUnit
) -> None:
    await trovis.async_update()
    seen: list[int] = []
    trovis.rk1.add_update_listener(lambda: seen.append(len(unit.read_events)))
    trovis.sensors.add_update_listener(lambda: seen.append(-1))

    unit.fail_read(12, ModbusTimeoutError("slow sensor block"))
    unit.read_events.clear()
    await trovis.async_update()

    # One notification, after every sub-system was tried; none for the failure.
    assert seen == [len(unit.read_events)]


async def test_one_circuit_failing_leaves_the_others_fresh(
    trovis: Trovis557x, unit: MockModbusUnit
) -> None:
    """Why the Rk circuits are not pooled into one ``ComponentGroup``.

    They do tile one short run — the mode/control-signal registers and the
    status coils step by circuit — but each circuit also owns a 44-register
    parameter block of its own at 41000 + 200 * i that no other circuit reads.
    Pooling would put those private blocks in one plan, so a controller
    refusing Rk1's parameters would blank Rk2, Rk3 and Rk4 as well.
    """
    await trovis.async_update()
    unit.fail_read(999, ModbusTimeoutError("Rk1 parameter block"))

    report = await trovis.async_update()

    assert set(report.failed) == {"rk1"}
    assert {"rk2", "rk3", "rk4"} <= report.updated
    assert trovis.rk2.flow_setpoint == pytest.approx(48.0)


async def test_a_dead_link_raises_instead_of_reporting(
    trovis: Trovis557x, unit: MockModbusUnit
) -> None:
    await trovis.async_update()
    unit.fail_requests(ModbusConnectionError("link down"))
    with pytest.raises(ModbusConnectionError):
        await trovis.async_update()


async def test_every_subsystem_refreshes_on_a_healthy_controller(
    trovis: Trovis557x,
) -> None:
    report = await trovis.async_update()
    assert report.complete
    assert report.failed == {}
    assert {"info", "sensors", "rk1", "rk4"} <= report.updated


async def test_unpolled_circuit_slots_are_not_in_the_report(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    """A 5576 has two circuit slots, so Rk3 is never read or reported."""
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.coils.update(COILS)

    report = await Trovis557x(mock_modbus_unit, model=5576).async_update()

    assert {"rk1", "rk2"} <= report.updated
    assert "rk3" not in report.updated and "rk3" not in report.failed


async def test_a_failed_probe_raises_and_retries(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    """Setup is the poll's foundation; a probe reporting half a device is worse."""
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.coils.update(COILS)
    mock_modbus_unit.fail_read(9, ModbusTimeoutError("no sensors"))

    with pytest.raises(ModbusTimeoutError):
        await Trovis557x.async_probe(mock_modbus_unit)

    mock_modbus_unit.fail_read(9, None)
    probe = await Trovis557x.async_probe(mock_modbus_unit)
    assert probe.model == 5579
    assert "af1" in probe.detected_sensors
