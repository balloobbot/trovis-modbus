"""Global physical and analog sensor inputs."""

from __future__ import annotations

from ..data_model import NAN_INT16, TrovisComponent, gauge, integer, temperature


class Sensors(TrovisComponent):
    """Physical sensors. Naming follows the manufacturer abbreviations."""

    af1 = temperature(40010)  # Außenfühler 1
    af2 = temperature(40011)  # Außenfühler 2

    vf1 = temperature(40013)  # Vorlauffühler 1
    vf2 = temperature(40014)  # Vorlauffühler 2
    vf3 = temperature(40015)  # Vorlauffühler 3
    vf4 = temperature(40016)  # Vorlauffühler 4

    ruef1 = temperature(40017)  # Rücklauffühler 1
    ruef2 = temperature(40018)  # Rücklauffühler 2
    ruef3 = temperature(40019)  # Rücklauffühler 3

    rf1 = temperature(40020)  # Raumfühler 1
    rf2 = temperature(40021)  # Raumfühler 2
    rf3 = temperature(40022)  # Raumfühler 3

    sf1 = temperature(40023)  # Speicherfühler 1
    sf2 = temperature(40024)  # Speicherfühler 2
    sf3 = temperature(40025)  # Speicherfühler 3

    ae1 = gauge(  # AnalogEingang 0-10V 1
        40026,
        0.1,
        signed=True,
        nan=NAN_INT16,
        min_value=-5,
        max_value=2000,
        digits=1,
        maker_key="AE1",
        maker_category="FÜH-FG",
        description="Analogeingang AE1",
    )
    fg1 = gauge(  # FernGeber 1 (alternative ae1)
        40026,
        0.1,
        signed=True,
        nan=NAN_INT16,
        min_value=-5,
        max_value=2000,
        digits=1,
        maker_key="FG1",
        maker_category="FÜH-FG",
        description="Ferngeber FG1",
    )

    ae2 = gauge(  # AnalogEingang 0-10V 2
        40027,
        0.1,
        signed=True,
        nan=NAN_INT16,
        min_value=-5,
        max_value=2000,
        digits=1,
        maker_key="AE2",
        maker_category="FÜH-FG",
        description="Analogeingang AE2",
    )
    fg2 = gauge(  # FernGeber 2 (alternative ae2)
        40027,
        0.1,
        signed=True,
        nan=NAN_INT16,
        min_value=-5,
        max_value=2000,
        digits=1,
        maker_key="FG2",
        maker_category="FÜH-FG",
        description="Ferngeber FG2",
    )

    ae3 = gauge(  # AnalogEingang 0-10V 3
        40028,
        0.1,
        signed=True,
        nan=NAN_INT16,
        min_value=-5,
        max_value=2000,
        digits=1,
        maker_key="AE3",
        maker_category="FÜH-FG",
        description="Analogeingang AE3",
    )
    fg3 = gauge(  # FernGeber 3 (alternative ae3)
        40028,
        0.1,
        signed=True,
        nan=NAN_INT16,
        min_value=-5,
        max_value=2000,
        digits=1,
        maker_key="FG3",
        maker_category="FÜH-FG",
        description="Ferngeber FG3",
    )

    pulse_rate = integer(
        40029,
        signed=False,
        min_value=0,
        max_value=1000,
        digits=0,
        unit="Imp/h",
        maker_key="Meßwert_Imp-h",
        maker_category="ALG-VOL",
        description="Impulsrate am Eingang Klemme 17/18",
    )

    analog_input_voltage = gauge(
        40042,
        0.01,
        signed=False,
        min_value=0,
        max_value=10,
        digits=2,
        unit="V",
        maker_key="AE_0-10V",
        maker_category="FÜH-EA",
        description="Analogeingang 0 bis 10 V",
    )
    analog_input_current = gauge(
        40042,
        0.2,
        signed=False,
        min_value=0,
        max_value=20,
        digits=1,
        unit="mA",
        maker_category="FÜH-EA",
        description="Analogeingang 0 bis 20 mA über 50-Ω-Shunt",
    )

    @property
    def detected_sensor_names(self) -> tuple[str, ...]:
        """Return sensor fields that currently have a valid value."""
        return tuple(
            name for name in self.resolved_fields if getattr(self, name) is not None
        )
