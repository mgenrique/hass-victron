[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

# Victron GX Modbus TCP for Home Assistant

A maintained and refactored fork of the Victron GX Modbus TCP integration for Home Assistant, updated to work with Python 3.12–3.14 and recent `pymodbus` versions.

This fork continues the work of the original project with significant internal changes to keep it compatible with modern Home Assistant installations and recent Victron GX firmware.

![Victron GX device](https://user-images.githubusercontent.com/61006057/227771568-78497ecc-e863-46f2-b29e-e15c7c20a154.gif)

## Project status

This integration is maintained in this fork and is intended for users who need to read data from a Victron GX device via Modbus TCP in Home Assistant.

## What this integration does

The integration connects to a Victron GX device exposed over Modbus TCP and creates Home Assistant entities based on the available registers.

- Scans for available registers on the GX device.
- Creates entities for sensors, switches, binary sensors, numbers, selects, buttons, and other supported controls.
- Provides configuration options for host, port, update interval, and advanced features.

## Compatibility

This version is adapted to work with:

- Modern Home Assistant installations (tested in HA core 2026.8.1)
- Python 3.12, 3.13, and 3.14.
- Recent `pymodbus` API changes.

The refactoring includes a new decoding strategy and compatibility with parameter name changes across `pymodbus` versions.

## Key refactoring changes

During the update of this fork, several critical issues were fixed:

- Replaced the Modbus payload decoder with a native implementation based on Python's `struct` module.
- Added compatibility with `pymodbus` API changes (`unit`, `slave`, `slave_id`, `device_id`).
- Fixed handling of slave `0`, which is the default for Cerbo GX devices.
- Improved network stability and reconnection logic.
- Correctly handled reserved or null values to avoid corrupt readings in the UI.
- Adjusted entity ID generation to maintain compatibility with existing installations.
- Reduced log noise for register blocks not supported by some devices.

A detailed summary of the refactoring (in Spanish) is available in [RESUMEN_REFACTORIZACION.md](RESUMEN_REFACTORIZACION.md).

## Installation

### Installation via HACS

1. Open HACS in Home Assistant.
2. Add this repository as a custom integration repository.
3. Search for **Victron** in HACS.
4. Install the integration.
5. Restart Home Assistant.
6. Add the integration from **Settings -> Devices & Services**.

### Manual installation

1. Clone the repository.
2. Copy the `custom_components/` folder to your Home Assistant instance.
3. Restart Home Assistant.
4. Add the integration from **Settings -> Devices & Services -> Add Integration**.

## Migrating from previous versions

If you are upgrading from an older version of the integration:

- Create a backup before updating.
- After installing this version, you may need to rescan the device if you were using Modbus ID `0`.
- In some cases, old entity names and associated history may require manual review after migration.

## Limitations

- Configuration can be slow if a full discovery scan is required.
- Some registers depend on the GX firmware version and connected devices.
- Older firmware versions may not expose all expected registers.

## Recommended requirements

It is recommended to use recent Victron firmware versions and keep Home Assistant up to date for best compatibility.

## Configuration options

### Host
IP address of the Victron GX device with the Modbus TCP service enabled.

### Port
Modbus TCP port. The default is `502`, but this can be changed if you use a proxy or port forwarding.

### Interval
Time between entity updates. On slower systems, very low intervals may cause issues.

### Write support / Advanced
Enables advanced features and write capabilities. Only use this if you know exactly which parameters you are modifying.

### AC Current
Maximum current supported by your AC installation.

### DC current
Maximum current supported by your battery and DC cabling.

### DC Voltage
DC voltage profile used to calculate battery limits and values.

### AC Voltage
AC voltage for your region. Used to automatically calculate certain power limits.

## Firmware compatibility notes

Victron adds new registers over time. On older firmware, some registers may not exist yet, which can cause certain devices not to be detected correctly.

If you encounter issues, please open an issue including:

- Connected devices.
- Firmware versions of the devices.
- Affected device type.
- Unit ID or Modbus ID involved.

## Disclaimer

This integration interacts with a real electrical system through the Victron GX device.

Use this integration at your own risk. Excessive polling frequency or misuse of write features may affect system behavior if configured incorrectly.

## Resources

- [Victron Modbus TCP FAQ](https://www.victronenergy.com/live/ccgx:modbustcp_faq)
- [Power Flow Card Plus](https://github.com/flixlix/power-flow-card-plus)

## Note about the original project

The original project was archived by its maintainer. This fork aims to keep the integration alive and compatible with the current Home Assistant and `pymodbus` ecosystem.

## Credits

- Original integration: [remcom/hass-victron](https://github.com/remcom/hass-victron)
- Earlier upstream work: [sfstar/hass-victron](https://github.com/sfstar/hass-victron)