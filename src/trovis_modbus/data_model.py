"""Trovis-specific pieces layered on the ``modbus_connection.model`` framework."""

from __future__ import annotations

import datetime
from collections.abc import Callable, Iterable
from enum import IntEnum
from typing import Any

from modbus_connection import ModbusError
from modbus_connection.model import (
    Component,
    RegisterField,
    coil as _modbus_coil,
    enum as _modbus_enum,
    gauge as _modbus_gauge,
    integer as _modbus_integer,
    raw_register as _modbus_raw_register,
)

from .addresses import coil_address, register_address
from .configurations.address_ranges import (
    COIL_RANGES,
    REGISTER_RANGES,
    is_span_readable,
)
from .enums import OperatingMode
from .exceptions import TrovisValueValidationError, TrovisWriteAccessError
from .metadata import (
    BooleanMetadata,
    DatapointMetadata,
    EnumMetadata,
    NumberMetadata,
    OptionMetadata,
    TemporalMetadata,
    attach_metadata,
    step_from_digits,
)
from .utils import (
    MonthDay,
    date_from_ddmm_year,
    date_to_ddmm_year,
    month_day_from_ddmm,
    month_day_to_ddmm,
    time_from_hhmm,
    time_to_hhmm,
)

NAN_INT16 = 0x7FFF  # the value the controller returns for an absent sensor

DEFAULT_WRITE_ACCESS_CODE = 1732
WRITE_ACCESS_REGISTER = 40145  # HR40145 / Write-En_Modem, Modbus address 144
WRITE_ACCESS_DISABLE_CODE = 0

LEVEL_GLT = False
LEVEL_AUTARK = True


class PackedTimeField(RegisterField[datetime.time]):
    """A TROVIS HHMM register exposed as a native ``datetime.time``."""

    def __init__(
        self,
        address: int,
        *,
        min_value: datetime.time,
        max_value: datetime.time,
        raw_min: int,
        raw_max: int,
        writable: bool = False,
    ) -> None:
        super().__init__(address, writable=writable)
        self.min_value = min_value
        self.max_value = max_value
        self.raw_min = raw_min
        self.raw_max = raw_max

    def decode(
        self,
        words: list[int],
        scale_exponent: int | None = None,
    ) -> datetime.time | None:
        """Decode one packed HHMM word within the documented range."""
        raw = words[0]
        if not self.raw_min <= raw <= self.raw_max:
            return None
        value = time_from_hhmm(raw)
        if value is None or not self.min_value <= value <= self.max_value:
            return None
        return value

    def encode(
        self,
        value: Any,
        scale_exponent: int | None = None,
    ) -> list[int]:
        """Encode a native time at the regulator's supported precision."""
        try:
            raw = time_to_hhmm(value)
        except (TypeError, ValueError) as err:
            raise TrovisValueValidationError(str(err)) from err
        if not self.min_value <= value <= self.max_value:
            raise TrovisValueValidationError(
                f"Time {value.isoformat()} is outside "
                f"{self.min_value.isoformat()}..{self.max_value.isoformat()}"
            )
        if not self.raw_min <= raw <= self.raw_max:
            raise TrovisValueValidationError(
                f"Packed time {raw} is outside {self.raw_min}..{self.raw_max}"
            )
        return [raw]


def _month_day_key(value: MonthDay) -> tuple[int, int]:
    """Return a calendar-order key for a recurring month/day value."""
    return value.month, value.day


