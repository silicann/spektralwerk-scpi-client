from __future__ import annotations

import logging
import time
import typing

import pyvisa

from spektralwerk_scpi_client.exceptions import (
    SpektralwerkConnectionError,
    SpektralwerkResponseError,
    SpektralwerkTimeoutError,
)
from spektralwerk_scpi_client.scpi.commands import SCPICommand as Scpi

_logger = logging.getLogger()


class Spectrum(typing.NamedTuple):
    timestamp_sec: float
    data: list[float]


# NOTE: The Spektralwerk Core needs some ms before the next connection is accepted. Therefore
# the DEVICE_RECONNECTION_DELAY is introduced to delay the finalization of a query.
# Any delay >= 0.5 ms works fine. Below, 0.5 ms the device might hang.
DEVICE_RECONNECTION_DELAY = 0.5

# using the open source pyvisa-py backend since NI-VISA is closed sources
VISA_BACKEND = "@py"


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

    def _init_resource(self, resource: pyvisa.Resource) -> None:
        resource.clear()

    def _finalize_resource(self, resource: pyvisa.Resource) -> None:
        resource.close()
        time.sleep(DEVICE_RECONNECTION_DELAY)

    def _request_handler(self, resource: pyvisa.Resource, message: str) -> str:
        # append query of the event status register
        message_with_esr = f"{message};{Scpi.ESR_QUERY}"
        response_with_esr = resource.query(message_with_esr)  # type: ignore
        if self.command_separator in response_with_esr:
            response, event_status_register = response_with_esr.rsplit(
                self.command_separator, 1
            )
        else:
            response, event_status_register = "", response_with_esr
        # any value different than "0" indicates a SCPI error
        # the current error is obtained from the error queue of the device
        if event_status_register != "0":
            error_code, error_message = resource.query(  # type: ignore
                Scpi.SYSTEM_ERROR_NEXT_QUERY
            ).split(",")
            raise SpektralwerkResponseError(message, error_code, error_message)
        return response

    def _request(self, message: str) -> str:
        _logger.debug("Query sent: %s", message)
        try:
            with pyvisa.ResourceManager(VISA_BACKEND).open_resource(
                self._resource,
                read_termination=self.read_termination,
                write_termination=self.write_termination,
            ) as session:
                self._init_resource(session)
                response = self._request_handler(session, message)
                self._finalize_resource(session)
        except ConnectionRefusedError:
            raise SpektralwerkConnectionError(self._host, self._port) from None
        # pyvista raises unspecific exceptions which contain a status code with the precise error
        # description
        except Exception as exc:
            if str(pyvisa.constants.StatusCode.error_timeout) in str(exc):
                raise SpektralwerkTimeoutError from None
            raise
        _logger.debug("Response received: %s", response)
        return response

    def get_identity(self) -> str:
        """
        Obtain the Spektralwerk identity

        The identity contains vendor, name, serial and firmware version.

        Returns:
            Spektralwerk identity
        """
        message = Scpi.IDN_QUERY
        return self._request(message=message)

    def get_spectrometer_peak_cont(self) -> int:
        """
        Obtain the maximum spectrometer count value

        Returns:
            Maximum spectrometer count value
        """
        message = Scpi.DEVICE_SPECTROMETER_PEAK_QUERY
        return int(self._request(message=message))

    def get_spectrometer_resolution(self) -> float:
        """
        Obtain the average resolution of the spectrometer

        Returns:
            Averaged spectrometer resolution
        """
        message = Scpi.DEVICE_SPECTROMETER_RESOLUTION_QUERY
        return float(self._request(message=message))

    def get_pixels_count(self) -> int:
        """
        Obtain the number of pixel available

        Returns:
            pixel count
        """
        message = Scpi.DEVICE_SPECTROMETER_PIXELS_COUNT_QUERY
        return int(self._request(message=message))

    def get_pixel_wavelengths(self) -> list[float]:
        """
        Obtain wavelength value per pixel

        Returns:
            array with wavelength value for each pixel
        """
        message = Scpi.DEVICE_SPECTROMETER_PIXELS_WAVELENGTH_QUERY
        wavelengths = (self._request(message=message)).split(",")
        return [float(wavelength) for wavelength in wavelengths]

    def get_exposure_time(self) -> float:
        """
        Obtain current exposure time value

        Returns:
            bare exposure time value without unit
        """
        message = Scpi.MEASURE_SPECTRUM_EXPOSURE_TIME_QUERY
        response = self._request(message=message)
        # TODO: the current firmware response contains the exposure time value and the
        # current unit. Once the two are separated the cast to float can be done
        # without splitting the string before.
        return float(response.split(" ")[0])

    def set_exposure_time(self, exposure_time: float) -> None:
        """
        Set the exposure time

        Args:
            exposure time in µs
        """
        message = f"{Scpi.MEASURE_SPECTRUM_EXPOSURE_TIME_COMMAND} {exposure_time}"
        self._request(message=message)

    def get_exposure_time_max(self) -> float:
        """
        Obtain maximum exposure time value

        Returns:
            bare maximum exposure time value without unit
        """
        message = Scpi.MEASURE_SPECTRUM_EXPOSURE_TIME_MAX_QUERY
        response = self._request(message=message)
        # TODO: the current firmware response contains the exposure time value and the
        # current unit. Once the two are separated the cast to float can be done
        # without splitting the string before.
        return float(response.split(" ")[0])

    def get_exposure_time_min(self) -> float:
        """
        Obtain minimum exposure time value

        Returns:
            bare minimum exposure time value without unit
        """
        message = Scpi.MEASURE_SPECTRUM_EXPOSURE_TIME_MIN_QUERY
        response = self._request(message=message)
        # TODO: the current firmware response contains the exposure time value and the
        # current unit. Once the two are separated the cast to float can be done
        # without splitting the string before.
        return float(response.split(" ")[0])

    def get_average_number(self) -> int:
        """
        Obtain current value for number of averaged spectra

        Returns:
            current value for number of averaged spectra
        """
        message = Scpi.MEASURE_SPECTRUM_AVERAGE_NUMBER_QUERY
        response = self._request(message=message)
        return int(response)

    def set_average_number(self, number_of_spectra: int) -> None:
        """
        Set the number of averaged spectra applied for requested spectra (rolling average width).

        Args:
            number_of_spectra: number of spectra used for the rolling average
        """
        message = f"{Scpi.MEASURE_SPECTRUM_AVERAGE_NUMBER_COMMAND} {number_of_spectra}"
        self._request(message=message)

    def get_average_number_max(self) -> int:
        """
        Obtain max value for number of averaged spectra

        Returns:
            maximum value for number of averaged spectra
        """
        message = Scpi.MEASURE_SPECTRUM_AVERAGE_NUMBER_MAX_QUERY
        response = self._request(message=message)
        return int(response)

    def get_average_number_min(self) -> int:
        """
        Obtain minimum value for number of averaged spectra

        Returns:
            minimum value for number of averaged spectra
        """
        message = Scpi.MEASURE_SPECTRUM_AVERAGE_NUMBER_MIN_QUERY
        response = self._request(message=message)
        return int(response)

    def get_offset_voltage(self) -> float:
        """
        Obtain current value for spectrometer pixel offset voltage

        Returns:
            current value for spectrometer pixel offset voltage
        """
        message = Scpi.DEVICE_SPECTROMETER_BACKGROUND_OFFSET_VOLTAGE_QUERY
        response = self._request(message=message)
        # TODO: the current firmware response contains the offset voltage value and the
        # current unit. Once the two are separated the cast to float can be done
        # without splitting the string before.
        return float(response.split(" ")[0])

    def set_offset_voltage(self, offset_voltage: float) -> None:
        """
        Set the spectrometer pixel offset voltage

        Args:
            offset_voltage in mV
        """
        message = f"{Scpi.DEVICE_SPECTROMETER_BACKGROUND_OFFSET_VOLTAGE_COMMAND} {offset_voltage}"
        self._request(message=message)

    def get_offset_voltage_max(self) -> float:
        """
        Obtain maximum value for spectrometer pixel offset voltage

        Returns:
            maximum value for spectrometer pixel offset voltage
        """
        message = Scpi.DEVICE_SPECTROMETER_BACKGROUND_OFFSET_VOLTAGE_MAX_QUERY
        response = self._request(message=message)
        # TODO: the current firmware response contains the offset voltage value and the
        # current unit. Once the two are separated the cast to float can be done
        # without splitting the string before.
        return float(response.split(" ")[0])

    def get_offset_voltage_min(self) -> float:
        """
        Obtain minimum value for spectrometer pixel offset voltage

        Returns:
            minimum value for spectrometer pixel offset voltage
        """
        message = Scpi.DEVICE_SPECTROMETER_BACKGROUND_OFFSET_VOLTAGE_MIN_QUERY
        response = self._request(message=message)
        # TODO: the current firmware response contains the offset voltage value and the
        # current unit. Once the two are separated the cast to float can be done
        # without splitting the string before.
        return float(response.split(" ")[0])

    def get_spectra(self) -> typing.Generator[Spectrum, typing.Any]:
        """
        Obtain raw spectra

        Returns:
            raw spectra
        """
        message = Scpi.MEASURE_SPECTRUM_SAMPLE_RAW_QUERY
        while True:
            [timestamp_msec, *spectral_data] = (self._request(message=message)).split(
                ","
            )
            # the timestamp delivered from the Spektralwerk is in µs and is delivered in seconds
            timestamp_sec = float(timestamp_msec) / 1_000_000
            yield Spectrum(timestamp_sec, [float(value) for value in spectral_data])

    def get_averaged_spectra(self) -> typing.Generator[Spectrum, typing.Any]:
        """
        Obtain avaeraged raw spectra

        Returns:
            averaged raw spectra
        """
        message = Scpi.MEASURE_SPECTRUM_SAMPLE_RAW_AVERAGED_QUERY
        while True:
            [timestamp_msec, *spectral_data] = (self._request(message=message)).split(
                ","
            )
            # The Spektralwerk Core returns the spectral timestamp in µs. The timestamp returned with the spectrum in in s
            timestamp_sec = float(timestamp_msec) / 1_000_000
            yield Spectrum(timestamp_sec, [float(value) for value in spectral_data])

    def process_request(self, command: str) -> str:
        """
        Send a command to the Spektralwerk

        A single command several commands, separated by a semicolon (;), are send to the
        Spektralwerk.

        Args:
            command: string to be processed to the Spektralwerk

        Returns:
            raw response of the provided command
        """
        return self._request(command)
