from __future__ import annotations

import contextlib
import logging
import time
import typing

import pyvisa

from spektralwerk_scpi_client.devices.models import Identity, SCPIValueContext, Spectrum
from spektralwerk_scpi_client.exceptions import (
    SpektralwerkConnectionError,
    SpektralwerkError,
    SpektralwerkResponseError,
    SpektralwerkTimeoutError,
    SpektralwerkUnexpectedResponseError,
)
from spektralwerk_scpi_client.scpi import SCPIErrorMessage
from spektralwerk_scpi_client.scpi.commands import (
    SCPICommand as SCPI,  # noqa N814
)
from spektralwerk_scpi_client.scpi.mnemonics import (
    OutputFormat,
    ProcessingStep,
    Trigger,
    TriggerOutputSource,
)
from spektralwerk_scpi_client.utils.convert import decoded_spectrum

_logger = logging.getLogger()


class ROI(typing.NamedTuple):
    start: int
    end: int


# NOTE: The Spektralwerk Core needs some ms before the next connection is accepted. Therefore
# the DEVICE_RECONNECTION_DELAY is introduced to delay the finalization of a query.
DEVICE_RECONNECTION_DELAY = 0.02

# using the open source pyvisa-py backend since NI-VISA is closed sources
VISA_BACKEND = "@py"
REQUEST_TIMEOUT_IN_SEC = 2.0


