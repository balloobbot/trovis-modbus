# `trovis-modbus` Python library

[![CI](https://github.com/Tom-Bom-badil/trovis-modbus/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/Tom-Bom-badil/trovis-modbus/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/trovis-modbus.svg)](https://pypi.org/project/trovis-modbus/)
[![Python](https://img.shields.io/pypi/pyversions/trovis-modbus.svg)](https://pypi.org/project/trovis-modbus/)
[![License](https://img.shields.io/github/license/Tom-Bom-badil/trovis-modbus.svg)](LICENSE)

<img width="100%" alt="SAMSON TROVIS controllers" src="https://raw.githubusercontent.com/wiki/Tom-Bom-badil/trovis-modbus/images/cover_pic.png" />

<br/>`trovis-modbus` is an asynchronous Python library for reading from and writing to **SAMSON TROVIS 557x** heating and district heating controllers over Modbus (compatible OEM controller variants from SAUTER, YADOS and PEWO are also covered, see below).

## Purpose and scope of this library

The library `trovis-modbus`:

- is intended for operational monitoring, and occasional fine tuning of already commissioned heating systems. It does _NOT_ attempt to reproduce every single controller menu, parameter level, special function, register or coil (there are literally thousands of them). It is also not meant as an initial commissioning tool for new heating systems - use the free SAMSON TrovisView for this.
- provides the auto-discovery and auto-configuration logic required to determine the controller model and its capabilities, the configured hydronic system, the sensor and input assignments, and the relevant controller functions, parameters, and configuration settings.
- contains the controller-specific data model. It knows the available
registers and coils, their data types and metadata, and the rules required for safe reads and writes.
- does _NOT_ create or own the Modbus transport. Applications utilizing the library provide a [`modbus_connection.ModbusUnit`](https://github.com/home-assistant-libs/modbus-connection) and may use any backend supported by `modbus-connection` (pymodbus, tmodbus, ...). Since `modbus-connection` 4.0 a connection manages its own link: it connects on demand and re-establishes itself after a drop, over the same unit handle. An application does not have to rebuild the `Trovis557x` object (nor, in Home Assistant, reload its config entry) when the link goes down.

## Data provided by the library

Depending on the controller model and its configuration, `trovis-modbus` provides:

- controller identity, firmware, hardware, serial, and system information,
- current hydronic system,
- measured temperatures and other physical sensor inputs (analog, pulse etc),
- controller-wide functions and parameters,
- technical control circuits Rk1 through Rk4 and their hydronic roles and data<br/>
  (known roles: pre-control, heating, domestic hot water, buffer, solar),
- operating modes, setpoints, pump and valve states, and controller date/time,
- selected derived operating states (incl. heating curves for each heating circuit),
- neutral datapoint metadata such as unit, scale, limits, step, enum options,<br/>
  invalid values, and writable state,
- grouped reads and validated writes with TROVIS write-access handling<br/>(including the mechanisms needed to write-enable 'special/protected' registers).

The exact datapoints available on a device depend on the controller model, the
selected hydronic system, active functions and parameters, and the sensor and
input assignments configured for the connected physical sensors.

## Supported controllers

| Controller                | Rk1-Rk3 / Heating | Rk4 / DHW | Hydronic systems | Comments                             |
| :------------------------ | :--------------: | :-----: | :--------------: | :------------------------------------|
| SAMSON TROVIS 5573        |                2 |    x    |               29 |                                      |
| SAMSON TROVIS 5573-1      |                2 |    x    |               29 |                                      |
| SAMSON TROVIS 5575        |                2 |    x    |               33 |                                      |
| SAMSON TROVIS 5576        |                2 |    x    |               52 |                                      |
| SAMSON TROVIS 5578        |                3 |    x    |               90 |                                      |
| SAMSON TROVIS 5578-E      |                3 |    x    |               95 |                                      |
| SAMSON TROVIS 5579        |                3 |    x    |               85 |                                      |
| SAUTER EQJW126F001        |                1 |         |                1 | TROVIS 5573, Rk1 and Anlage 1.0 only |
| SAUTER EQJW146F001        |                2 |    x    |               29 | TROVIS 5573                          |
| SAUTER EQJW146F002        |                2 |    x    |               29 | TROVIS 5573-1                        |
| SAUTER EQJW246F002        |                3 |    x    |               90 | TROVIS 5578                          |
| SAUTER EQJW246F003        |                3 |    x    |               95 | TROVIS 5578-E                        |
| YADOS YADO\|MATIC 01      |                2 |    x    |               33 | TROVIS 5575                          |
| YADOS YADO\|MATIC 01-0003 |                2 |    x    |               33 | TROVIS 5575                          |
| YADOS YADO\|MATIC 03      |                2 |    x    |               29 | TROVIS 5573                          |
| YADOS YADO\|MATIC 03-1003 |                2 |    x    |               29 | TROVIS 5573-1                        |
| YADOS YADO\|MATIC 08      |                3 |    x    |               90 | TROVIS 5578-1114                     |
| PEWO PCR06                |                2 |    x    |               33 | TROVIS 5575                          |

<sup>Note: The non-SAMSON models have not yet been tested. The figures are based on the currently available documentation.</sup>

Other compatible OEM controllers will likely work, based on the TROVIS model identity they provide. OEM controllers return and use the corresponding TROVIS model profile and are not maintained with separate datapoint definitions.

## Testing and validation

All releases of the library are tested with the following hardware setup:

- 1× `TROVIS 5576`: live heating controller, Anlage 2.1 (4 required + 4 additional Pt1000 sensors),
- 1× `TROVIS 5578`: dedicated testing device, Anlage 6.1 (fully equipped with 17 Pt1000 sensors),
- 1× `TROVIS 5579`: dedicated testing device, Anlage 5.1 (fully equipped
  with 17 Pt1000 sensors).

Additional software-based tests are part of the project to ensure code quality
and consistency.

## Documentation, development and contribution guidelines

Detailed architecture, usage examples, datapoint behavior, development setup,
branch workflow, contribution guidance, and known limitations are documented in
the [project wiki](https://github.com/Tom-Bom-badil/trovis-modbus/wiki).

Support for the Home Assistant integration is maintained separately in
[`trovis-modbus-hass`](https://github.com/Tom-Bom-badil/trovis-modbus-hass).