class PackedMonthDayField(RegisterField[MonthDay]):
    """A TROVIS DDMM register exposed as a recurring ``MonthDay``."""

    def __init__(
        self,
        address: int,
        *,
        min_value: MonthDay,
        max_value: MonthDay,
        raw_min: int,
        raw_max: int,
        writable: bool = False,
    ) -> None:
        super().__init__(address, writable=writable)
        self.min_value = min_value
        self.max_value = max_value
        self.raw_min = raw_min
        self.raw_max = raw_max

    def decode(
        self,
        words: list[int],
        scale_exponent: int | None = None,
    ) -> MonthDay | None:
        """Decode one packed DDMM word within the documented range."""
        raw = words[0]
        if not self.raw_min <= raw <= self.raw_max:
            return None
        value = month_day_from_ddmm(raw)
        if value is None:
            return None
        if not (
            _month_day_key(self.min_value)
            <= _month_day_key(value)
            <= _month_day_key(self.max_value)
        ):
            return None
        return value

    def encode(
        self,
        value: Any,
        scale_exponent: int | None = None,
    ) -> list[int]:
        """Encode a validated recurring date."""
        try:
            raw = month_day_to_ddmm(value)
        except (TypeError, ValueError) as err:
            raise TrovisValueValidationError(str(err)) from err
        if not (
            _month_day_key(self.min_value)
            <= _month_day_key(value)
            <= _month_day_key(self.max_value)
        ):
            raise TrovisValueValidationError(
                f"Recurring date {value} is outside {self.min_value}..{self.max_value}"
            )
        if not self.raw_min <= raw <= self.raw_max:
            raise TrovisValueValidationError(
                f"Packed recurring date {raw} is outside {self.raw_min}..{self.raw_max}"
            )
        return [raw]


class PackedDateField(RegisterField[datetime.date]):
    """A TROVIS DDMM register followed by its separate year register."""

    def __init__(
        self,
        address: int,
        *,
        min_value: datetime.date,
        max_value: datetime.date,
        raw_min: int,
        raw_max: int,
        writable: bool = False,
    ) -> None:
        super().__init__(address, count=2, writable=writable)
        self.min_value = min_value
        self.max_value = max_value
        self.raw_min = raw_min
        self.raw_max = raw_max

    def decode(
        self,
        words: list[int],
        scale_exponent: int | None = None,
    ) -> datetime.date | None:
        """Decode ``[DDMM, year]`` into a calendar date."""
        if len(words) != 2 or not self.raw_min <= words[0] <= self.raw_max:
            return None
        value = date_from_ddmm_year(words[0], words[1])
        if value is None or not self.min_value <= value <= self.max_value:
            return None
        return value

    def encode(
        self,
        value: Any,
        scale_exponent: int | None = None,
    ) -> list[int]:
        """Encode a calendar date into ``[DDMM, year]``."""
        try:
            raw_date, year = date_to_ddmm_year(value)
        except (TypeError, ValueError) as err:
            raise TrovisValueValidationError(str(err)) from err
        if not self.min_value <= value <= self.max_value:
            raise TrovisValueValidationError(
                f"Date {value.isoformat()} is outside "
                f"{self.min_value.isoformat()}..{self.max_value.isoformat()}"
            )
        if not self.raw_min <= raw_date <= self.raw_max:
            raise TrovisValueValidationError(
                f"Packed date {raw_date} is outside {self.raw_min}..{self.raw_max}"
            )
        return [raw_date, year]


def _number_validator(
    *,
    min_value: float | int | None = None,
    max_value: float | int | None = None,
    step: float | int | None = None,
) -> Callable[[Any], Any]:
    """Return a write validator for numeric TROVIS values."""

    def validate(value: Any) -> Any:
        number = float(value)
        if min_value is not None and number < min_value:
            raise TrovisValueValidationError(
                f"Value {value} is below minimum {min_value}"
            )
        if max_value is not None and number > max_value:
            raise TrovisValueValidationError(
                f"Value {value} is above maximum {max_value}"
            )
        # Step is primarily UI metadata for now. Avoid hard float-modulo
        # validation until we see invalid writes slipping through.
        return value

    return validate


def _with_number_validator(
    writable: bool | Callable[[Any], Any],
    *,
    min_value: float | int | None,
    max_value: float | int | None,
    step: float | int | None,
) -> bool | Callable[[Any], Any]:
    """Return writable or a validator-backed writable value."""
    if not writable:
        return False
    if callable(writable):
        return writable
    if min_value is None and max_value is None and step is None:
        return True
    return _number_validator(
        min_value=min_value,
        max_value=max_value,
        step=step,
    )


