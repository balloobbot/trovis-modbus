"""The controller's date and time, as native ``datetime`` objects."""

from __future__ import annotations

import datetime
from typing import Any

from ..data_model import TrovisComponent, date_value, raw_register, time_value


class Clock(TrovisComponent):
    """Controller clock, exposed as native ``date`` / ``time`` / ``datetime``."""

    time = time_value(
        40100,
        writable=True,
        min_value=datetime.time(0, 0),
        max_value=datetime.time(23, 59),
        raw_min=0,
        raw_max=2359,
        maker_key="Uhrzeit",
        maker_category="ALG-DAT",
        description="Uhrzeit",
    )

    date = date_value(
        40101,
        writable=True,
        min_value=datetime.date(2000, 1, 1),
        max_value=datetime.date(2098, 12, 31),
        raw_min=101,
        raw_max=3112,
        maker_key="Datum",
        maker_category="ALG-DAT",
        description="Datum",
    )

    year = raw_register(
        40102,
        writable=True,
        min_value=2000,
        max_value=2098,
        raw_min=2000,
        raw_max=2098,
        digits=0,
        maker_key="Jahr",
        maker_category="ALG-DAT",
        description="Jahr",
    )

    @property
    def datetime(self) -> datetime.datetime | None:
        """Combined local controller date and time."""
        moment = self.time
        day = self.date
        if day is None or moment is None:
            return None
        return datetime.datetime.combine(day, moment)

    async def write(self, field: str, value: Any) -> None:
        """Write dates in the year-first order used by the TROVIS tools."""
        if field != "date":
            await super().write(field, value)
            return

        # resolved_fields reports where the field actually lands on the device.
        resolved = self.resolved_fields[field]
        raw_date, year = resolved.field.encode(value)

        # 55Pro writes the year first and DDMM afterwards. Keep that proven
        # sequence instead of relying on one FC16 request across both words.
        await self._unit.write_register(resolved.address + 1, year)
        await self._unit.write_register(resolved.address, raw_date)

    async def set_time(self, value: datetime.time) -> None:
        """Set the controller clock time at minute resolution."""
        await self.async_write_datapoint("time", value)

    async def set_date(self, value: datetime.date) -> None:
        """Set the controller calendar date."""
        await self.async_write_datapoint("date", value)

    async def set_datetime(self, value: datetime.datetime) -> None:
        """Set controller date and time from one naive local datetime."""
        if value.tzinfo is not None:
            raise ValueError("TROVIS controller datetime must be timezone-naive")
        await self.set_date(value.date())
        await self.set_time(value.time())
