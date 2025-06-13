import enum


class SCPICommand(enum.StrEnum):
    QUERY_END = "?"

    def get_query_string(self) -> str:
        """
        Wrap the command and provide a SCPI compatible query string
        """

        if self.value.endswith(self.QUERY_END):
            return f"{self}"
        return f"{self.value}{self.QUERY_END}"

    def get_command_string(self, content) -> str:
        """
        Wrap the command and additional content into a SCPI compatible command string.
        """
        return f"{self} {content}"

    # SCPI standard/IEEE 488 commands
    IDENTITY = "*IDN?"
    ESR = "*ESR?"
    SYSTEM_ERROR_NEXT = "SYSTem:ERRor:NEXT"

    # Spektralwerk SCPI commands
    DEVICE_SPECTROMETER_PEAK = "DEVice:SPECtrometer:PEAK"
    DEVICE_SPECTROMETER_PIXELS_COUNT = "DEVice:SPECtrometer:PIXels:COUNt"
    DEVICE_SPECTROMETER_PIXELS_WAVELENGTH = "DEVice:SPECtrometer:PIXels:WAVelength"
    DEVICE_SPECTROMETER_RESOLUTION = "DEVice:SPECtrometer:RESolution"

    DEVICE_SPECTROMETER_PIXELS_OFFSET_VOLTAGE = "DEVice:SPECtrometer:PIXels:OFFSet:VOLTage"
    DEVICE_SPECTROMETER_PIXELS_OFFSET_VOLTAGE_MAX = "DEVice:SPECtrometer:PIXels:OFFSet:VOLTage:MAXimum"
    DEVICE_SPECTROMETER_PIXELS_OFFSET_VOLTAGE_MIN = "DEVice:SPECtrometer:PIXels:OFFSet:VOLTage:MINimum"

    MEASURE_SPECTRUM_AVERAGE_NUMBER = "MEASure:SPECtrum:AVERage:NUMBer"
    MEASURE_SPECTRUM_AVERAGE_NUMBER_MAX = "MEASure:SPECtrum:AVERage:NUMBer:MAXimum"
    MEASURE_SPECTRUM_AVERAGE_NUMBER_MIN = "MEASure:SPECtrum:AVERage:NUMBer:MINimum"

    MEASURE_SPECTRUM_EXPOSURE_TIME = "MEASure:SPECtrum:EXPosure:TIME"
    MEASURE_SPECTRUM_EXPOSURE_TIME_MAX = "MEASure:SPECtrum:EXPosure:TIME:MAXimum"
    MEASURE_SPECTRUM_EXPOSURE_TIME_MIN = "MEASure:SPECtrum:EXPosure:TIME:MINimum"

    MEASURE_SPECTRUM_SAMPLE_RAW = "MEASure:SPECtrum:SAMPle:RAW"
    MEASURE_SPECTRUM_SAMPLE_RAW_AVERAGED = "MEASure:SPECtrum:SAMPle:RAW:AVERaged"
