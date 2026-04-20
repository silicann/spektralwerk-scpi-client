# Changelog

All notable changes of the `spektralwerk_scpi_client` will be documented in this file


## [0.x.x] - 2026-...

### Added

- Functions for requesting output format and change the output format on the Spektralwerk Core
- Functions for requesting trigger and change trigger in the Spektralwerk Core
- A spectrum generator which does not alter the current configuration on the Spektralwerk Core
- `binning` SCPI endpoints
- Processing steps for `binning` and `roi` handling
    - Examples for `binning` and `roi` are added
- Input and output trigger handling
- Accept `base64` encoded spectra

### Changed

- Adopt current SCPI command structure for
    - exposure time
    - average number
- Rename functions
    - `get_request_cont` -> `get_count`
    - `set_request_cont` -> `set_count`
    - `set_processing` -> `set_processing`
    - `get_request_roi` -> `get_roi`
    - `set_request_roi` -> `set_roi`
    - in general, the `_config` substring was removed from function names.
- Replace `pydantic.BaseModel` with `dataclass` for `Identity`
- Replace the separate functions to obtain min/max for exposure time by a `get_exposure_time_context` function. Therefore a SCPIValueContext dataclass is introduced to provide a structured access to the context of a value, e.g. exposure time.
- Switched from `bump2version` to `bump-my-version`. In addition `makefilet` became obsolete since the release process is integrated in the `pyproject.toml` and can be triggered with `hatch run version {LEVEL}`.

### Fixed

- Tolerate empty records in a stream response. There are used as heartbeat messages for keeping the TCP connection alive.
- Handle the last spectrum in a finite spectra emission. The last spectrum lacks the delimiter. Thus, the last spectrum must be treated separately.
- Define a fallback output format. If no output format is defined by a user, the `cobs_int16` format is used as fallback output format.


## [0.4.2] - 2026-03-04

### Added

- A with-context was introduced to apply a clear structure for changing the timeout for a single action
- function to request a single raw spectrum
- `Spectrum` class is additionally exported from `device` level
- function to request a single spectrum with the request configuration applied

### Fixed

- Convert the timeout value for the backend (second value was interpreted as milliseconds)
- Upon requesting a stream, an infionite number of spectra is returned and not only one spectra (the previous default value)
- The spectral stream is interrupted once the provided `spectra_count` is reached.

## [0.4.1] - 2026-02-13

### Fixed

- Applied type hinting which prevents building

## [0.4.0] - 2026-02-13

### Added

- Add configuration for fixed number of streamed spectra
- Enable infinite stream of spectra
- Optional output format `cobs_int16`
- Provide methods to restrict the pixel returned to a region-of-interest

### Changed

- introduce pydantic BaseModel for Identity
- use SI base units for the timeout representation (changed from [ms] to [s])

## [0.3.2] - 2025-10-09

### Fixed

- Set and acquire functions does not cause an "Invalid character data" error

## [0.3.1] - 2025-10-08

### Fixed

- Fix spelling issue

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
