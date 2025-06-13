class SpektralwerkError(Exception):
    """
    Base class for errors with a Spektralwerk device
    """


class SpektralwerkConnectionError(SpektralwerkError):
    """
    Connection to the Spektralwerk could not be established.
    """

    def __init__(self, host, port):
        super().__init__(f"Connection to {host}:{port} is refused.")


class SpektralwerkTimeoutError(SpektralwerkError):
    """
    The command could not be resolved.
    """


class SpektralwerkResponseError(SpektralwerkError):
    """
    The used SCPI command returned an error

    The SCPI handler error response and the SCPI error code are included in
    SpektralwerkResponseError
    """

    def __init__(self, command, scpi_error_code: str, scpi_error_message: str):
        self.scpi_error_code = scpi_error_code
        self.scpi_error_message = scpi_error_message
        super().__init__(
            f"The command {command} lead to {self.scpi_error_code} - {self.scpi_error_message}."
        )
