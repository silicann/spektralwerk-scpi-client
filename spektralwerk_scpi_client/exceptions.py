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
