# spektralwerk_scpi_client

[![style and lint](https://github.com/silicann/spektralwerk-scpi-client/actions/workflows/style.yml/badge.svg)](https://github.com/silicann/spektralwerk-scpi-client/actions/workflows/style.yml)
[![Upload to PyPI](https://github.com/silicann/spektralwerk-scpi-client/actions/workflows/pypi-publish.yml/badge.svg)](https://github.com/silicann/spektralwerk-scpi-client/actions/workflows/pypi-publish.yml)

`spektralwerk_scpi_client` is a [Python](https://python.org/) library for communicating with [Spektralwerk NIR spectrometers](https://www.en.silicann.com/spectrometers/spektralwerk-core-nir-spectrometer/) via their [SCPI interface](https://en.wikipedia.org/wiki/Standard_Commands_for_Programmable_Instruments).

The library supports all available configuration settings as well as the retrieval of spectral data.

The API supports two ways of obtaining spectra:

- single spectrum mode: returns a single spectrum upon request. Intended for use cases like exploratory spectroscopy in the lab or requests triggered by the trigger in interface
- streaming streaming mode: returns a continuous stream of spectral information. Intended for process analytics, in-line spectrometry in production and other situations demanding very high sample rates.

## Supported Devices

- Spektralwerk Core
  - set/get exposure time
  - set/get average number
  - set/get offset voltage
  - set/get light and dark reference spectrum
  - get pixel count and wavelengths array of the spectrometer
  - get single/averaged raw spectrum and continuous emisison of spectra
  - configuration of processing steps
    - set/get output format of the Spektralwerk Core
    - set/get the number of emitted spectra
    - set/get region-of-interest
    - set/get binning width

## Requirements

- Python3
- [hatch](https://hatch.pypa.io/) for development (e.g. `pipx install hatch`)
- [bump-my-version](https://github.com/callowayproject/bump-my-version) for semantic verioning

## Usage

`spektralwerk-scpi-client` is available via [PyPI](https://pypi.org/project/spektralwerk-scpi-client/). To install `spektralwerk-scpi-client` use `pip`:

```shell
pip install spektralwerk-scpi-client
```

## Example Usage

An example can be found in the [`examples`](./examples/) directory.

```shell
export SPW_HOST="<hostname or IP>"
export SPW_PORT="<port number>"
hatch run examples:spw_core_demo
```

## Development

`bump-my-version` for increasing version of `spektralwerk-scpi-client`.
The configuration of `bump-my-version` is located in `.bumpversion.toml` and `pyproject.toml`.
To increase the version these commands can be used:

```shell
# Create a new release.
hatch run version {major|minor|patch}
```

## License

`spektralwerk_scpi_client` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
