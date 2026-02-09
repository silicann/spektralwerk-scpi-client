import enum


class ProcessingStep(enum.StrEnum):
    AVERAGE = "average"


class OutputFormat(enum.StrEnum):
    HUMAN = "human"
    BASE64_INT16 = "base64_int16"
    BASE64_FLOAT = "base64_float"
    COBS_INT16 = "cobs_int16"