class SpektralwerkCore:
    """
    Spektralwerk Core device class
    """

    write_termination = "\n"
    read_termination = "\n"
    command_separator = ";"

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port

        self.timeout = REQUEST_TIMEOUT_IN_SEC

        # the Spektralwerk Core uses TCP/IP socket communication
        self._resource = f"TCPIP0::{host}::{port}::SOCKET"

        # wait a bit between two requests
        self._wait_until_next_connection_time = 0.0

    def _request_handler_with_error_check(
        self, resource: pyvisa.Resource, message: str
    ) -> str:
        """
        Embed the SCPI message within "*CLS" and "*ESR?" in order to check its success

        Checking the success of a SCPI query requires a look into the status register (`*ESR?`).
        In order to recover from earlier errors, we need to discard potentially existing status
        flags before running our request (`*CLS`).
        """
        # Clear status register before and read it right after the query.
        # This approach is used for checking the success of a query.
        message_with_esr = f"{SCPI.CLS_COMMAND};{message};{SCPI.ESR_QUERY}"
        response_with_esr = resource.query(message_with_esr).rstrip("\r")  # type: ignore
        if self.command_separator in response_with_esr:
            response, event_status_register = response_with_esr.rsplit(
                self.command_separator, 1
            )
        else:
            response, event_status_register = "", response_with_esr
        # Any value different than "0" indicates a SCPI error.
        if event_status_register != "0":
            """
            We cannot reuse the current session for error retrieval, since we indicated the
            connection to be closed (the line termination was sent above).
            """
            try:
                # Use a short timeout in order to avoid problem escalation.
                with self.apply_temporary_timeout(0.2):
                    error = self.get_error_message()
            except SpektralwerkError:
                # The connection is somehow lost forever. Stop asking questions.
                _logger.debug("SCPI request returned with non-zero status flag")
                raise SpektralwerkConnectionError(self._host, self._port) from None
            raise SpektralwerkResponseError(message, error)
        return response

    @contextlib.contextmanager
    def get_session(self) -> typing.Generator[pyvisa.Resource, None, None]:
        """
        Create a session context for reading and writing.

        Use `session.query` for typical write/read combinations.
        Use `session.write` and session.read` for raw communication handling.
        Please note: the connection will be closed by the peer as soon as our write termination is
        processed.
        Thus, you may emit only a single request ("query" or "write") in a connection context.
        This single request may be composed of multiple queries/commands separated by ";".
        """
        delay_time = self._wait_until_next_connection_time - time.monotonic()
        if delay_time > 0:
            time.sleep(delay_time)
        try:
            with pyvisa.ResourceManager(VISA_BACKEND).open_resource(
                self._resource,
                read_termination=self.read_termination,
                write_termination=self.write_termination,
            ) as session:
                # pyvisa timeout is always in [ms]. Thus, the SpektralwerkCore timeout
                # has to be converted from [s] to [ms]
                session.timeout = self.timeout * 1000
                session.clear()
                try:
                    yield session
                except Exception as exc:
                    # pyvisa raises unspecific exceptions which contain a status code with the
                    # precise error description.
                    if str(pyvisa.constants.StatusCode.error_timeout) in str(exc):
                        error_message = "Connection lost."
                        raise SpektralwerkTimeoutError(error_message) from None
                    raise
                session.close()
                self._wait_until_next_connection_time = (
                    time.monotonic() + DEVICE_RECONNECTION_DELAY
                )
        except ConnectionRefusedError as exc:
            raise SpektralwerkConnectionError(self._host, self._port) from exc

    @contextlib.contextmanager
    def apply_temporary_timeout(self, timeout):
        """
        Create a context with a different timeout than the default timeout.

        Within the context the provided timeout is applied. The previous value is
        restored afterwards.
        """
        old_timeout = self.timeout
        self.timeout = timeout
        yield
        self.timeout = old_timeout

    def _request_stream(self, message: str, delimiter: bytes) -> typing.Generator[str]:
        _logger.debug("Stream Query sent: %s", message)
        with self.get_session() as session:
            session.write(message)  # type: ignore[attr-defined]
            with session.read_termination_context(delimiter):  # type: ignore[attr-defined]
                while True:
                    response = session.read_raw()  # type: ignore[attr-defined]
                    raw_response = response.rstrip(delimiter)
                    # handle empty responses
                    if not raw_response:
                        continue
                    yield raw_response

    def _request_with_error_check(self, message: str) -> str:
        _logger.debug("Query sent: %s", message)
        with self.get_session() as session:
            response = self._request_handler_with_error_check(session, message)
            _logger.debug("Response received: %s", response)
            return response

    def _request_without_error_check(self, message: str) -> str:
        _logger.debug("Query sent (without error checks): %s", message)
        with self.get_session() as session:
            response = session.query(message)  # type: ignore
            _logger.debug("Response received (without error checks): %s", response)
            return response

    def _spectrum_generator(
        self,
        spectra_count: int | None = None,
        output_format: OutputFormat | None = OutputFormat.COBS_INT16,
    ) -> typing.Generator[Spectrum, typing.Any]:
        """
        Retrieve multiple spectra within one request

        The spectral emission is started with the provided configuration. If spectra
        count and output format are not provided, an infinite in-band stream with cobs
        encoded spectra (high sample rate).

        Args:
            spectra_count: number of spectra which will be returned
            output_format: encoding for the returned spectra

        Returns:
            spectrum generator
        """
        # apply configurations
        # if nothing is specified, an infinite stream cobs encoded is started
        for query in (
            SCPI.MEASURE_SPECTRUM_CONFIG_COUNT_COMMAND.with_arguments(
                spectra_count if spectra_count else 0
            ),
            SCPI.MEASURE_SPECTRUM_CONFIG_FORMAT_COMMAND.with_arguments(output_format),
        ):
            self._request_with_error_check(query)
        # cobs uses b"\0" for separating responses, while other formats use b";"
        delimiter = b"\0" if output_format is OutputFormat.COBS_INT16 else b";"
        for emitted_count, raw_spectrum in enumerate(
            self._request_stream(
                SCPI.MEASURE_SPECTRUM_REQUEST_QUERY, delimiter=delimiter
            ),
            start=1,
        ):
            spectrum = decoded_spectrum(raw_spectrum, output_format)
            yield spectrum
            if spectra_count and emitted_count >= spectra_count:
                break

    def _configured_spectrum_generator(self) -> typing.Generator[Spectrum, typing.Any]:
        """
        Retrieve multiple spectra within one request

        The spectral emission relies on the current configuration on the Spektralwerk.

        Returns:
            spectrum generator
        """
        output_format = self.get_format()
        spectra_count = self.get_count()

        is_triggered = self.get_trigger_condition() != Trigger.NONE

        delimiter = b"\0" if output_format is OutputFormat.COBS_INT16 else b";"
        for emitted_count, raw_spectrum in enumerate(
            self._request_stream(
                SCPI.MEASURE_SPECTRUM_REQUEST_QUERY, delimiter=delimiter
            ),
            start=1,
        ):
            spectrum = decoded_spectrum(raw_spectrum, output_format)
            yield spectrum
            if spectra_count and emitted_count >= spectra_count:
                # prevent the stream to be interrupted
                if is_triggered:
                    continue
                break

    def get_error_message(self) -> SCPIErrorMessage:
        """
        Request the last error message from the SCPI error queue

        The last entry from the error queue is removed from the error queue and returned
        to the requester. If no error occurred (the error queue is empty)
        `0, "No Error"` is returned.

        Returns:
            Last occurred error from the SCPI error queue

        """
        message = SCPI.SYSTEM_ERROR_NEXT_QUERY
        response = self._request_without_error_check(message=message)
        try:
            error_code_string, error_message = response.split(",")
            error_code = int(error_code_string)
        except ValueError:
            error_code, error_message = -1, response
        return SCPIErrorMessage(code=error_code, message=error_message)

    def get_identity(self) -> Identity:
        """
        Obtain the Spektralwerk identity

        The identity contains vendor, name, serial and firmware version.

        Returns:
            Spektralwerk identity
        """
        message = SCPI.IDN_QUERY
        [vendor, model, serial_number, firmware_version] = (
            self._request_with_error_check(message=message).split(",")
        )
        return Identity(
            vendor=vendor,
            model=model,
            serial_number=serial_number,
            firmware_version=firmware_version,
        )

    def get_spectrometer_peak_count(self) -> int:
        """
        Obtain the maximum spectrometer count value

        Returns:
            Maximum spectrometer count value
        """
        message = SCPI.DEVICE_SPECTROMETER_ARRAY_PEAK_QUERY
        return int(self._request_with_error_check(message=message))

    def get_spectrometer_resolution(self) -> float:
        """
        Obtain the average resolution of the spectrometer

        Returns:
            Averaged spectrometer resolution
        """
        message = SCPI.DEVICE_SPECTROMETER_RESOLUTION_QUERY
        return float(self._request_with_error_check(message=message))

    def get_pixels_count(self) -> int:
        """
        Obtain the number of pixel available

        Returns:
            pixel count
        """
        message = SCPI.DEVICE_SPECTROMETER_ARRAY_PCOUNT_QUERY
        return int(self._request_with_error_check(message=message))

    def get_pixel_wavelengths(self) -> list[float]:
        """
        Obtain wavelength value per pixel

        Returns:
            array with wavelength value for each pixel
        """
        message = SCPI.DEVICE_SPECTROMETER_PIXELS_WAVELENGTHS_QUERY
        wavelengths = (self._request_with_error_check(message=message)).split(",")
        return [float(wavelength) for wavelength in wavelengths]

    def get_exposure_time(self) -> float:
        """
        Obtain current exposure time value

        Returns:
            exposure time value
        """
        message = SCPI.MEASURE_SPECTRUM_CONFIG_EXPOSURE_TIME_QUERY
        response = self._request_with_error_check(message=message)
        return float(response)

    def set_exposure_time(self, exposure_time: float) -> None:
        """
        Set the exposure time

        Args:
            exposure time in µs
        """
        message = SCPI.MEASURE_SPECTRUM_CONFIG_EXPOSURE_TIME_COMMAND.with_arguments(
            exposure_time
        )
        self._request_with_error_check(message=message)

    def get_exposure_time_context(self) -> SCPIValueContext:
        """
        Get the context of the exposure time

        The context contains the min/max values for the exposure time, the default value
        and the unit for the current, min, max and default value.

        Returns:
            exposure time context
        """
        context_queries = [
            SCPI.MEASURE_SPECTRUM_CONFIG_EXPOSURE_TIME_MIN_QUERY,
            SCPI.MEASURE_SPECTRUM_CONFIG_EXPOSURE_TIME_MAX_QUERY,
            SCPI.MEASURE_SPECTRUM_CONFIG_EXPOSURE_TIME_DEFAULT_QUERY,
            SCPI.MEASURE_SPECTRUM_CONFIG_EXPOSURE_TIME_UNIT_QUERY,
        ]
        context_message = ";".join(context_queries)
        [minimum, maximum, default, unit] = self._request_with_error_check(
            message=context_message
        ).split(";")
        return SCPIValueContext(
            minimum=float(minimum),
            maximum=float(maximum),
            default=float(default),
            unit=unit,
        )

    def get_average_number(self) -> int:
        """
        Obtain current value for number of averaged spectra

        Returns:
            current value for number of averaged spectra
        """
        message = SCPI.MEASURE_SPECTRUM_CONFIG_AVERAGE_NUMBER_QUERY
        response = self._request_with_error_check(message=message)
        return int(response)

    def set_average_number(self, number_of_spectra: int) -> None:
        """
        Set the number of averaged spectra applied for requested spectra (rolling average width).

        Args:
            number_of_spectra: number of spectra used for the rolling average

        """
        message = SCPI.MEASURE_SPECTRUM_CONFIG_AVERAGE_NUMBER_COMMAND.with_arguments(
            number_of_spectra
        )
        self._request_with_error_check(message=message)

    def get_average_number_context(self) -> SCPIValueContext:
        """
        Get the context of the average number

        The context contains the min/max values for the average number and the default value

        Returns:
            average number context
        """
        context_queries = [
            SCPI.MEASURE_SPECTRUM_CONFIG_AVERAGE_NUMBER_MIN_QUERY,
            SCPI.MEASURE_SPECTRUM_CONFIG_AVERAGE_NUMBER_MAX_QUERY,
            SCPI.MEASURE_SPECTRUM_CONFIG_AVERAGE_NUMBER_DEFAULT_QUERY,
        ]
        context_message = ";".join(context_queries)
        [minimum, maximum, default] = self._request_with_error_check(
            message=context_message
        ).split(";")
        return SCPIValueContext(
            minimum=int(minimum),
            maximum=int(maximum),
            default=int(default),
            unit=None,
        )

    def get_offset_voltage(self) -> float:
        """
        Obtain current value for spectrometer pixel offset voltage

        Returns:
            current value for spectrometer pixel offset voltage
        """
        message = SCPI.DEVICE_SPECTROMETER_BACKGROUND_OFFSET_VOLTAGE_QUERY
        response = self._request_with_error_check(message=message)
        return float(response)

    def set_offset_voltage(self, offset_voltage: float) -> None:
        """
        Set the spectrometer pixel offset voltage

        Args:
            offset_voltage in mV
        """
        message = (
            SCPI.DEVICE_SPECTROMETER_BACKGROUND_OFFSET_VOLTAGE_COMMAND.with_arguments(
                offset_voltage
            )
        )
        self._request_with_error_check(message=message)

    def get_offset_voltage_context(self) -> SCPIValueContext:
        """
        Get the context of the offset voltage

        The context contains the min/max values for the offset voltage, the default value
        and the unit for the current, min, max and default value.

        Returns:
            offset voltage context
        """
        context_queries = [
            SCPI.DEVICE_SPECTROMETER_BACKGROUND_OFFSET_VOLTAGE_MIN_QUERY,
            SCPI.DEVICE_SPECTROMETER_BACKGROUND_OFFSET_VOLTAGE_MAX_QUERY,
            SCPI.DEVICE_SPECTROMETER_BACKGROUND_OFFSET_VOLTAGE_DEFAULT_QUERY,
            SCPI.DEVICE_SPECTROMETER_BACKGROUND_OFFSET_VOLTAGE_UNIT_QUERY,
        ]
        context_message = ";".join(context_queries)
        [minimum, maximum, default, unit] = self._request_with_error_check(
            message=context_message
        ).split(";")
        return SCPIValueContext(
            minimum=float(minimum),
            maximum=float(maximum),
            default=float(default),
            unit=unit,
        )

    def get_dark_reference(self) -> list[float]:
        """
        Obtain current stored dark reference spectrum

        Returns:
            current dark reference spectrum
        """
        message = SCPI.MEASURE_SPECTRUM_REFERENCE_DARK_QUERY
        dark_reference = self._request_with_error_check(message=message).split(",")
        return [float(value) for value in dark_reference]

    def acquire_dark_reference(self, average_number: int | None = None) -> None:
        """
        Acquire a dark reference spectrum

        A dark reference spectrum is obtained from spectral samples averaged by the Spektralwerk
        device itself.

        Args:
            average_number: number of spectra used for the averaging of the dark reference
                spectrum. If no value is provided, the currently set value of
                `MEASure:SPECtrum:AVERage:NUMBer` is used. Default: None
        """
        message = SCPI.MEASURE_SPECTRUM_REFERENCE_DARK_ACQUIRE_COMMAND.with_arguments(
            average_number if average_number else ""
        )
        self._request_with_error_check(message=message)

    def set_dark_reference(self, reference_spectrum: list[float]) -> None:
        """
        Set a dark reference spectrum

        The dark reference spectrum is set by a provided reference spectrum.

        Args:
            reference_spectrum: list of spectral intensities which is used as a dark reference
                spectrum.
        """
        message = SCPI.MEASURE_SPECTRUM_REFERENCE_DARK_SET_COMMAND.with_arguments(
            reference_spectrum
        )
        self._request_with_error_check(message=message)

    def get_light_reference(self) -> list[float]:
        """
        Obtain current stored light reference spectrum

        Returns:
            current light reference spectrum
        """
        message = SCPI.MEASURE_SPECTRUM_REFERENCE_LIGHT_QUERY
        light_refernce = self._request_with_error_check(message=message).split(",")
        return [float(value) for value in light_refernce]

    def acquire_light_reference(self, average_number: int | None = None) -> None:
        """
        Acquire a light reference spectrum

        A light reference spectrum is obtained from spectral samples averaged by the Spektralwerk
        device itself.

        Args:
            average_number: number of spectra used for the averaging of the light reference
                spectrum. If no value is provided, the currently set value of
                `MEASure:SPECtrum:AVERage:NUMBer` is used. Default: None
        """
        message = SCPI.MEASURE_SPECTRUM_REFERENCE_LIGHT_ACQUIRE_COMMAND.with_arguments(
            average_number if average_number else ""
        )
        self._request_with_error_check(message=message)

    def set_light_reference(self, reference_spectrum: list[float]) -> None:
        """
        Set a light reference spectrum

        The light reference spectrum is set by a provided reference spectrum.

        Args:
            reference_spectrum: list of spectral intensities which is used as a light reference spectrum.
        """
        message = SCPI.MEASURE_SPECTRUM_REFERENCE_LIGHT_SET_COMMAND.with_arguments(
            reference_spectrum
        )
        self._request_with_error_check(message=message)

    def get_raw_spectrum(self) -> Spectrum:
        """
        Get a single raw spectrum

        The raw spectrum is not influenced by additional configurations.

        Returns:
            single raw spectrum
        """
        response = self._request_with_error_check(
            message=SCPI.MEASURE_SPECTRUM_REQUEST_RAW_QUERY
        )
        return decoded_spectrum(response)

    def get_spectrum(self) -> Spectrum:
        """
        Obtain a single spectrum

        Request configurations are applied and will effect the returned spectrum.

        Returns:
            a single spectrum
        """
        return next(self._spectrum_generator(spectra_count=1))

    def get_spectra(
        self,
        spectra_count: int | None = None,
        output_format: OutputFormat | None = None,
    ) -> typing.Generator[Spectrum, typing.Any]:
        """
        Obtain spectra

        Returns:
            incremental delivery of spectra
        """
        return self._spectrum_generator(
            spectra_count=spectra_count, output_format=output_format
        )

    def get_configured_spectra(self) -> typing.Generator[Spectrum, typing.Any]:
        """
        Obtain spectra without changing configuration on the Spektralwerk Core

        Returns:
            incremental delivery of spectra
        """
        return self._configured_spectrum_generator()

    def get_processing(self) -> set[ProcessingStep]:
        """
        Obtain the configured processing steps

        Returns:
            set with the configured processing steps
        """
        message = SCPI.MEASURE_SPECTRUM_CONFIG_PROCESSING_QUERY
        response = self._request_with_error_check(message=message)
        return {ProcessingStep(step) for step in response.split(",")}

    def set_processing(
        self,
        processing_steps: set[ProcessingStep] | None,
    ) -> None:
        """
        Set processing steps for requesting spectral sample

        Args:
            processing_steps: set of processing steps. If `None` is passed, the
                currently valid processing steps will be removed.
        """
        message = f"{SCPI.MEASURE_SPECTRUM_CONFIG_PROCESSING_COMMAND}"
        if processing_steps:
            message = f"{message} {','.join(processing_steps)}"
        self._request_with_error_check(message=message)

    def get_binning_width(self) -> int:
        """
        Obtain the current binning width

        Returns:
            configured number of merged pixels
        """
        message = SCPI.MEASURE_SPECTRUM_CONFIG_BINNING_WIDTH_QUERY
        return int(self._request_with_error_check(message=message))

    def set_binnig_width(self, width: int) -> None:
        """
        Set the number of merged pixel

        Args:
            width: the number of merged pixel
        """
        message = SCPI.MEASURE_SPECTRUM_CONFIG_BINNING_WIDTH_COMMAND.with_arguments(
            width
        )
        self._request_with_error_check(message=message)

    def get_count(self) -> int:
        """
        Obtain the current configured number of streamed spectra

        Returns:
            configured number of counts. A value of `0` will lead to an infinite stream.
        """
        message = f"{SCPI.MEASURE_SPECTRUM_CONFIG_COUNT_QUERY}"
        return int(self._request_with_error_check(message=message))

    def set_count(self, count: int) -> None:
        """
        Set the number of spectra to obtain from a single call

        Args:
            count: the number of spectra which should be returned upon calling `MEASure
                :SPECtrum:REQuest?`
        """
        message = SCPI.MEASURE_SPECTRUM_CONFIG_COUNT_COMMAND.with_arguments(count)
        self._request_with_error_check(message=message)

    def get_format(self) -> OutputFormat:
        """
        Obtain the current configured output format

        Returns:
            configured output format
        """
        message = SCPI.MEASURE_SPECTRUM_CONFIG_FORMAT_QUERY
        return OutputFormat(self._request_with_error_check(message=message))

    def set_format(self, output_format: OutputFormat):
        """
        Set the output format for in-band and out-of-band spectral emission

        Args:
            output_format: the output format for the spectral emission

        """
        message = SCPI.MEASURE_SPECTRUM_CONFIG_FORMAT_COMMAND.with_arguments(
            output_format.value
        )
        self._request_with_error_check(message=message)

    def get_trigger_condition(self) -> Trigger:
        """
        Obtain the current trigger condition

        Returns:
            the configured trigger condition
        """
        message = SCPI.MEASURE_SPECTRUM_CONFIG_TRIGGER_QUERY
        return Trigger(self._request_with_error_check(message=message))

    def set_trigger_condition(self, trigger: Trigger) -> None:
        """
        Set the trigger condition

        Args:
            trigger: the condition which starts spectral emission
        """
        message = SCPI.MEASURE_SPECTRUM_CONFIG_TRIGGER_COMMAND.with_arguments(trigger)
        self._request_with_error_check(message=message)

    def get_roi(self) -> tuple[int, int]:
        """
        Obtain the currend configured region-of-interest

        The region-of-interest limits the spectral output to the provided pixel range
        when requesting spectra with `MEASure:SPECtrum:REQuest?`

        Returns:
            region-of-interest
        """
        message = f"{SCPI.MEASURE_SPECTRUM_CONFIG_ROI_QUERY}"
        try:
            roi_str = self._request_with_error_check(message=message).split(",")
            roi = ROI(*[int(value) for value in roi_str])
        except TypeError as exc:
            raise SpektralwerkUnexpectedResponseError from exc
        return roi

    def set_roi(self, roi: tuple[int, int]) -> None:
        """
        Set the region-of-interest

        Args:
            roi: a tuple containing the start and end pixel number for restricting the
                returned spectra.
        """
        message = SCPI.MEASURE_SPECTRUM_CONFIG_ROI_COMMAND.with_arguments(
            ",".join(str(pixel) for pixel in roi)
        )
        self._request_with_error_check(message=message)

    def get_averaged_spectra(
        self,
        spectra_count: int | None = 1,
        output_format: OutputFormat | None = None,
    ) -> typing.Generator[Spectrum, typing.Any]:
        """
        Obtain averaged spectra

        The number of spectra used for the averaged spectrum can be adjusted with
        `MEASure:SPECtrum:AVERage:NUMBer`.

        Returns:
            averaged spectra
        """
        # adjust processing steps to obtain averaged spectra; other processing steps are removed
        self.set_processing({ProcessingStep.AVERAGE})
        return self._spectrum_generator(
            spectra_count=spectra_count, output_format=output_format
        )

    def get_input_trigger_level(self) -> int:
        """
        Obtain the current level of the input trigger

        The level of the input trigger is either `0` (low) or `1` high. The input
        trigger level is controlled by some other device and can not be set from the
        Spektralwerk.

        Returns:
            current level of the input trigger
        """
        message = SCPI.CONTROL_INPUT_LEVEL_QUERY
        return int(self._request_with_error_check(message=message))

    def get_output_delay(self) -> tuple[float, float]:
        """
        Obtain the current start and end delay

        Returns
            a tuple containing the start and end delay
        """
        delay_queries = [
            SCPI.CONTROL_OUTPUT_DELAY_START_QUERY,
            SCPI.CONTROL_OUTPUT_DELAY_END_QUERY,
        ]
        delay_message = ";".join(delay_queries)
        [start_delay, end_delay] = self._request_with_error_check(
            message=delay_message
        ).split(";")
        return (float(start_delay), float(end_delay))

    def set_output_delay(
        self, start_delay: float | None = None, end_delay: float | None = None
    ) -> None:
        """
        Set the either start or end delay or both.

        Args:
            start_delay: delay in [s] between the change of the output level and the
                emission of spectra
            end_delay: delay in [s] between the end of the spectral acquisition and the
                change of the level of the output trigger
        """
        messages = []
        if start_delay is not None:
            messages.append(
                SCPI.CONTROL_OUTPUT_DELAY_START_COMMAND.with_arguments(start_delay)
            )
        if end_delay is not None:
            messages.append(
                SCPI.CONTROL_OUTPUT_DELAY_END_COMMAND.with_arguments(end_delay)
            )
        message = ";".join(messages)
        self._request_with_error_check(message=message)

    def get_output_source(self) -> TriggerOutputSource:
        """
        Obtain the current output source

        The output source determines which event will change the level of the output
        trigger.

        Returns:
            source for output trigger level changes
        """
        message = SCPI.CONTROL_OUTPUT_SOURCE_QUERY
        return TriggerOutputSource(self._request_with_error_check(message=message))

    def set_output_source(self, source: TriggerOutputSource) -> None:
        """
        Set the source for output trigger level changes

        Args:
            source for level changes
        """
        message = SCPI.CONTROL_OUTPUT_SOURCE_COMMAND.with_arguments(source)
        self._request_with_error_check(message=message)

    def get_output_trigger_level(self) -> int:
        """
        Obtain the current level of the output trigger

        The level of the output trigger is either `0` (low) or `1` (high).

        Returns:
            current level of the output trigger
        """
        message = SCPI.CONTROL_OUTPUT_LEVEL_TARGET_QUERY
        return int(self._request_with_error_check(message=message))

    def set_output_trigger_level(self, level: int) -> None:
        """
        Set the current level of the output trigger

        The level of the output trigger can be set either to `0` (low) or `1` high
        """
        message = SCPI.CONTROL_OUTPUT_LEVEL_TARGET_COMMAND.with_arguments(level)
        self._request_with_error_check(message=message)

    def process_request_with_error_check(self, command: str) -> str:
        """
        Send a command to the Spektralwerk

        A single command several commands, separated by a semicolon (;), are send to the
        Spektralwerk.

        Args:
            command: string to be processed to the Spektralwerk

        Returns:
            raw response of the provided command
        """
        return self._request_with_error_check(command)