def raw_register(
    hr_number: int,
    *args: Any,
    min_value: float | int | None = None,
    max_value: float | int | None = None,
    step: float | int | None = None,
    digits: int | None = None,
    unit: str | None = None,
    raw_min: float | int | None = None,
    raw_max: float | int | None = None,
    maker_key: str | None = None,
    maker_category: str | None = None,
    description: str | None = None,
    writable: bool | Callable[[Any], Any] = False,
    **kwargs: Any,
):
    """Create a raw register field from a manufacturer TROVIS HR reference."""
    effective_step = step if step is not None else step_from_digits(digits)
    effective_writable = _with_number_validator(
        writable,
        min_value=min_value,
        max_value=max_value,
        step=effective_step,
    )
    field = _modbus_raw_register(
        register_address(hr_number),
        *args,
        writable=effective_writable,
        **kwargs,
    )
    return attach_metadata(
        field,
        DatapointMetadata(
            value_kind="number",
            maker_reference=hr_number,
            maker_key=maker_key,
            maker_category=maker_category,
            description=description,
            writable=bool(writable),
            number=NumberMetadata(
                min_value=min_value,
                max_value=max_value,
                step=effective_step,
                digits=digits,
                unit=unit,
                raw_min=raw_min,
                raw_max=raw_max,
            ),
        ),
    )


def integer(
    hr_number: int,
    *args: Any,
    min_value: float | int | None = None,
    max_value: float | int | None = None,
    step: float | int | None = None,
    digits: int | None = None,
    unit: str | None = None,
    raw_min: float | int | None = None,
    raw_max: float | int | None = None,
    maker_key: str | None = None,
    maker_category: str | None = None,
    description: str | None = None,
    writable: bool | Callable[[Any], Any] = False,
    **kwargs: Any,
):
    """Create an integer field from a manufacturer TROVIS HR reference."""
    effective_step = step if step is not None else step_from_digits(digits)
    effective_writable = _with_number_validator(
        writable,
        min_value=min_value,
        max_value=max_value,
        step=effective_step,
    )
    field = _modbus_integer(
        register_address(hr_number),
        *args,
        writable=effective_writable,
        unit=unit,
        **kwargs,
    )
    return attach_metadata(
        field,
        DatapointMetadata(
            value_kind="number",
            maker_reference=hr_number,
            maker_key=maker_key,
            maker_category=maker_category,
            description=description,
            writable=bool(writable),
            number=NumberMetadata(
                min_value=min_value,
                max_value=max_value,
                step=effective_step,
                digits=digits,
                unit=unit,
                raw_min=raw_min,
                raw_max=raw_max,
            ),
        ),
    )


def gauge(
    hr_number: int,
    scale: float,
    *args: Any,
    min_value: float | int | None = None,
    max_value: float | int | None = None,
    step: float | int | None = None,
    digits: int | None = None,
    unit: str | None = None,
    raw_min: float | int | None = None,
    raw_max: float | int | None = None,
    maker_key: str | None = None,
    maker_category: str | None = None,
    description: str | None = None,
    writable: bool | Callable[[Any], Any] = False,
    **kwargs: Any,
):
    """Create a gauge field from a manufacturer TROVIS HR reference."""
    effective_step = step if step is not None else step_from_digits(digits)
    effective_writable = _with_number_validator(
        writable,
        min_value=min_value,
        max_value=max_value,
        step=effective_step,
    )
    field = _modbus_gauge(
        register_address(hr_number),
        scale,
        *args,
        writable=effective_writable,
        unit=unit,
        **kwargs,
    )
    return attach_metadata(
        field,
        DatapointMetadata(
            value_kind="number",
            maker_reference=hr_number,
            maker_key=maker_key,
            maker_category=maker_category,
            description=description,
            writable=bool(writable),
            number=NumberMetadata(
                min_value=min_value,
                max_value=max_value,
                step=effective_step,
                digits=digits,
                unit=unit,
                raw_min=raw_min,
                raw_max=raw_max,
            ),
        ),
    )


