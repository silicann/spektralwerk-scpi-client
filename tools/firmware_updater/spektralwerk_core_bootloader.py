import json
import logging
import os
import socket
import time
import typing

from spektralwerk_scpi_client.devices import SpektralwerkCore
from spektralwerk_scpi_client.exceptions import (
    SpektralwerkConnectionError,
    SpektralwerkTimeoutError,
)
from spektralwerk_scpi_client.scpi.commands import SCPICommand

logger = logging.getLogger(__name__)

# Maximum time to wait for a bootloader command response during normal control requests.
BOOTLOADER_TIMEOUT = 10
# Short timeout used while polling for bootloader availability after a reset/context switch.
BOOTLOADER_DETECT_TIMEOUT = 1
# Delay between bootloader availability probes while waiting for context switches.
BOOTLOADER_POLL_INTERVAL = 0.5
# Delay between SCPI availability probes while waiting for application startup.
APPLICATION_POLL_INTERVAL = 1
# Per raw SCPI socket probe timeout while waiting for application startup.
APPLICATION_DETECT_TIMEOUT = 1
# Minimal SCPI query used to detect whether the application interface is available.
SCPI_IDENTITY_QUERY = "*IDN?\n"
# Maximum time to wait for an optional upload result from legacy-compatible bootloaders.
UPLOAD_RESPONSE_TIMEOUT = 30
# Maximum time to wait for the bootloader network interface after a context switch.
BOOTLOADER_STARTUP_DURATION = 120
# Maximum time to wait for the application to become reachable after a bootloader reboot.
REBOOT_DURATION = 80
MAX_RETRY_ATTEMPTS = 4

DEFAULT_CHUNK_SIZE = 4096


