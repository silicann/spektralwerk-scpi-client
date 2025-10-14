from pydantic import BaseModel


class Identity(BaseModel):
    vendor: str
    model: str
    serial_number: str
    firmware_version: str
