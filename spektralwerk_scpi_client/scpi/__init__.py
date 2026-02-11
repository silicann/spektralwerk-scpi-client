import dataclasses


@dataclasses.dataclass
class SCPIErrorMessage:
    code: int
    message: str
