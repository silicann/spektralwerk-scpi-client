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
from spektralwerk_scpi_client.scpi.commands import (
    SCPICommand as SCPI,  # noqa N814
)

logger = logging.getLogger(__name__)

VISA_TIMEOUT_CODE = "-1073807339"
BOOTLOADER_TIMEOUT = 10
REBOOT_DURATION = 80
MAX_RETRY_ATTEMPTS = 4


class SpektralwerkCoreBootloader(SpektralwerkCore):
    """
    Spektralwerk Core Bootloader class

    The Spektralwerk Core Bootloader class provides additional functionalities:
    - switch between application and bootloader context
    - upload firmware version
    - perform factory reset
    """

    STATE_BOOTLOADER = "bootloader"
    STATE_APPLICATION = "application"

    SPEKTRALWERK_FIRMWARE_UPLOAD_PORT = 5300
    SPEKTRALWERK_BOOTLOADER_PORT = 5301
    FIRMWARE_CHUNK_SIZE = 1024

    BOOTLOADER_EXIT_MSG = '{"command": "bootloader-exit"}\n'
    BOOTLOADER_REBOOT_MSG = '{"command": "reboot"}\n'
    BOOTLOADER_HELP_MSG = '{"command": "help"}\n'

    def get_state(self) -> typing.Literal["application", "bootloader"] | None:
        """
        Determine the current Spektralwerk state.

        The Spektralwerk cen be in one of two different states. In `application` state, the SCPI
        interface is available, while in `bootloader` state only few selected options are available.

        In a first step, the reachability of the SCPI interface is checked. If it fails with
        `SpektralwerkConnectionError`, the SCPI interface is unavailable and bootloader context is
        checked. If neither application nor bootloader context is responding, the device state is
        not known.

        Returns:
            current Spektralwerk state information
        """
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
        else:
            return self.STATE_APPLICATION

        response = self._send_to_bootloader(self.BOOTLOADER_HELP_MSG)
        if response is not None and response.get("success") is True:
            return self.STATE_BOOTLOADER

        logger.info(
            "Bootloader context unavailable on %s:%s",
            self._host,
            self.SPEKTRALWERK_BOOTLOADER_PORT,
        )
        return None

    def enter_bootloader(self) -> None:
        """
        Enter bootloader context from application context

        A SCPI command is used in the application context to access bootloader context. The
        bootloader context provides additional functions, e.g. factory reset and firmware update.

        While in `bootloader` context, the SCPI interface is disabled and send messages will time
        out.
        """
        message = SCPI.SYSTEM_ACTION_BOOTLOADER_ENTER_COMMAND
        try:
            logger.info(
                "Switching to bootloader. Please be patient, this takes several seconds"
            )
            self._request_without_error_check(message=message)
        except (SpektralwerkTimeoutError, SpektralwerkConnectionError):
            # once the bootloader is entered, the existing connection will throw a timeout exception
            # which can be ignored.
            logger.debug("SCPI interface unavailable while in bootloader context")
        time.sleep(120)
        if self.get_state() == self.STATE_BOOTLOADER:
            logger.info("Accessed bootloader context.")
            return
        raise SpektralwerkConnectionError(self._host, self.SPEKTRALWERK_BOOTLOADER_PORT)

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
                    "Rebooting to application context. Please be patient, this requires about %s seconds.",
                    REBOOT_DURATION,
                )
                # rebooting and recovering to application context takes about 70 seconds.
                time.sleep(REBOOT_DURATION)
                break
            if attempt < MAX_RETRY_ATTEMPTS:
                time.sleep(5)
                logger.warning(
                    "Rebooting from bootloader context failed. Retry: %s.", attempt
                )
            else:
                logger.error("Rebooting failed.")

    def _send_to_bootloader(self, message: str) -> dict[str, typing.Any] | None:
        """
        Send a message to the bootloader context of the Spektralwerk

        Returns:

        """
        try:
            with socket.create_connection(
                (self._host, self.SPEKTRALWERK_BOOTLOADER_PORT),
                timeout=BOOTLOADER_TIMEOUT,
            ) as sock:
                sock.sendall(message.encode("utf8"))
                try:
                    response = sock.recv(4096)
                except TimeoutError:
                    logger.exception("No response received.")
                    return
                else:
                    if response:
                        return json.loads(response.decode("utf-8", errors="replace"))
                    logger.error("Error: connection closed without response")

        except TimeoutError:
            return {"success": False}
        except OSError:
            logger.exception("TCP connection failed")
            return {"success": False}

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
                (self._host, self.SPEKTRALWERK_FIRMWARE_UPLOAD_PORT)
            ) as sock:
                sent = 0
                while chunk := firmware_blob.read(self.FIRMWARE_CHUNK_SIZE):
                    sock.sendall(chunk)
                    sent += len(chunk)

                    log_progress(sent, total_size)

            logger.info("Upload complete")
            time.sleep(70)

        except ConnectionRefusedError:
            logger.exception("Cannot connect and upload firmware image.")
            return False
        else:
            return True

        finally:
            firmware_blob.close()


PROGRESS_LOG_STEP = 5


def log_progress(sent: int, total: int) -> None:
    percent = 100.0 if total == 0 else min(sent / total * 100, 100.0)
    progress = int(percent // PROGRESS_LOG_STEP) * PROGRESS_LOG_STEP

    if sent < total and progress <= getattr(log_progress, "last_progress", -1):
        return

    log_progress.last_progress = progress
    logger.info(
        "Firmware upload progress: %.1f%% (%d/%d bytes)",
        percent,
        sent,
        total,
    )
