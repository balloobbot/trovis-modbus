"""Tests for TROVIS address ranges as field-availability maps."""

from __future__ import annotations

from trovis_modbus.configurations.address_ranges import (
    COIL_RANGES_3_RK,
    REGISTER_RANGES_3_RK,
    SUPPORTED_MODELS,
    control_circuit_count,
    is_span_readable,
    ranges_for_model,
)


def test_span_must_fit_completely_inside_one_range() -> None:
    ranges = ((0, 5), (10, 20))

    assert is_span_readable(0, 1, ranges)
    assert is_span_readable(3, 3, ranges)
    assert is_span_readable(10, 11, ranges)
    assert not is_span_readable(5, 2, ranges)
    assert not is_span_readable(6, 1, ranges)


def test_extended_model_raw_values_use_family_ranges() -> None:
    assert ranges_for_model(55781) == (REGISTER_RANGES_3_RK, COIL_RANGES_3_RK)
    assert control_circuit_count(55781) == 3
    assert control_circuit_count(55731) == 2


async def test_every_supported_model_plans_inside_its_ranges(
    mock_modbus_unit,
) -> None:
    """Every model's read layout survives the planner's readable-range check.

    ``modbus-connection`` refuses to plan a field (or scale register) the
    declared map cannot contain, so a profile that keeps an unreadable field
    fails here at plan time rather than on a real controller.
    """
    from trovis_modbus import Trovis557x

    for model in sorted(SUPPORTED_MODELS):
        device = Trovis557x(mock_modbus_unit, model=model)
        await device.async_update()  # pooled; raises ValueError on a misfit
        for component in device.components:
            await component.async_update()  # and standalone, per component


async def test_ranges_can_be_narrowed_after_the_first_read(
    mock_modbus_unit,
) -> None:
    """A later range profile re-plans the reads and drops what it excluded."""
    from trovis_modbus import Functions

    functions = Functions(mock_modbus_unit)
    await functions.async_update()  # builds and caches the read layout
    assert functions.is_field_readable("input_12_is_binary")
    assert functions.input_12_is_binary is False

    # The two-Rk profile serves CL801/CL802 only, so CL812 goes away.
    functions.configure_readable_ranges(*ranges_for_model(5573))

    assert not functions.is_field_readable("input_12_is_binary")
    assert functions.input_12_is_binary is None
    await functions.async_update()
    assert functions.input_12_is_binary is None
    assert functions.input_02_is_binary is False
