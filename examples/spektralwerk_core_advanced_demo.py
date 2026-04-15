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

    few_spectral_samples = 3
    current_counts = spw_core.get_count()
    print(f"Number of counts: {current_counts}")
    if current_counts != few_spectral_samples:
        spw_core.set_count(count=few_spectral_samples)
        current_counts = spw_core.get_count()
        print(f"Number of counts: {current_counts}")

    current_trigger = spw_core.get_trigger_condition()
    print(f"Current trigger: {current_trigger}")
    if current_trigger is not Trigger.NONE:
        spw_core.set_trigger_condition(trigger=Trigger.NONE)
        current_trigger = spw_core.get_trigger_condition()
        print(f"Current trigger: {current_trigger}")

    current_format = spw_core.get_format()
    print(f"Current format: {current_format}")
    if current_format is not OutputFormat.HUMAN:
        spw_core.set_format(output_format=OutputFormat.HUMAN)
        current_format = spw_core.get_format()
        print(f"Current format: {current_format}")

    # disables output trigger if enabled since the timeout must be adjusted otherwise
    current_output_source = spw_core.get_output_source()
    if current_output_source is not TriggerOutputSource.MANUAL:
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

    current_counts = spw_core.get_count()
    print(f"Number of counts: {current_counts}")
    if current_counts != 0:
        spw_core.set_count(count=0)
        current_counts = spw_core.get_count()
        print(f"Number of counts: {current_counts}")

    current_trigger = spw_core.get_trigger_condition()
    print(f"Current trigger: {current_trigger}")
    if current_trigger is not Trigger.NONE:
        spw_core.set_trigger_condition(trigger=Trigger.NONE)
        current_trigger = spw_core.get_trigger_condition()
        print(f"Current trigger: {current_trigger}")

    current_format = spw_core.get_format()
    print(f"Current format: {current_format}")
    if current_format is not OutputFormat.HUMAN:
        spw_core.set_format(output_format=OutputFormat.HUMAN)
        current_format = spw_core.get_format()
        print(f"Current format: {current_format}")

    # disables output trigger if enabled since the timeout must be adjusted otherwise
    current_output_source = spw_core.get_output_source()
    if current_output_source is not TriggerOutputSource.MANUAL:
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

    Despite the final stream, the client must close the connection. Otherwise it is kept
    open and listens for input signals.
    """
    # configuration
    number_of_spectra = 10
    # listens on any signal change
    trigger_condition = Trigger.INPUT_BOTH

    spw_core = SpektralwerkCore(host=host, port=port)

    # request the device identity
    identity = spw_core.get_identity()
    print(f"device identity: {identity}")

    # configure the number of spectra which will be emitted
    current_counts = spw_core.get_count()
    print(f"Number of counts: {current_counts}")
    if current_counts != number_of_spectra:
        spw_core.set_count(count=number_of_spectra)
        current_counts = spw_core.get_count()
        print(f"Number of counts: {current_counts}")

    current_trigger = spw_core.get_trigger_condition()
    print(f"Current trigger: {current_trigger}")
    if current_trigger is not trigger_condition:
        spw_core.set_trigger_condition(trigger=trigger_condition)
        current_trigger = spw_core.get_trigger_condition()
        print(f"Current trigger: {current_trigger}")

    spw_core.set_output_source(source=TriggerOutputSource.SAMPLING)
    spw_core.set_output_delay(start_delay=1.1, end_delay=1.1)

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
