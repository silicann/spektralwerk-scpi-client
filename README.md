# spektralwerk_scpi_client

[![style and lint](https://github.com/silicann/spektralwerk-scpi-client/actions/workflows/style.yml/badge.svg)](https://github.com/silicann/spektralwerk-scpi-client/actions/workflows/style.yml)
[![Upload to PyPI](https://github.com/silicann/spektralwerk-scpi-client/actions/workflows/pypi-publish.yml/badge.svg)](https://github.com/silicann/spektralwerk-scpi-client/actions/workflows/pypi-publish.yml)

`spektralwerk_scpi_client` is a [Python](https://python.org/) library for communicating with [Spektralwerk](https://www.silicann.com/spektrometer/) devices via their [SCPI interface](https://en.wikipedia.org/wiki/Standard_Commands_for_Programmable_Instruments).

The library supports all available configuration settings as well as the retrieval of spectral data.

## Supported Devices

- Spektralwerk Core
  - set/get exposure time
  - set/get average number
  - set/get offset voltage
  - get pixel count and wavelengths array of the spectrometer
  - get single raw spectrum and averaged raw spectrum

## Requirements

- Python3
- [hatch](https://hatch.pypa.io/) for development (e.g. `pipx install hatch`)

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

## License

`spektralwerk_scpi_client` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