def time_value(
    hr_number: int,
    *,
    min_value: datetime.time,
    max_value: datetime.time,
    raw_min: int,
    raw_max: int,
    writable: bool = False,
    maker_key: str | None = None,
    maker_category: str | None = None,
    description: str | None = None,
) -> RegisterField[datetime.time]:
    """Create a native minute-resolution time field from a TROVIS HR."""
    field = PackedTimeField(
        register_address(hr_number),
        min_value=min_value,
        max_value=max_value,
        raw_min=raw_min,
        raw_max=raw_max,
        writable=writable,
    )
    return attach_metadata(
        field,
        DatapointMetadata(
            value_kind="time",
            maker_reference=hr_number,
            maker_key=maker_key,
            maker_category=maker_category,
            description=description,
            writable=writable,
            temporal=TemporalMetadata(
                resolution="minute",
                min_value=min_value,
                max_value=max_value,
                raw_min=raw_min,
                raw_max=raw_max,
            ),
        ),
    )


def month_day_value(
    hr_number: int,
    *,
    min_value: MonthDay,
    max_value: MonthDay,
    raw_min: int,
    raw_max: int,
    writable: bool = False,
    maker_key: str | None = None,
    maker_category: str | None = None,
    description: str | None = None,
) -> RegisterField[MonthDay]:
    """Create a native recurring-date field from a packed TROVIS DDMM HR."""
    field = PackedMonthDayField(
        register_address(hr_number),
        min_value=min_value,
        max_value=max_value,
        raw_min=raw_min,
        raw_max=raw_max,
        writable=writable,
    )
    return attach_metadata(
        field,
        DatapointMetadata(
            value_kind="month_day",
            maker_reference=hr_number,
            maker_key=maker_key,
            maker_category=maker_category,
            description=description,
            writable=writable,
            temporal=TemporalMetadata(
                resolution="day",
                min_value=min_value,
                max_value=max_value,
                raw_min=raw_min,
                raw_max=raw_max,
            ),
        ),
    )


def date_value(
    hr_number: int,
    *,
    min_value: datetime.date,
    max_value: datetime.date,
    raw_min: int,
    raw_max: int,
    writable: bool = False,
    maker_key: str | None = None,
    maker_category: str | None = None,
    description: str | None = None,
) -> RegisterField[datetime.date]:
    """Create a native date from adjacent TROVIS DDMM and year registers."""
    field = PackedDateField(
        register_address(hr_number),
        min_value=min_value,
        max_value=max_value,
        raw_min=raw_min,
        raw_max=raw_max,
        writable=writable,
    )
    return attach_metadata(
        field,
        DatapointMetadata(
            value_kind="date",
            maker_reference=hr_number,
            maker_key=maker_key,
            maker_category=maker_category,
            description=description,
            writable=writable,
            temporal=TemporalMetadata(
                resolution="day",
                min_value=min_value,
                max_value=max_value,
                raw_min=raw_min,
                raw_max=raw_max,
            ),
        ),
    )


def enum(
    hr_number: int,
    enum_type: type[IntEnum],
    *args: Any,
    options: tuple[OptionMetadata, ...] | None = None,
    maker_key: str | None = None,
    maker_category: str | None = None,
    description: str | None = None,
    writable: bool | Callable[[Any], Any] = False,
    **kwargs: Any,
):
    """Create an enum field from a manufacturer TROVIS HR reference."""
    field = _modbus_enum(
        register_address(hr_number),
        enum_type,
        *args,
        writable=writable,
        **kwargs,
    )
    resolved_options = options or tuple(
        OptionMetadata(member.name.lower(), int(member), member.name)
        for member in enum_type
    )
    return attach_metadata(
        field,
        DatapointMetadata(
            value_kind="enum",
            maker_reference=hr_number,
            maker_key=maker_key,
            maker_category=maker_category,
            description=description,
            writable=bool(writable),
            enum=EnumMetadata(enum_type=enum_type, options=resolved_options),
        ),
    )


