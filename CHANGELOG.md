# Changelog

All notable changes of the `spektralwerk_scpi_client` will be documented in this file

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
