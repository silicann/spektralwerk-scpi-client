from __future__ import annotations

import contextlib
import logging
import struct
import time
import typing

import cobs.cobs
import pyvisa

from spektralwerk_scpi_client.devices.models import Identity
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
                self.timeout = 0.2
                with self.apply_temporary_timeout(0.2):
                    error = self.get_error_message()
            except SpektralwerkError:
                # The connection is somehow lost forever. Stop asking questions.
                _logger.debug("SCPI request returned with non-zero status flag")
                raise SpektralwerkResponseError(
                    message,
                    event_status_register,
                ) from None
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
                        raise SpektralwerkTimeoutError from exc
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
                    yield response.rstrip(delimiter)

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
        output_format: OutputFormat | None = OutputFormat.COBS_INT16,
        spectra_count: int | None = None,
        sample_frequency: float | None = None,
        format_timestamp: str = "Q",
        format_pixel: str = "h",
    ) -> typing.Generator[Spectrum, typing.Any]:
        for query in (
            # infinite number of spectra to retrieve
            SCPI.MEASURE_SPECTRUM_REQUEST_CONFIG_COUNT_COMMAND.with_arguments(
                0 if spectra_count is None else spectra_count
            ),
            # as fast as possible
            SCPI.MEASURE_SPECTRUM_REQUEST_CONFIG_FREQUENCY_COMMAND.with_arguments(
                0 if sample_frequency is None else sample_frequency
            ),
            SCPI.MEASURE_SPECTRUM_REQUEST_CONFIG_FORMAT_COMMAND.with_arguments(
                output_format
            ),
        ):
            self._request_with_error_check(query)
        for raw_spectrum in self._request_stream(
            SCPI.MEASURE_SPECTRUM_REQUEST_QUERY, delimiter=b"\0"
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
        message = SCPI.MEASURE_SPECTRUM_EXPOSURE_TIME_QUERY
        response = self._request_with_error_check(message=message)
        return float(response)

    def set_exposure_time(self, exposure_time: float) -> None:
        """
        Set the exposure time

        Args:
            exposure time in µs
        """
        message = SCPI.MEASURE_SPECTRUM_EXPOSURE_TIME_COMMAND.with_arguments(
            exposure_time
        )
        self._request_with_error_check(message=message)

    def get_exposure_time_unit(self) -> str:
        """
        Get the unit of the exposure time

        Returns:
            unit of the exposure time
        """
        message = SCPI.MEASURE_SPECTRUM_EXPOSURE_TIME_UNIT_QUERY
        return self._request_with_error_check(message=message)

    def get_exposure_time_max(self) -> float:
        """
        Obtain maximum exposure time value

        Returns:
            bare maximum exposure time value
        """
        message = SCPI.MEASURE_SPECTRUM_EXPOSURE_TIME_MAX_QUERY
        response = self._request_with_error_check(message=message)
        return float(response)

    def get_exposure_time_min(self) -> float:
        """
        Obtain minimum exposure time value

        Returns:
            bare minimum exposure time value
        """
        message = SCPI.MEASURE_SPECTRUM_EXPOSURE_TIME_MIN_QUERY
        response = self._request_with_error_check(message=message)
        return float(response)

    def get_average_number(self) -> int:
        """
        Obtain current value for number of averaged spectra

        Returns:
            current value for number of averaged spectra
        """
        message = SCPI.MEASURE_SPECTRUM_AVERAGE_NUMBER_QUERY
        response = self._request_with_error_check(message=message)
        return int(response)

    def set_average_number(self, number_of_spectra: int) -> None:
        """
        Set the number of averaged spectra applied for requested spectra (rolling average width).

        Args:
            number_of_spectra: number of spectra used for the rolling average

        """
        message = SCPI.MEASURE_SPECTRUM_AVERAGE_NUMBER_COMMAND.with_arguments(
            number_of_spectra
        )
        self._request_with_error_check(message=message)

    def get_average_number_max(self) -> int:
        """
        Obtain max value for number of averaged spectra

        Returns:
            maximum value for number of averaged spectra
        """
        message = SCPI.MEASURE_SPECTRUM_AVERAGE_NUMBER_MAX_QUERY
        response = self._request_with_error_check(message=message)
        return int(response)

    def get_average_number_min(self) -> int:
        """
        Obtain minimum value for number of averaged spectra

        Returns:
            minimum value for number of averaged spectra
        """
        message = SCPI.MEASURE_SPECTRUM_AVERAGE_NUMBER_MIN_QUERY
        response = self._request_with_error_check(message=message)
        return int(response)

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

    def get_offset_voltag_unit(self) -> str:
        """
        Get the unit of the offset voltage

        Returns:
            unit of the offset voltage
        """
        message = SCPI.DEVICE_SPECTROMETER_BACKGROUND_OFFSET_VOLTAGE_UNIT_QUERY
        return self._request_with_error_check(message=message)

    def get_offset_voltage_max(self) -> float:
        """
        Obtain maximum value for spectrometer pixel offset voltage

        Returns:
            maximum value for spectrometer pixel offset voltage
        """
        message = SCPI.DEVICE_SPECTROMETER_BACKGROUND_OFFSET_VOLTAGE_MAX_QUERY
        response = self._request_with_error_check(message=message)
        return float(response)

    def get_offset_voltage_min(self) -> float:
        """
        Obtain minimum value for spectrometer pixel offset voltage

        Returns:
            minimum value for spectrometer pixel offset voltage
        """
        message = SCPI.DEVICE_SPECTROMETER_BACKGROUND_OFFSET_VOLTAGE_MIN_QUERY
        response = self._request_with_error_check(message=message)
        return float(response)

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

    def get_spectra(
        self, spectra_count: int | None = None
    ) -> typing.Generator[Spectrum, typing.Any]:
        """
        Obtain raw spectra

        Returns:
            incremental delivery of spectra
        """
        return self._spectrum_generator(spectra_count=spectra_count)

    def set_processing(
        self,
        processing_steps: list[ProcessingStep] | None,
    ) -> None:
        """
        Set processing steps for requesting spectral sample

        Args:
            processing_steps: list of processing steps. If `None` is passed, the currently valid
                processing steps will be removed.
        """
        message = f"{SCPI.MEASURE_SPECTRUM_REQUEST_CONFIG_PROCESSING_COMMAND}"

        if processing_steps:
            message = f"{message} {','.join([step.value for step in processing_steps])}"
        self._request_with_error_check(message=message)

    def get_request_count(self) -> int:
        message = f"{SCPI.MEASURE_SPECTRUM_REQUEST_CONFIG_COUNT_QUERY}"
        return int(self._request_with_error_check(message=message))

    def set_request_count(self, count: int) -> None:
        """
        Set the number of spectra to obtain from a single call
        """
        message = SCPI.MEASURE_SPECTRUM_REQUEST_CONFIG_COUNT_COMMAND.with_arguments(
            count
        )
        self._request_with_error_check(message=message)

    def get_request_roi(self) -> tuple[int, int]:
        """
        Obtain the region-of-interest

        The region-of-interest limits the spectral output to the provided pixel range.

        Returns:
            region-of-interest
        """
        message = f"{SCPI.MEASURE_SPECTRUM_REQUEST_CONFIG_ROI_QUERY}"
        try:
            roi_str = self._request_with_error_check(message=message).split(",")
            roi = ROI(*[int(value) for value in roi_str])
        except TypeError as exc:
            raise SpektralwerkUnexpectedResponseError from exc
        return roi

    def set_request_roi(self, roi: tuple[int, int]) -> None:
        message = f"{SCPI.MEASURE_SPECTRUM_REQUEST_CONFIG_ROI_COMMAND} {','.join(str(pixel) for pixel in roi)}"
        self._request_with_error_check(message=message)

    def get_averaged_spectra(
        self,
    ) -> typing.Generator[Spectrum, typing.Any]:
        """
        Obtain averaged spectra

        The number of spectra used for the averaged spectrum can be adjusted with
        `MEASure:SPECtrum:AVERage:NUMBer`.

        Returns:
            averaged spectra
        """

        # adjust processing steps to obtain averaged spectra; other processing steps are removed
        self.set_processing([ProcessingStep.AVERAGE])
        return self._spectrum_generator()

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
