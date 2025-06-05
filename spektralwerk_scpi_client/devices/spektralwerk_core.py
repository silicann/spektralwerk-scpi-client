from __future__ import annotations

import logging
import time
import typing

import pyvisa

from spektralwerk_scpi_client.exceptions import (
    SpektralwerkConnectionError,
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

    def _command(self, message: str) -> None:
        _logger.debug("Query sent: %s", message)
        try:
            with pyvisa.ResourceManager(VISA_BACKEND).open_resource(
                self._resource,
                read_termination=self.read_termination,
                write_termination=self.write_termination,
            ) as session:
                self._init_resource(session)
                session.write(message)  # type: ignore
                self._finalize_resource(session)
        except ConnectionRefusedError:
            raise SpektralwerkConnectionError(self._host, self._port) from None
        # pyvista raises unspecific exceptions which contain a status code with the precise error
        # description
        except Exception as exc:
            if str(pyvisa.constants.StatusCode.error_timeout) in str(exc):
                raise SpektralwerkTimeoutError from None
            raise

    def _query(self, message: str) -> str:
        _logger.debug("Query sent: %s", message)
        try:
            with pyvisa.ResourceManager(VISA_BACKEND).open_resource(
                self._resource,
                read_termination=self.read_termination,
                write_termination=self.write_termination,
            ) as session:
                self._init_resource(session)
                response = session.query(message)  # type: ignore
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
        message = Scpi.IDENTITY.get_query_string()
        return self._query(message=message)

    def get_pixels_count(self) -> int:
        """
        Obtain the number of pixel available

        Returns:
            pixel count
        """
        message = Scpi.DEVICE_SPECTROMETER_PIXELS_COUNT.get_query_string()
        return int(self._query(message=message))

    def get_pixel_wavelengths(self) -> list[float]:
        """
        Obtain wavelength value per pixel

        Returns:
            array with wavelength value for each pixel
        """
        message = Scpi.DEVICE_SPECTROMETER_PIXELS_WAVELENGTH.get_query_string()
        wavelengths = (self._query(message=message)).split(",")
        return [float(wavelength) for wavelength in wavelengths]

    def get_exposure_time(self) -> float:
        """
        Obtain current exposure time value

        Returns:
            bare exposure time value without unit
        """
        message = Scpi.MEASURE_SPECTRUM_EXPOSURE_TIME.get_query_string()
        response = self._query(message=message)
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
        message = Scpi.MEASURE_SPECTRUM_EXPOSURE_TIME.get_command_string(str(exposure_time))
        self._command(message=message)

    def get_exposure_time_max(self) -> float:
        """
        Obtain maximum exposure time value

        Returns:
            bare maximum exposure time value without unit
        """
        message = Scpi.MEASURE_SPECTRUM_EXPOSURE_TIME_MAX.get_query_string()
        response = self._query(message=message)
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
        message = Scpi.MEASURE_SPECTRUM_EXPOSURE_TIME_MIN.get_query_string()
        response = self._query(message=message)
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
        message = Scpi.MEASURE_SPECTRUM_AVERAGE_NUMBER.get_query_string()
        response = self._query(message=message)
        return int(response)

    def set_average_number(self, number_of_spectra: int) -> None:
        """
        Set the number of averaged spectra applied for requested spectra (rolling average width).

        Args:
            number_of_spectra: number of spectra used for the rolling average
        """
        message = Scpi.MEASURE_SPECTRUM_AVERAGE_NUMBER.get_command_string(str(number_of_spectra))
        self._command(message=message)

    def get_average_number_max(self) -> int:
        """
        Obtain max value for number of averaged spectra

        Returns:
            maximum value for number of averaged spectra
        """
        message = Scpi.MEASURE_SPECTRUM_AVERAGE_NUMBER_MAX.get_query_string()
        response = self._query(message=message)
        return int(response)

    def get_average_number_min(self) -> int:
        """
        Obtain minimum value for number of averaged spectra

        Returns:
            minimum value for number of averaged spectra
        """
        message = Scpi.MEASURE_SPECTRUM_AVERAGE_NUMBER_MIN.get_query_string()
        response = self._query(message=message)
        return int(response)

    def get_offset_voltage(self) -> float:
        """
        Obtain current value for spectrometer pixel offset voltage

        Returns:
            current value for spectrometer pixel offset voltage
        """
        message = Scpi.DEVICE_SPECTROMETER_PIXELS_OFFSET_VOLTAGE.get_query_string()
        response = self._query(message=message)
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
        message = Scpi.DEVICE_SPECTROMETER_PIXELS_OFFSET_VOLTAGE.get_command_string(str(offset_voltage))
        self._command(message=message)

    def get_offset_voltage_max(self) -> float:
        """
        Obtain maximum value for spectrometer pixel offset voltage

        Returns:
            maximum value for spectrometer pixel offset voltage
        """
        message = Scpi.DEVICE_SPECTROMETER_PIXELS_OFFSET_VOLTAGE_MAX.get_query_string()
        response = self._query(message=message)
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
        message = Scpi.DEVICE_SPECTROMETER_PIXELS_OFFSET_VOLTAGE_MIN.get_query_string()
        response = self._query(message=message)
        # TODO: the current firmware response contains the offset voltage value and the
        # current unit. Once the two are separated the cast to float can be done
        # without splitting the string before.
        return float(response.split(" ")[0])

    def get_spectra(self) -> typing.Generator[Spectrum, typing.Any]:
        """
        Obtain a single raw spectrum

        Returns:
            single spectrum
        """
        message = Scpi.MEASURE_SPECTRUM_SAMPLE_RAW.get_query_string()
        spectral_data = (self._query(message=message)).split(",")
        # the timestamp delivered from the Spektralwerk is in µs and is delivered in seconds
        timestamp_sec = float(spectral_data[0]) / 1_000_000
        yield Spectrum(timestamp_sec, [float(value) for value in spectral_data[1:]])