def coil(
    cl_number: int,
    *,
    stride: int = 0,
    writable: bool = False,
    false_key: str = "off",
    true_key: str = "on",
    false_label: str | None = None,
    true_label: str | None = None,
    inverted: bool = False,
    maker_key: str | None = None,
    maker_category: str | None = None,
    description: str | None = None,
):
    """Create a coil field from a manufacturer TROVIS CL number."""
    field = _modbus_coil(
        coil_address(cl_number),
        stride=stride,
        writable=writable,
    )
    return attach_metadata(
        field,
        DatapointMetadata(
            value_kind="boolean",
            maker_reference=cl_number,
            maker_key=maker_key,
            maker_category=maker_category,
            description=description,
            writable=writable,
            boolean=BooleanMetadata(
                false_key=false_key,
                true_key=true_key,
                false_label=false_label,
                true_label=true_label,
                inverted=inverted,
            ),
        ),
    )


def temperature(
    hr_number: int,
    *,
    stride: int = 0,
    writable: bool = False,
    unit: str = "°C",
    min_value: float | int | None = None,
    max_value: float | int | None = None,
    step: float | int | None = None,
    digits: int | None = None,
    raw_min: float | int | None = None,
    raw_max: float | int | None = None,
    maker_key: str | None = None,
    maker_category: str | None = None,
    description: str | None = None,
) -> RegisterField[float]:
    """A signed 0.1-scaled temperature register with the Trovis NaN sentinel."""
    return gauge(
        hr_number,
        0.1,
        signed=True,
        nan=NAN_INT16,
        stride=stride,
        writable=writable,
        unit=unit,
        min_value=min_value,
        max_value=max_value,
        step=step,
        digits=digits,
        raw_min=raw_min,
        raw_max=raw_max,
        maker_key=maker_key,
        maker_category=maker_category,
        description=description,
    )


async def async_read_writing_enabled(unit: Any) -> bool:
    """Return whether TROVIS write access appears to be active."""
    try:
        return (
            await unit.read_holding_registers(
                register_address(WRITE_ACCESS_REGISTER),
                1,
            )
        )[0] != WRITE_ACCESS_DISABLE_CODE
    except ModbusError as err:
        raise TrovisWriteAccessError(
            "Could not read TROVIS write access state"
        ) from err


async def async_enable_writing(
    unit: Any,
    access_code: int = DEFAULT_WRITE_ACCESS_CODE,
) -> None:
    """Enable TROVIS writing globally."""
    try:
        await unit.write_register(register_address(WRITE_ACCESS_REGISTER), access_code)
    except ModbusError as err:
        raise TrovisWriteAccessError("Could not enable TROVIS write access") from err


async def async_disable_writing(unit: Any) -> None:
    """Disable TROVIS writing globally."""
    try:
        await unit.write_register(
            register_address(WRITE_ACCESS_REGISTER),
            WRITE_ACCESS_DISABLE_CODE,
        )
    except ModbusError as err:
        raise TrovisWriteAccessError("Could not reset TROVIS write access") from err


async def async_ensure_writing_enabled(
    unit: Any,
    access_code: int = DEFAULT_WRITE_ACCESS_CODE,
) -> None:
    """Ensure that the TROVIS access code is active for the next write."""
    try:
        await unit.write_register(register_address(WRITE_ACCESS_REGISTER), access_code)
    except ModbusError as err:
        raise TrovisWriteAccessError("Could not refresh TROVIS write access") from err


