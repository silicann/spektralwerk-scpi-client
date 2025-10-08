# Changelog

All notable changes of the `spektralwerk_scpi_client` will be documented in this file

## [0.3.0] - 2025-10-08

### Added

- Extend the available SCPI commands
  - Dark reference
  - Light reference
  - Adjust processing steps to the in-band spectral data delivery

### Changed

- Remove unit separation since the unit is no longer appended to value query


## [0.2.4] - 2025-08-05

### Fixed

- added missing SCPI queries for offset voltage and exposure time unit

## [0.2.3] - 205-08-05

### Added

- SCPI endpoint for unit request

### Changed

- Exposure time is delivered in seconds (previously µs were used)

## [0.2.2] - 2025-06-24

### Changed

- Wavelength SCPI endpoint naming

## [0.2.1] - 2025-06-20

### Added

- Individual timeout for each function can be set

## [0.2.0] - 2025-06-19

### Added

- Extend the available SCPI commands (offset voltage, min/max values for exposure time and average number)
  - Offset voltage
  - Min/max for average number and exposure time
  - Maximum spectrometer count value
  - Averaged spectrometer resolution
  - Averaged raw spectra
- Error handling (read the `*ESR` and the error queue of the Spektralwerk Core)
- Streaming of spectra capability (by continuous rrequest of single spectra)

## [0.1.0] - 2025-05-27

### Added

- Basic functions of the Spektralwerk Core (exposure time, average number, single raw spectrum)