class SpektralwerkCoreBootloader(SpektralwerkCore):
    """
    Spektralwerk Core Bootloader class

    The Spektralwerk Core Bootloader class provides additional functionalities:
    - switch between application and bootloader context
    - upload firmware version
    - perform factory reset
    """

    STATE_BOOTLOADER: typing.Literal["bootloader"] = "bootloader"
    STATE_APPLICATION: typing.Literal["application"] = "application"

    BOOTLOADER_IPV4 = "192.168.0.83"
    SPEKTRALWERK_FIRMWARE_UPLOAD_PORT = 5300
    SPEKTRALWERK_BOOTLOADER_PORT = 5301
    FIRMWARE_CHUNK_SIZE = DEFAULT_CHUNK_SIZE

    BOOTLOADER_EXIT_MSG = '{"command": "bootloader-exit"}\n'
    BOOTLOADER_REBOOT_MSG = '{"command": "reboot"}\n'
    BOOTLOADER_HELP_MSG = '{"command": "help"}\n'
    BOOTLOADER_FACTORY_RESET_MSG = '{"command": "factory-reset"}\n'

    def is_bootloader_available(
        self, timeout: float = BOOTLOADER_DETECT_TIMEOUT
    ) -> bool:
        """
        Check whether the bootloader control interface responds.
        """
        response = self._send_to_bootloader(
            self.BOOTLOADER_HELP_MSG, timeout=timeout, log_errors=False
        )
        return response is not None and response.get("success") is True

    def get_state(self) -> typing.Literal["application", "bootloader"] | None:
        """
        Determine the current Spektralwerk state.

        The Spektralwerk cen be in one of two different states. In `application` state, the SCPI
        interface is available, while in `bootloader` state only few selected options are available.

        In a first step, the reachability of the bootloader control interface is checked. If it is
        unavailable, the SCPI interface is checked. If neither application nor bootloader context is
        responding, the device state is not known.

        Returns:
            current Spektralwerk state information
        """
        if self.is_bootloader_available(timeout=BOOTLOADER_TIMEOUT):
            return self.STATE_BOOTLOADER

        logger.info(
            "Bootloader context unavailable on %s:%s",
            self.BOOTLOADER_IPV4,
            self.SPEKTRALWERK_BOOTLOADER_PORT,
        )
        try:
            # SCPI interface is not available right upon boot of the Spektralwerk. Therefore some additional time is
            # required and the timeout is increased.
            with self.apply_temporary_timeout(30):
                self.get_identity()
        except (SpektralwerkConnectionError, SpektralwerkTimeoutError) as exc:
            logger.info(
                "SCPI interface unavailable on %s:%s: %s",
                self._host,
                self._port,
                exc,
            )
            return None
        return self.STATE_APPLICATION

    def wait_for_bootloader(self, timeout: float = BOOTLOADER_STARTUP_DURATION) -> None:
        """
        Wait until the bootloader control interface responds.
        The device can reset quickly or slowly depending on network state.
        """
        deadline = time.monotonic() + timeout
        logger.info(
            "Waiting up to %s seconds for bootloader on %s:%s",
            timeout,
            self.BOOTLOADER_IPV4,
            self.SPEKTRALWERK_BOOTLOADER_PORT,
        )
        while time.monotonic() < deadline:
            if self.is_bootloader_available():
                logger.info("Accessed bootloader context.")
                return
            time.sleep(BOOTLOADER_POLL_INTERVAL * 5)
        raise SpektralwerkConnectionError(
            self.BOOTLOADER_IPV4, self.SPEKTRALWERK_BOOTLOADER_PORT
        )

    def wait_for_application(self, timeout: float = REBOOT_DURATION) -> None:
        """
        Wait until the SCPI application interface responds.

        This replaces the old fixed reboot delay and returns as soon as the application answers a
        minimal raw SCPI identity query. The raw socket probe avoids pyvisa spinning or blocking
        indefinitely while the device is rebooting.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._is_application_available():
                return
            time.sleep(APPLICATION_POLL_INTERVAL)
        raise SpektralwerkConnectionError(self._host, self._port)

    def _is_application_available(self) -> bool:
        """
        Check whether the SCPI application socket answers a minimal identity query.
        """
        try:
            with socket.create_connection(
                (self._host, self._port), timeout=APPLICATION_DETECT_TIMEOUT
            ) as sock:
                sock.settimeout(APPLICATION_DETECT_TIMEOUT)
                sock.sendall(SCPI_IDENTITY_QUERY.encode("ascii"))
                return bool(sock.recv(DEFAULT_CHUNK_SIZE))
        except OSError:
            return False

    def enter_bootloader(self) -> None:
        """
        Enter bootloader context from application context

        A SCPI command is used in the application context to access bootloader context. The
        bootloader context provides additional functions, e.g. factory reset and firmware update.

        While in `bootloader` context, the SCPI interface is disabled and send messages will time
        out.
        """
        message = SCPICommand.SYSTEM_ACTION_BOOTLOADER_ENTER_COMMAND
        try:
            logger.info(
                "Switching to bootloader. Please be patient, this takes several seconds"
            )
            self._request_without_error_check(message=message)
        except (SpektralwerkTimeoutError, SpektralwerkConnectionError):
            # once the bootloader is entered, the existing connection will throw a timeout exception
            # which can be ignored.
            logger.debug("SCPI interface unavailable while in bootloader context")
        self.wait_for_bootloader()

    def exit_bootloader(self) -> None:
        """
        Exit bootloader context and resume with application context
        """
        for attempt in range(1, 5):
            response = self._send_to_bootloader(self.BOOTLOADER_EXIT_MSG)
            if response is not None and response.get("success"):
                logger.debug(
                    "Leaving bootloader context and switch to application context."
                )
                time.sleep(60)
                return
            if attempt < MAX_RETRY_ATTEMPTS:
                time.sleep(5)
                logger.warning("Leaving bootloader context failed. Retry: %s", attempt)
            else:
                logger.error("Leaving bootloader context failed.")

    def reboot_from_bootloader(self) -> None:
        """
        Reboot the Spektralwerk from the bootloader context

        Rebooting is device will lead to normal application mode.
        """
        for attempt in range(1, 5):
            response = self._send_to_bootloader(self.BOOTLOADER_REBOOT_MSG)
            if response is not None and response.get("success"):
                logger.info("Reboot command was successfully received.")
                logger.info(
                    "Rebooting to application context. Please be patient, this takes several seconds."
                )
                self.wait_for_application()
                break
            if attempt < MAX_RETRY_ATTEMPTS:
                time.sleep(5)
                logger.warning(
                    "Rebooting from bootloader context failed. Retry: %s.", attempt
                )
            else:
                logger.error("Rebooting failed.")

    def _send_to_bootloader(
        self,
        message: str,
        timeout: float = BOOTLOADER_TIMEOUT,
        *,
        log_errors: bool = True,
    ) -> dict[str, typing.Any] | None:
        """
        Send a message to the bootloader context of the Spektralwerk

        Returns:
            dict with at least a "success" key-value pair. The value is a boolean.
        """
        try:
            with socket.create_connection(
                (self.BOOTLOADER_IPV4, self.SPEKTRALWERK_BOOTLOADER_PORT),
                timeout=timeout,
            ) as sock:
                sock.sendall(message.encode("utf8"))
                try:
                    response = sock.recv(self.FIRMWARE_CHUNK_SIZE)
                except TimeoutError:
                    if log_errors:
                        logger.exception("No response received.")
                    return None
                else:
                    if response:
                        return json.loads(response.decode("utf-8", errors="replace"))
                    logger.error("Error: connection closed without response")

        except OSError as exc:
            if log_errors:
                logger.exception("TCP connection to bootloader failed")
            else:
                logger.debug(
                    "TCP connection to bootloader at %s:%s failed: %s",
                    self.BOOTLOADER_IPV4,
                    self.SPEKTRALWERK_BOOTLOADER_PORT,
                    exc,
                )
            return {"success": False}
        return None

    def upload_firmware(self, firmware_blob: typing.BinaryIO) -> bool:
        """
        Upload firmware blob.
        """
        if firmware_blob.closed:
            logger.error("Firmware")
            return False

        try:
            firmware_blob.seek(0)
            total_size = os.fstat(firmware_blob.fileno()).st_size

            with socket.create_connection(
                (self.BOOTLOADER_IPV4, self.SPEKTRALWERK_FIRMWARE_UPLOAD_PORT)
            ) as sock:
                sock.settimeout(UPLOAD_RESPONSE_TIMEOUT)
                sent = 0
                last_progress = -1
                while chunk := firmware_blob.read(self.FIRMWARE_CHUNK_SIZE):
                    sock.sendall(chunk)
                    sent += len(chunk)

                    last_progress = log_progress(sent, total_size, last_progress)

                response = self.wait_for_upload_response(sock)
                if response is not None:
                    if response.get("success") is True:
                        logger.info("Upload complete")
                        return True
                    logger.error("Firmware upload failed: %s", response)
                    return False

            logger.info("Upload complete without bootloader status response")

        except (ConnectionError, TimeoutError):
            # Catches Refused, Reset, Aborted, and network timeouts
            logger.exception("Network error during firmware upload: %s")
            return False
        except OSError:
            # Catches local fstat/read failures or unresolved host errors
            logger.exception("Local file or system error: %s")
            return False
        else:
            return True

        finally:
            firmware_blob.close()

    def reset_to_factory_settings(self) -> bool:
        """
        Reset the Spektralwerk to it's default factory settings.

        The factory resets all user and network settings and configurations to their default values.

        Returns:
            boolean value indicating the success of the factory reset
        """

        if self.get_state() == "application":
            self.enter_bootloader()
        response = self._send_to_bootloader(message=self.BOOTLOADER_FACTORY_RESET_MSG)

        return bool(response is not None and response.get("success") is True)

    def wait_for_upload_response(
        self, sock: socket.socket
    ) -> dict[str, typing.Any] | None:
        received_buffer = ""
        while True:
            try:
                response = sock.recv(self.FIRMWARE_CHUNK_SIZE)
            except TimeoutError:
                return None

            if not response:
                return None

            received_buffer += response.decode("utf-8", errors="replace")
            while "\n" in received_buffer:
                line, received_buffer = received_buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    status = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("Ignoring invalid upload response: %s", line)
                    continue
                if status.get("event") == "complete" or "success" in status:
                    return status


PROGRESS_LOG_STEP = 5


def log_progress(sent: int, total: int, last_progress: int = -1) -> int:
    percent = 100.0 if total == 0 else min(sent / total * 100, 100.0)
    progress = int(percent // PROGRESS_LOG_STEP) * PROGRESS_LOG_STEP

    if sent < total and progress <= last_progress:
        return last_progress

    logger.info(
        "Firmware upload progress: %.1f%% (%d/%d bytes)",
        percent,
        sent,
        total,
    )
    return progress