class TrovisComponent(Component):
    """A Trovis sub-system: readable ranges + the Ebene write-unlock quirk.

    Some writable values are ignored over Modbus unless their "Ebene" override
    coil is first released to 0 (= GLT / remote control). Subclasses list those
    in :attr:`ebene_coils`.
    """

    register_ranges = REGISTER_RANGES
    coil_ranges = COIL_RANGES
    max_span = 50

    # Writable fields whose write must first change an Ebene override coil.
    ebene_coils: dict[str, tuple[int, int]] = {}

    # Values that restore autonomous controller operation through the Ebene
    # coil instead of being written to the corresponding holding register.
    ebene_autark_values: dict[str, Any] = {"mode": OperatingMode.AUTOMATIC}

    def _ensure_read_layout_is_configurable(self) -> None:
        """Reject availability changes after the read layout was built."""
        cached_layout = {"_read_items"} & self.__dict__.keys()
        if self.__dict__.get("_plan") is not None:
            cached_layout.add("_plan")
        if cached_layout:
            names = ", ".join(sorted(cached_layout))
            raise RuntimeError(
                "read availability must be configured before the first read "
                f"layout is built (already cached: {names})"
            )

    def configure_readable_ranges(
        self,
        register_ranges: tuple[tuple[int, int], ...],
        coil_ranges: tuple[tuple[int, int], ...],
    ) -> None:
        """Keep only fields whose complete spans are readable for the model."""
        self._ensure_read_layout_is_configurable()
        self.register_ranges = register_ranges
        self.coil_ranges = coil_ranges

        declared_registers = type(self)._register_fields
        self._register_fields = {
            name: descriptor
            for name, descriptor in declared_registers.items()
            if self._register_field_is_readable(descriptor, register_ranges)
        }

        declared_bits = type(self)._bit_fields
        self._bit_fields = {
            name: descriptor
            for name, descriptor in declared_bits.items()
            if is_span_readable(
                self._address(descriptor),
                getattr(descriptor, "count", 1),
                coil_ranges,
            )
        }

    def configure_readable_fields(self, field_names: Iterable[str]) -> None:
        """Limit one component instance to a declared set of field names.

        Ranges remain the coarse address-availability map. This optional second
        filter removes unsupported logical views that share an otherwise valid
        address, for example model-specific sensor aliases.
        """
        self._ensure_read_layout_is_configurable()
        allowed = frozenset(field_names)
        self._register_fields = {
            name: descriptor
            for name, descriptor in self._register_fields.items()
            if name in allowed
        }
        self._bit_fields = {
            name: descriptor
            for name, descriptor in self._bit_fields.items()
            if name in allowed
        }

    def _register_field_is_readable(
        self,
        descriptor: RegisterField[Any],
        register_ranges: tuple[tuple[int, int], ...],
    ) -> bool:
        """Return whether a register field and its scale register are readable."""
        if not is_span_readable(
            self._address(descriptor),
            descriptor.count,
            register_ranges,
        ):
            return False

        if descriptor.scale_register is None:
            return True

        return is_span_readable(self._scale_address(descriptor), 1, register_ranges)

    @property
    def readable_field_names(self) -> frozenset[str]:
        """Return fields selected by the current model's range profile."""
        return frozenset((*self._register_fields, *self._bit_fields))

    def is_field_readable(self, field: str) -> bool:
        """Return whether ``field`` is part of this instance's read layout."""
        return field in self._register_fields or field in self._bit_fields

    def metadata_for(self, field: str) -> DatapointMetadata | None:
        """Return neutral TROVIS metadata for a declared field."""
        descriptor = type(self).declared_fields.get(field)
        if descriptor is None:
            return None
        return getattr(descriptor, "trovis_metadata", None)

    def require_metadata_for(self, field: str) -> DatapointMetadata:
        """Return TROVIS metadata for a field or raise."""
        metadata = self.metadata_for(field)
        if metadata is None:
            raise AttributeError(f"unknown or untyped TROVIS field {field!r}")
        return metadata

    async def write(self, field: str, value: Any) -> None:
        """Write a field, applying field-specific TROVIS preconditions.

        Most overridden fields first switch their Ebene coil to ``GLT`` and
        then write the requested register value. Operating mode ``AUTOMATIC``
        is the inverse operation: it restores ``AUTARK`` and deliberately
        leaves the holding register untouched.
        """
        if (override := self.ebene_coils.get(field)) is not None:
            address, stride = override
            coil = coil_address(address + stride * (self._index - 1))

            if (
                field in self.ebene_autark_values
                and value == self.ebene_autark_values[field]
            ):
                await self._unit.write_coil(coil, LEVEL_AUTARK)
                return

            await self._unit.write_coil(coil, LEVEL_GLT)

        await super().write(field, value)

    async def async_write_datapoint(
        self,
        field: str,
        value: Any,
        *,
        access_code: int = DEFAULT_WRITE_ACCESS_CODE,
    ) -> None:
        """Write a TROVIS data point.

        This is the public write entry point for integrations. It refreshes the
        access code and then delegates to the generic component write path.
        """
        await async_ensure_writing_enabled(self._unit, access_code)
        await self.write(field, value)
