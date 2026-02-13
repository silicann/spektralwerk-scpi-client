from __future__ import annotations

import contextlib
import logging
import struct
import time
import typing

import cobs.cobs
import pyvisa

from spektralwerk_scpi_client.exceptions import (
    SpektralwerkConnectionError,
    SpektralwerkError,
    SpektralwerkResponseError,
    SpektralwerkTimeoutError,
)
from spektralwerk_scpi_client.scpi import SCPIErrorMessage
from spektralwerk_scpi_client.scpi.commands import SCPICommand as Scpi
from spektralwerk_scpi_client.scpi.mnemonics import OutputFormat, ProcessingStep

_logger = logging.getLogger()


class Spectrum(typing.NamedTuple):
    """
    Basic spectrum class

    A spectrum consists of a timestamp in [s] and list of floats containing the spectral
    intensities.
    """

    timestamp_sec: float
    data: list[float]


# NOTE: The Spektralwerk Core needs some ms before the next connection is accepted. Therefore
# the DEVICE_RECONNECTION_DELAY is introduced to delay the finalization of a query.
DEVICE_RECONNECTION_DELAY = 0.02

# using the open source pyvisa-py backend since NI-VISA is closed sources
VISA_BACKEND = "@py"
REQUEST_TIMEOUT_IN_MS = 2000


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
        message_with_esr = f"{Scpi.CLS_COMMAND};{message};{Scpi.ESR_QUERY}"
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
                error = self.get_error_message(timeout=200)
            except SpektralwerkError:
                # The connection is somehow lost forever. Stop asking questions.
                _logger.error("SCPI request returned with non-zero status flag")
                raise SpektralwerkResponseError(
                    message,
                    event_status_register,
                ) from None
            raise SpektralwerkResponseError(message, error.code, error.message)
        return response

    @contextlib.contextmanager
    def get_session(
        self, timeout: int
    ) -> typing.Generator[pyvisa.Resource, None, None]:
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
                session.timeout = timeout
                session.clear()
                try:
                    yield session
                except Exception as exc:
                    # pyvisa raises unspecific exceptions which contain a status code with the
                    # precise error description.
                    if str(pyvisa.constants.StatusCode.error_timeout) in str(exc):
                        raise SpektralwerkTimeoutError from exc
                    raise
                session.close()
                self._wait_until_next_connection_time = (
                    time.monotonic() + DEVICE_RECONNECTION_DELAY
                )
        except ConnectionRefusedError as exc:
            raise SpektralwerkConnectionError(self._host, self._port) from exc

    def _request_stream(
        self, message: str, delimiter: bytes, timeout: int
    ) -> typing.Generator[str]:
        _logger.debug("Stream Query sent: %s", message)
        with self.get_session(timeout) as session:
            session.write(message)  # type: ignore[attr-defined]
            with session.read_termination_context(delimiter):  # type: ignore[attr-defined]
                while True:
                    response = session.read_raw()  # type: ignore[attr-defined]
                    yield response.rstrip(delimiter)

    def _request_with_error_check(self, message: str, timeout: int) -> str:
        _logger.debug("Query sent: %s", message)
        with self.get_session(timeout) as session:
            response = self._request_handler_with_error_check(session, message)
            _logger.debug("Response received: %s", response)
            return response

    def _request_without_error_check(self, message: str, timeout: int) -> str:
        _logger.debug("Query sent (without error checks): %s", message)
        with self.get_session(timeout) as session:
            response = session.query(message)  # type: ignore
            _logger.debug("Response received (without error checks): %s", response)
            return response

    def _spectrum_generator(
        self,
        output_format: OutputFormat | None = OutputFormat.COBS_INT16,
        spectra_count: int | None = None,
        sample_frequency: float | None = None,
        timeout: int = REQUEST_TIMEOUT_IN_MS,
        format_timestamp: str = "Q",
        format_pixel: str = "h",
    ) -> typing.Generator[Spectrum, typing.Any]:
        for query in (
            # infinite number of spectra to retrieve
            Scpi.MEASURE_SPECTRUM_REQUEST_CONFIG_COUNT_COMMAND.with_arguments(
                0 if spectra_count is None else spectra_count
            ),
            # as fast as possible
            Scpi.MEASURE_SPECTRUM_REQUEST_CONFIG_FREQUENCY_COMMAND.with_arguments(
                0 if sample_frequency is None else sample_frequency
            ),
            Scpi.MEASURE_SPECTRUM_REQUEST_CONFIG_FORMAT_COMMAND.with_arguments(
                output_format
            ),
        ):
            self._request_with_error_check(query, timeout)
        for raw_spectrum in self._request_stream(
            Scpi.MEASURE_SPECTRUM_REQUEST_QUERY, delimiter=b"\0", timeout=timeout
        ):
            decoded_spectrum = cobs.cobs.decode(raw_spectrum)
            pixel_count = (
                len(decoded_spectrum) - struct.calcsize(format_timestamp)
            ) // struct.calcsize(format_pixel)
            unpack_format = f"<{format_timestamp}{pixel_count}{format_pixel}"
            [timestamp_musec, *spectral_data] = struct.unpack(
                unpack_format, decoded_spectrum
            )
            yield Spectrum(
                float(timestamp_musec / 1_000_000),
                [float(value) for value in spectral_data],
            )

    def get_error_message(
        self, timeout: int = REQUEST_TIMEOUT_IN_MS
    ) -> SCPIErrorMessage:
        """
        Request the last error message from the SCPI error queue

        The last entry from the error queue is removed from the error queue and returned
        to the requester. If no error occurred (the error queue is empty)
        `0, "No Error"` is returned.

        Args:
            timeout: timeout [ms] for error request. Default: REQUEST_TIMEOUT_IN_MS

        Returns:
            Last occurred error from the SCPI error queue

        """
        message = Scpi.SYSTEM_ERROR_NEXT_QUERY
        response = self._request_without_error_check(message=message, timeout=timeout)
        try:
            error_code_string, error_message = response.split(",")
            error_code = int(error_code_string)
        except ValueError:
            error_code, error_message = -1, response
        return SCPIErrorMessage(code=error_code, message=error_message)

    def get_identity(self, timeout: int = REQUEST_TIMEOUT_IN_MS) -> str:
        """
        Obtain the Spektralwerk identity

        The identity contains vendor, name, serial and firmware version.

        Args:
            timeout: timeout [ms] for identity request. Default: REQUEST_TIMEOUT_IN_MS

        Returns:
            Spektralwerk identity
        """
        message = Scpi.IDN_QUERY
        return self._request_with_error_check(message=message, timeout=timeout)

    def get_spectrometer_peak_count(self, timeout: int = REQUEST_TIMEOUT_IN_MS) -> int:
        """
        Obtain the maximum spectrometer count value

        Args:
            timeout: timeout [ms] for maximum spectrometer count value request. Default: REQUEST_TIMEOUT_IN_MS

        Returns:
            Maximum spectrometer count value
        """
        message = Scpi.DEVICE_SPECTROMETER_ARRAY_PEAK_QUERY
        return int(self._request_with_error_check(message=message, timeout=timeout))

    def get_spectrometer_resolution(
        self, timeout: int = REQUEST_TIMEOUT_IN_MS
    ) -> float:
        """
        Obtain the average resolution of the spectrometer

        Args
            timeout: timeout [ms] for spectrometer resolution request. Default: REQUEST_TIMEOUT_IN_MS

        Returns:
            Averaged spectrometer resolution
        """
        message = Scpi.DEVICE_SPECTROMETER_RESOLUTION_QUERY
        return float(self._request_with_error_check(message=message, timeout=timeout))

    def get_pixels_count(self, timeout: int = REQUEST_TIMEOUT_IN_MS) -> int:
        """
        Obtain the number of pixel available

        Args:
            timeout: timeout [ms] for spectrometer pixel count request. Default: REQUEST_TIMEOUT_IN_MS

        Returns:
            pixel count
        """
        message = Scpi.DEVICE_SPECTROMETER_ARRAY_PCOUNT_QUERY
        return int(self._request_with_error_check(message=message, timeout=timeout))

    def get_pixel_wavelengths(
        self, timeout: int = REQUEST_TIMEOUT_IN_MS
    ) -> list[float]:
        """
        Obtain wavelength value per pixel

        Args:
            timeout: timeout [ms] for spectrometer wavelength array request. Default: REQUEST_TIMEOUT_IN_MS

        Returns:
            array with wavelength value for each pixel
        """
        message = Scpi.DEVICE_SPECTROMETER_PIXELS_WAVELENGTHS_QUERY
        wavelengths = (
            self._request_with_error_check(message=message, timeout=timeout)
        ).split(",")
        return [float(wavelength) for wavelength in wavelengths]

    def get_exposure_time(self, timeout: int = REQUEST_TIMEOUT_IN_MS) -> float:
        """
        Obtain current exposure time value

        Args:
            timeout: timeout [ms] for spectrometer resolution request. Default: REQUEST_TIMEOUT_IN_MS

        Returns:
            exposure time value
        """
        message = Scpi.MEASURE_SPECTRUM_EXPOSURE_TIME_QUERY
        response = self._request_with_error_check(message=message, timeout=timeout)
        return float(response)

    def set_exposure_time(
        self, exposure_time: float, timeout: int = REQUEST_TIMEOUT_IN_MS
    ) -> None:
        """
        Set the exposure time

        Args:
            exposure time in µs
            timeout: timeout [ms] for exposure time request. Default: REQUEST_TIMEOUT_IN_MS

        """
        message = f"{Scpi.MEASURE_SPECTRUM_EXPOSURE_TIME_COMMAND} {exposure_time}"
        self._request_with_error_check(message=message, timeout=timeout)

    def get_exposure_time_unit(self, timeout: int = REQUEST_TIMEOUT_IN_MS) -> str:
        """
        Get the unit of the exposure time

        Args:
            timeout: timeout [ms] for exposure time unit request. Default: REQUEST_TIMEOUT_IN_MS

        Returns:
            unit of the exposure time
        """
        message = Scpi.MEASURE_SPECTRUM_EXPOSURE_TIME_UNIT_QUERY
        return self._request_with_error_check(message=message, timeout=timeout)

    def get_exposure_time_max(self, timeout: int = REQUEST_TIMEOUT_IN_MS) -> float:
        """
        Obtain maximum exposure time value

        Args:
            timeout: timeout [ms] for maximum exposure time request. Default: REQUEST_TIMEOUT_IN_MS

        Returns:
            bare maximum exposure time value
        """
        message = Scpi.MEASURE_SPECTRUM_EXPOSURE_TIME_MAX_QUERY
        response = self._request_with_error_check(message=message, timeout=timeout)
        return float(response)

    def get_exposure_time_min(self, timeout: int = REQUEST_TIMEOUT_IN_MS) -> float:
        """
        Obtain minimum exposure time value

        Args:
            timeout: timeout [ms] for minimum exposure time request. Default: REQUEST_TIMEOUT_IN_MS

        Returns:
            bare minimum exposure time value
        """
        message = Scpi.MEASURE_SPECTRUM_EXPOSURE_TIME_MIN_QUERY
        response = self._request_with_error_check(message=message, timeout=timeout)
        return float(response)

    def get_average_number(self, timeout: int = REQUEST_TIMEOUT_IN_MS) -> int:
        """
        Obtain current value for number of averaged spectra

        Args:
            timeout: timeout [ms] for average number time request. Default: REQUEST_TIMEOUT_IN_MS

        Returns:
            current value for number of averaged spectra
        """
        message = Scpi.MEASURE_SPECTRUM_AVERAGE_NUMBER_QUERY
        response = self._request_with_error_check(message=message, timeout=timeout)
        return int(response)

    def set_average_number(
        self, number_of_spectra: int, timeout: int = REQUEST_TIMEOUT_IN_MS
    ) -> None:
        """
        Set the number of averaged spectra applied for requested spectra (rolling average width).

        Args:
            number_of_spectra: number of spectra used for the rolling average
            timeout: timeout [ms] for average number time request. Default: REQUEST_TIMEOUT_IN_MS

        """
        message = f"{Scpi.MEASURE_SPECTRUM_AVERAGE_NUMBER_COMMAND} {number_of_spectra}"
        self._request_with_error_check(message=message, timeout=timeout)

    def get_average_number_max(self, timeout: int = REQUEST_TIMEOUT_IN_MS) -> int:
        """
        Obtain max value for number of averaged spectra

        Args:
            timeout: timeout [ms] for maximum average number request. Default: REQUEST_TIMEOUT_IN_MS

        Returns:
            maximum value for number of averaged spectra
        """
        message = Scpi.MEASURE_SPECTRUM_AVERAGE_NUMBER_MAX_QUERY
        response = self._request_with_error_check(message=message, timeout=timeout)
        return int(response)

    def get_average_number_min(self, timeout: int = REQUEST_TIMEOUT_IN_MS) -> int:
        """
        Obtain minimum value for number of averaged spectra

        Args:
            timeout: timeout [ms] for minimum average number request. Default: REQUEST_TIMEOUT_IN_MS

        Returns:
            minimum value for number of averaged spectra
        """
        message = Scpi.MEASURE_SPECTRUM_AVERAGE_NUMBER_MIN_QUERY
        response = self._request_with_error_check(message=message, timeout=timeout)
        return int(response)

    def get_offset_voltage(self, timeout: int = REQUEST_TIMEOUT_IN_MS) -> float:
        """
        Obtain current value for spectrometer pixel offset voltage

        Args:
            timeout: timeout [ms] for offset voltage request. Default: REQUEST_TIMEOUT_IN_MS

        Returns:
            current value for spectrometer pixel offset voltage
        """
        message = Scpi.DEVICE_SPECTROMETER_BACKGROUND_OFFSET_VOLTAGE_QUERY
        response = self._request_with_error_check(message=message, timeout=timeout)
        return float(response)

    def set_offset_voltage(
        self, offset_voltage: float, timeout: int = REQUEST_TIMEOUT_IN_MS
    ) -> None:
        """
        Set the spectrometer pixel offset voltage

        Args:
            offset_voltage in mV
            timeout: timeout [ms] for offset voltage request. Default: REQUEST_TIMEOUT_IN_MS

        """
        message = f"{Scpi.DEVICE_SPECTROMETER_BACKGROUND_OFFSET_VOLTAGE_COMMAND} {offset_voltage}"
        self._request_with_error_check(message=message, timeout=timeout)

    def get_offset_voltag_unit(self, timeout: int = REQUEST_TIMEOUT_IN_MS) -> str:
        """
        Get the unit of the offset voltage

        Args:
            timeout: timeout [ms] for exposure time unit request. Default: REQUEST_TIMEOUT_IN_MS

        Returns:
            unit of the offset voltage
        """
        message = Scpi.DEVICE_SPECTROMETER_BACKGROUND_OFFSET_VOLTAGE_UNIT_QUERY
        return self._request_with_error_check(message=message, timeout=timeout)

    def get_offset_voltage_max(self, timeout: int = REQUEST_TIMEOUT_IN_MS) -> float:
        """
        Obtain maximum value for spectrometer pixel offset voltage

        Args:
            timeout: timeout [ms] for maximum offset voltage request. Default: REQUEST_TIMEOUT_IN_MS

        Returns:
            maximum value for spectrometer pixel offset voltage
        """
        message = Scpi.DEVICE_SPECTROMETER_BACKGROUND_OFFSET_VOLTAGE_MAX_QUERY
        response = self._request_with_error_check(message=message, timeout=timeout)
        return float(response)

    def get_offset_voltage_min(self, timeout: int = REQUEST_TIMEOUT_IN_MS) -> float:
        """
        Obtain minimum value for spectrometer pixel offset voltage

        Args:
            timeout: timeout [ms] for minimum offset voltage request. Default: REQUEST_TIMEOUT_IN_MS

        Returns:
            minimum value for spectrometer pixel offset voltage
        """
        message = Scpi.DEVICE_SPECTROMETER_BACKGROUND_OFFSET_VOLTAGE_MIN_QUERY
        response = self._request_with_error_check(message=message, timeout=timeout)
        return float(response)

    def get_dark_reference(self, timeout: int = REQUEST_TIMEOUT_IN_MS) -> list[float]:
        """
        Obtain current stored dark reference spectrum

        Args:
            timeout: timeout [ms] for dark reference spectrum request. Default: REQUEST_TIMEOUT_IN_MS

        Returns:
            current dark reference spectrum
        """
        message = Scpi.MEASURE_SPECTRUM_REFERENCE_DARK_QUERY
        dark_reference = self._request_with_error_check(
            message=message, timeout=timeout
        ).split(",")
        return [float(value) for value in dark_reference]

    def acquire_dark_reference(
        self, average_number: int | None = None, timeout: int = REQUEST_TIMEOUT_IN_MS
    ) -> None:
        """
        Acquire a dark reference spectrum

        A dark reference spectrum is obtained from spectral samples averaged by the Spektralwerk
        device itself.

        Args:
            average_number: number of spectra used for the averaging of the dark reference
                spectrum. If no value is provided, the currently set value of
                `MEASure:SPECtrum:AVERage:NUMBer` is used. Default: None
            timeout: timeout [ms] for acquiring dark reference spectrum. Default: REQUEST_TIMEOUT_IN_MS
        """
        message = f"{Scpi.MEASURE_SPECTRUM_REFERENCE_DARK_ACQUIRE_COMMAND}"
        if average_number:
            message = f"{message} {average_number}"
        self._request_with_error_check(message=message, timeout=timeout)

    def set_dark_reference(
        self, reference_spectrum: list[float], timeout: int = REQUEST_TIMEOUT_IN_MS
    ) -> None:
        """
        Set a dark reference spectrum

        The dark reference spectrum is set by a provided reference spectrum.

        Args:
            reference_spectrum: list of spectral intensities which is used as a dark reference
                spectrum.
            timeout: timeout [ms] for setting dark reference spectrum. Default: REQUEST_TIMEOUT_IN_MS
        """
        message = (
            f"{Scpi.MEASURE_SPECTRUM_REFERENCE_DARK_SET_COMMAND} {reference_spectrum}"
        )
        self._request_with_error_check(message=message, timeout=timeout)

    def get_light_reference(self, timeout: int = REQUEST_TIMEOUT_IN_MS) -> list[float]:
        """
        Obtain current stored light reference spectrum

        Args:
            timeout: timeout [ms] for light reference spectrum request. Default: REQUEST_TIMEOUT_IN_MS

        Returns:
            current light reference spectrum
        """
        message = Scpi.MEASURE_SPECTRUM_REFERENCE_LIGHT_QUERY
        light_refernce = self._request_with_error_check(
            message=message, timeout=timeout
        ).split(",")
        return [float(value) for value in light_refernce]

    def acquire_light_reference(
        self, average_number: int | None = None, timeout: int = REQUEST_TIMEOUT_IN_MS
    ) -> None:
        """
        Acquire a light reference spectrum

        A light reference spectrum is obtained from spectral samples averaged by the Spektralwerk
        device itself.

        Args:
            average_number: number of spectra used for the averaging of the light reference
                spectrum. If no value is provided, the currently set value of
                `MEASure:SPECtrum:AVERage:NUMBer` is used. Default: None
            timeout: timeout [ms] for acquiring light reference spectrum. Default: REQUEST_TIMEOUT_IN_MS
        """
        message = f"{Scpi.MEASURE_SPECTRUM_REFERENCE_LIGHT_ACQUIRE_COMMAND}"
        if average_number:
            message = f"{message} {average_number}"
        self._request_with_error_check(message=message, timeout=timeout)

    def set_light_reference(
        self, reference_spectrum: list[float], timeout: int = REQUEST_TIMEOUT_IN_MS
    ) -> None:
        """
        Set a light reference spectrum

        The light reference spectrum is set by a provided reference spectrum.

        Args:
            reference_spectrum: list of spectral intensities which is used as a light reference spectrum.
            timeout: timeout [ms] for setting light reference spectrum. Default: REQUEST_TIMEOUT_IN_MS
        """
        message = (
            f"{Scpi.MEASURE_SPECTRUM_REFERENCE_LIGHT_SET_COMMAND} {reference_spectrum}"
        )
        self._request_with_error_check(message=message, timeout=timeout)

    def get_spectra(
        self, timeout: int = REQUEST_TIMEOUT_IN_MS
    ) -> typing.Generator[Spectrum, typing.Any]:
        """
        Obtain raw spectra

        Args:
            timeout: timeout [ms] for spectra request. Default: REQUEST_TIMEOUT_IN_MS

        Returns:
            incremental delivery of spectra
        """
        return self._spectrum_generator(timeout=timeout)

    def set_processing(
        self,
        processing_steps: list[ProcessingStep] | None,
        timeout: int = REQUEST_TIMEOUT_IN_MS,
    ) -> None:
        """
        Set processing steps for requesting spectral sample

        Args:
            processing_steps: list of processing steps. If `None` is passed, the currently valid
                processing steps will be removed.
            timeout: timeout [ms] for setting processing steps. Default:REQUEST_TIMEOUT_IN_MS
        """
        message = f"{Scpi.MEASURE_SPECTRUM_REQUEST_CONFIG_PROCESSING_COMMAND}"

        if processing_steps:
            message = f"{message} {','.join([step.value for step in processing_steps])}"
        self._request_with_error_check(message=message, timeout=timeout)

    def get_averaged_spectra(
        self, timeout: int = REQUEST_TIMEOUT_IN_MS
    ) -> typing.Generator[Spectrum, typing.Any]:
        """
        Obtain averaged spectra

        The number of spectra used for the averaged spectrum can be adjusted with
        `MEASure:SPECtrum:AVERage:NUMBer`.

        Args:
            timeout: timeout [ms] for averaged spectra request. Default: REQUEST_TIMEOUT_IN_MS

        Returns:
            averaged spectra
        """

        # adjust processing steps to obtain averaged spectra; other processing steps are removed
        self.set_processing([ProcessingStep.AVERAGE], timeout=timeout)
        return self._spectrum_generator(timeout=timeout)

    def process_request_with_error_check(
        self, command: str, timeout: int = REQUEST_TIMEOUT_IN_MS
    ) -> str:
        """
        Send a command to the Spektralwerk

        A single command several commands, separated by a semicolon (;), are send to the
        Spektralwerk.

        Args:
            command: string to be processed to the Spektralwerk
            timeout: timeout [ms] for process request. Default: REQUEST_TIMEOUT_IN_MS

        Returns:
            raw response of the provided command
        """
        return self._request_with_error_check(command, timeout=timeout)
