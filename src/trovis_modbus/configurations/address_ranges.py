"""Model-specific readable TROVIS Modbus ranges.

Definitions use manufacturer references:

- holding-register references such as HR40102
- coil references such as CL137

Known gaps and manufacturer block boundaries are preserved intentionally. Both
bound a read: an address no range claims keeps a pooled read off it, and the
boundary between two touching ranges keeps a pooled read from spanning them.
"""

from __future__ import annotations

from ..addresses import cl_range, hr_range

TWO_CONTROL_CIRCUIT_MODELS = frozenset({5573, 55731, 5575, 5576})
THREE_CONTROL_CIRCUIT_MODELS = frozenset({5578, 55781, 5579})
SUPPORTED_MODELS = TWO_CONTROL_CIRCUIT_MODELS | THREE_CONTROL_CIRCUIT_MODELS


def _hr_ranges(
    *ranges: tuple[int, int],
) -> tuple[tuple[int, int], ...]:
    """Convert manufacturer HR ranges to Modbus PDU ranges."""
    return tuple(hr_range(start, end) for start, end in ranges)


def _cl_ranges(
    *ranges: tuple[int, int],
) -> tuple[tuple[int, int], ...]:
    """Convert manufacturer CL ranges to Modbus PDU ranges."""
    return tuple(cl_range(start, end) for start, end in ranges)


# TROVIS 5573 Rev. 2.54.
# Also used as the initial safe profile for the two-Rk models 5575 and 5576.
REGISTER_RANGES_2_RK = _hr_ranges(
    (40001, 40006),
    (40010, 40031),
    (40034, 40043),
    (40070, 40085),
    (40099, 40125),
    (40133, 40163),
    (40300, 40320),
    (40900, 40932),
    (41000, 41045),
    (41046, 41072),
    (41090, 41104),
    (41200, 41244),
    (41254, 41272),
    (41800, 41809),
    (41810, 41813),
    (41827, 41850),
    (41863, 41871),
    (42000, 42001),
    (42200, 42203),
    (46400, 46429),
    (46470, 46499),
    (46500, 46530),
    (46531, 46562),
    (46563, 46593),
    (46594, 46624),
    (46625, 46658),
    (46750, 46780),
    (46781, 46812),
    (46813, 46843),
    (46844, 46874),
    (46875, 46908),
    (47000, 47030),
    (47031, 47062),
    (47063, 47093),
    (47094, 47124),
    (47125, 47158),
    (47250, 47280),
    (47281, 47312),
    (47313, 47343),
    (47344, 47374),
    (47375, 47408),
    (47500, 47530),
    (47531, 47562),
    (47563, 47593),
    (47594, 47624),
    (47625, 47658),
    (47750, 47780),
    (47781, 47812),
    (47813, 47843),
    (47844, 47874),
    (47875, 47908),
    (48000, 48030),
    (48031, 48062),
    (48063, 48093),
    (48094, 48124),
    (48125, 48158),
    (48250, 48280),
    (48281, 48312),
    (48313, 48343),
    (48344, 48374),
    (48375, 48408),
    (48500, 48530),
    (48531, 48562),
    (48563, 48593),
    (48594, 48624),
    (48625, 48658),
    (48750, 48780),
    (48781, 48812),
    (48813, 48843),
    (48844, 48874),
    (48875, 48908),
    (49000, 49030),
    (49031, 49062),
    (49063, 49093),
    (49094, 49124),
    (49125, 49158),
    (49250, 49280),
    (49281, 49312),
    (49313, 49343),
    (49344, 49374),
    (49375, 49408),
)

COIL_RANGES_2_RK = _cl_ranges(
    (1, 9),
    (10, 18),
    (22, 23),
    (33, 34),
    (57, 67),
    (88, 113),
    (116, 119),
    (130, 144),
    (145, 172),
    (246, 255),
    (300, 309),
    (401, 422),
    (500, 531),
    (601, 620),
    (801, 802),
    (901, 928),
    (998, 1009),
    (1025, 1046),
    (1200, 1213),
    (1225, 1238),
    (1800, 1812),
    (1825, 1845),
    (2101, 2124),
    (2201, 2224),
    (9910, 9910),
)


