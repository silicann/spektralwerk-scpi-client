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

    # SCPI commands
    DEVICE_SPECTROMETER_PIXELS_COUNT = "DEVice:SPECtrometer:PIXels:COUNt"
    DEVICE_SPECTROMETER_PIXELS_WAVELENGTH = "DEVice:SPECtrometer:PIXels:WAVelength"

    IDENTITY = "IDN?"

    MEASURE_SPECTRUM_AVERAGE_NUMBER = "MEASure:SPECtrum:AVERage:NUMBer"
    MEASURE_SPECTRUM_EXPOSURE_TIME = "MEASure:SPECtrum:EXPosure:TIME"

    MEASURE_SPECTRUM_SAMPLE_RAW = "MEASure:SPECtrum:SAMPle:RAW"
