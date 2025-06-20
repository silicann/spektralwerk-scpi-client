#!/usr/bin/env python3
"""
Create a SpektralwerkCore object and request the identity and change basic settings.

This example aims to provide basic usage of the `spektralwerk_scpi_client` library.

The environmental variables `SPW_HOST` and `SPW_PORT` can be used to specify host and port.
The default IP is `127.0.0.1` (localhost) and the default port is `5025`.
"""

from spektralwerk_scpi_client.devices import SpektralwerkCore

DEFAULT_HOST: str = "127.0.0.1"
DEFAULT_PORT: str = "5025"


def main(host, port):
    spw_core = SpektralwerkCore(host=host, port=port)

    # request the device identity
    identity = spw_core.get_identity()
    print(f"device identity: {identity}")

    # receive wavelength array
    wavelengths = spw_core.get_pixel_wavelengths()
    print(f"wavelength range: {wavelengths[0]} - {wavelengths[-1]}")

    # set and get the exposure time
    target_exposure_time = 100.0
    spw_core.set_exposure_time(target_exposure_time)
    current_exposure_time = spw_core.get_exposure_time()
    print(f"current exposure time: {current_exposure_time}")

    # set and get average number
    target_average_number = 100
    spw_core.set_average_number(target_average_number)
    current_average_number = spw_core.get_average_number()
    print(f"current average number: {current_average_number}")

    # retrieve 10 single raw spectra
    number_sample_spectra = 10
    spectra = []
    for spectra_count in range(number_sample_spectra):
        spectrum = next(spw_core.get_spectra())
        print(f"{spectra_count + 1}. spectrum:\n{spectrum}")
        spectra.append(spectrum)
    print(f"received {len(spectra)} spectra")

    # "stream" 100 raw spectra
    number_of_streamed_spectra = 100
    counter = 1
    for spectrum in spw_core.get_spectra():
        if counter > number_of_streamed_spectra:
            break
        print(f"{counter}:\n{spectrum}\n")
        counter += 1


if __name__ == "__main__":
    import os

    SPW_HOST = os.getenv("SPW_HOST", DEFAULT_HOST)
    SPW_PORT = os.getenv("SPW_PORT", DEFAULT_PORT)

    main(SPW_HOST, int(SPW_PORT))