# TROVIS 5578 Rev. 2.62 final.
# Also used as the initial safe profile for 5578-E and 5579.
REGISTER_RANGES_3_RK = _hr_ranges(
    (40001, 40006),
    (40010, 40032),
    (40034, 40054),
    (40057, 40085),
    (40099, 40125),
    (40130, 40142),
    (40143, 40167),
    (40201, 40215),
    (40300, 40320),
    (40500, 40513),
    (40700, 40712),
    (40900, 40932),
    (41000, 41045),
    (41046, 41072),
    (41090, 41105),
    (41200, 41244),
    (41249, 41272),
    (41400, 41444),
    (41449, 41472),
    (41800, 41807),
    (41808, 41813),
    (41827, 41850),
    (41863, 41871),
    (41900, 41903),
    (42000, 42003),
    (42200, 42203),
    (42400, 42403),
    (46400, 46433),
    (46470, 46478),
    (46488, 46494),
    (46500, 46530),
    (46531, 46562),
    (46563, 46593),
    (46594, 46624),
    (46625, 46658),
    (46750, 46772),
    (46775, 46782),
    (46786, 46793),
    (46798, 46874),
    (46875, 46908),
    (47000, 47030),
    (47031, 47062),
    (47063, 47093),
    (47094, 47124),
    (47125, 47158),
    (47250, 47272),
    (47275, 47282),
    (47286, 47293),
    (47298, 47374),
    (47375, 47408),
    (47500, 47530),
    (47531, 47562),
    (47563, 47593),
    (47594, 47624),
    (47625, 47658),
    (47750, 47772),
    (47775, 47782),
    (47786, 47793),
    (47798, 47874),
    (47875, 47908),
)

COIL_RANGES_3_RK = _cl_ranges(
    (1, 9),
    (10, 18),
    (22, 23),
    (24, 40),
    (57, 67),
    (88, 113),
    (114, 121),
    (122, 144),
    (145, 172),
    (176, 215),
    (222, 238),
    (245, 255),
    (300, 309),
    (322, 338),
    (401, 427),
    (501, 537),
    (601, 631),
    (701, 733),
    (801, 817),
    (901, 929),
    (998, 1010),
    (1025, 1046),
    (1200, 1213),
    (1224, 1238),
    (1400, 1413),
    (1424, 1438),
    (1800, 1812),
    (1825, 1845),
    (2101, 2128),
    (2201, 2224),
    (2301, 2328),
    (3101, 3128),
    (3201, 3228),
    (3301, 3328),
    (4000, 4016),
    (4100, 4123),
    (4200, 4209),
    (6000, 6001),
    (9910, 9914),
)


def is_span_readable(
    address: int,
    count: int,
    ranges: tuple[tuple[int, int], ...],
) -> bool:
    """Return whether one complete field span lies in a readable range.

    ``modbus-connection`` uses readable ranges as block-planning boundaries.
    TROVIS additionally uses them as the static availability map: fields outside
    the selected model profile must not be queried as isolated reads.
    """
    if count <= 0:
        raise ValueError(f"field count must be positive, got {count}")

    end = address + count - 1
    return any(low <= address and end <= high for low, high in ranges)


def control_circuit_count(model: int) -> int:
    """Return the number of built-in Rk1-Rk3 control circuits."""
    if model in TWO_CONTROL_CIRCUIT_MODELS:
        return 2
    if model in THREE_CONTROL_CIRCUIT_MODELS:
        return 3
    raise ValueError(f"Unsupported TROVIS model: {model}")


def ranges_for_model(
    model: int,
) -> tuple[
    tuple[tuple[int, int], ...],
    tuple[tuple[int, int], ...],
]:
    """Return register and coil ranges for a TROVIS model."""
    if model in TWO_CONTROL_CIRCUIT_MODELS:
        return REGISTER_RANGES_2_RK, COIL_RANGES_2_RK
    if model in THREE_CONTROL_CIRCUIT_MODELS:
        return REGISTER_RANGES_3_RK, COIL_RANGES_3_RK
    raise ValueError(f"Unsupported TROVIS model: {model}")


# Backwards-compatible default for components instantiated without a device.
REGISTER_RANGES = REGISTER_RANGES_3_RK
COIL_RANGES = COIL_RANGES_3_RK
