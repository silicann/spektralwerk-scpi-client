#!/usr/bin/env python3
"""
Provides examples of the usage of the in-band request to obtain a finite or infinite
number of spectra.

The environmental variables `SPW_HOST` and `SPW_PORT` can be used to specify host and port.
The default IP is `127.0.0.1` (localhost) and the default port is `5025`.
"""

from spektralwerk_scpi_client.devices import SpektralwerkCore
from spektralwerk_scpi_client.scpi.mnemonics import (
    OutputFormat,
    Trigger,
    TriggerOutputSource,
)

DEFAULT_HOST: str = "127.0.0.1"
DEFAULT_PORT: str = "5025"


def finite_spectra_resquest(host, port):
    """
    Usage example for requesting a finite in-band number of spectra

    This example sets a finite number of spectra, fixes the trigger and output format
    and uses the spectral stream to obtain the defined number of samples.
    """
    spw_core = SpektralwerkCore(host=host, port=port)

    # request the device identity
    identity = spw_core.get_identity()
    print(f"device identity: {identity}")

    # adjust configurations
    # return 3 spectra in a row
    # disable external trigger
    # use human readable output format
    # disable treiggering of external devices
    few_spectral_samples = 3
    spw_core.set_count(count=few_spectral_samples)
    spw_core.set_trigger_condition(trigger=Trigger.NONE)
    spw_core.set_format(output_format=OutputFormat.HUMAN)
    spw_core.set_output_source(source=TriggerOutputSource.MANUAL)

    spectrum = list(spw_core.get_configured_spectra())
    print(f"Obtained spectra: {spectrum}")


def infinite_stream_request(host, port):
    """
    Usage example for requesting an infinite in-band stream of spectra

    This example demonstrates the infinite in-band stream of spectra. In advance, the
    output format and the trigger are set.

    Be aware, the infinite stream must be ended by closing the connection from the
    client side.
    """
    spw_core = SpektralwerkCore(host=host, port=port)

    # request the device identity
    identity = spw_core.get_identity()
    print(f"device identity: {identity}")

    # adjust configuration
    # enable infinite emission of spectra
    # disable external trigger
    # use human readable output format
    # disable treiggering of external devices
    spw_core.set_count(count=0)
    spw_core.set_trigger_condition(trigger=Trigger.NONE)
    spw_core.set_format(output_format=OutputFormat.HUMAN)
    spw_core.set_output_source(source=TriggerOutputSource.MANUAL)

    for index, spectrum in enumerate(spw_core.get_configured_spectra()):
        print(f"{index}: {spectrum}")


def finite_triggered_stream(host, port):
    """
    Usage example for a triggered finite in-band stream of spectra

    This example demonstrates the triggered finite in-band stream of spectra. In
    advance, the output format and the trigger are set. In addition, a delayed output
    trigger signal is toggled, which might control additional devices (shutter, light
    source, camera, ...).

    The client can close the connection once all relevant trigger signals have been
    observed.
    """
    spw_core = SpektralwerkCore(host=host, port=port)

    # request the device identity
    identity = spw_core.get_identity()
    print(f"device identity: {identity}")

    # adjust configuration
    # configure the number of spectra which will be emitted
    # request a single spectrum
    # listen on any signal change
    number_of_spectra = 1
    spw_core.set_count(count=number_of_spectra)
    spw_core.set_trigger_condition(trigger=Trigger.INPUT_BOTH)

    # trigger an external device on each spectral emisision
    spw_core.set_output_source(source=TriggerOutputSource.SAMPLING)
    # Allow the light source controlled via the output line to warm up for 2.5 seconds
    # before the exposure begins.
    spw_core.set_output_delay(start_delay=2.5, end_delay=0)

    with spw_core.apply_temporary_timeout(30):
        for index, spec in enumerate(spw_core.get_configured_spectra()):
            print(f"{index}, {spec}")


def main(host, port):
    # request a finite number of spectra
    finite_spectra_resquest(host, port)

    # start an infinite stream
    # since we will not wait until infinite we stop the process after 10 seconds.
    infinite_process = multiprocessing.Process(
        target=infinite_stream_request,
        name="infinite stream",
        args=(
            host,
            port,
        ),
    )
    infinite_process.start()

    time.sleep(10)

    infinite_process.terminate()
    infinite_process.join()

    # start a triggered finite stream
    # The client closes the connection after 30 seconds
    finite_triggered_process = multiprocessing.Process(
        target=finite_triggered_stream,
        name="finite triggered stream",
        args=(
            host,
            port,
        ),
    )
    finite_triggered_process.start()

    time.sleep(30)

    finite_triggered_process.terminate()
    finite_triggered_process.join()


if __name__ == "__main__":
    import multiprocessing
    import os
    import time

    SPW_HOST = os.getenv("SPW_HOST", DEFAULT_HOST)
    SPW_PORT = os.getenv("SPW_PORT", DEFAULT_PORT)

    main(SPW_HOST, int(SPW_PORT))
