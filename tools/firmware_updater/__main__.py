import argparse
import enum
import logging
import time

from spektralwerk_scpi_client.exceptions import SpektralwerkConnectionError
from tools.firmware_updater.device_state import SpektralwerkState
from tools.firmware_updater.spektralwerk_core_bootloader import (
    SpektralwerkCoreBootloader,
)

logger = logging.getLogger(__name__)


class SpektralwerkAction(enum.Enum):
    ENTER_BOOTLOADER = "enter-bootloader"
    ENTER_APPLICATION = "enter-application"
    UPLOAD_APPLICATION = "upload-application"
    FIRMWARE_VERSION = "get-firmware-version"
    EMERGENCY_RESET = "reset-lost-device"

    def execute(self, spektralwerk: SpektralwerkCoreBootloader, args):
        # enter and stay in bootloader context
        if self is self.ENTER_BOOTLOADER:
            return SpektralwerkState.BOOTLOADER.switch_to_state(spektralwerk)

        # enter application context
        if self is self.ENTER_APPLICATION:
            return SpektralwerkState.APPLICATION.switch_to_state(spektralwerk)

        # upload new application
        if self is self.UPLOAD_APPLICATION:
            upload_file = args.upload_file
            if upload_file is None:
                logger.error("Missing '--upload-file' argument for this action.")
                return False
            # switch to bootloader context to upload an application release
            # in bootloader context, the Spektralwerk is only reachable via default IPv4 address
            # 192.168.0.83.
            if not SpektralwerkState.BOOTLOADER.switch_to_state(spektralwerk):
                logger.error(
                    "Failed to enter bootloader state before uploading firmware."
                )
                return False
            if not spektralwerk.upload_firmware(upload_file):
                return False
            spektralwerk.reboot_from_bootloader()
            return True

        # get the current firmware version
        if self is self.FIRMWARE_VERSION:
            if not SpektralwerkState.APPLICATION.switch_to_state(spektralwerk):
                logger.error(
                    "Failed to enter application context before requesting the firmware version."
                )
                return False
            logger.info(
                "Current firmware version: %s", spektralwerk.get_firmware_version()
            )
            return True

        # resets a lost Spektralwerk to factory settings
        if self is self.EMERGENCY_RESET:
            logger.info(
                "Waiting 30 seconds for bootloader at %s. Ensure this host can access "
                "192.168.0.0/24, then disconnect and reconnect the device power (PoE).",
                spektralwerk.BOOTLOADER_IPV4,
            )
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if spektralwerk.is_bootloader_available(timeout=0.5):
                    logger.info("Bootloader reached; resetting to factory settings.")
                    return spektralwerk.reset_to_factory_settings()
                time.sleep(min(0.5, max(0, deadline - time.monotonic())))
            logger.error("Bootloader was not reachable within 30 seconds.")
            return False
        error_msg = f"Missing implementation for action: {self}"
        raise NotImplementedError(error_msg)


def get_parsed_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--host",
        default="192.168.0.83",
        help="IP address or hostname of the Spektralwerk Core.",
    )
    parser.add_argument(
        "--port",
        default=5025,
        type=int,
        help="SCPI port of the Spektralwerk Core.",
    )
    parser.add_argument(
        "--log-level",
        default="warning",
        choices={key.lower() for key in logging.getLevelNamesMapping()},
        help="Wanted log level for output",
    )
    parser.add_argument(
        "--upload-file",
        type=argparse.FileType("rb"),
        help="Filename of a firmware image.",
    )
    parser.add_argument(
        "action",
        choices={item.value for item in SpektralwerkAction},
    )

    return parser.parse_args()


def main():
    args = get_parsed_args()
    log_level = logging.getLevelNamesMapping()[args.log_level.upper()]
    logging.basicConfig(
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        level=log_level,
    )

    spektralwerk = SpektralwerkCoreBootloader(host=args.host, port=args.port)
    action = SpektralwerkAction(args.action)
    try:
        action.execute(spektralwerk, args)
    except SpektralwerkConnectionError:
        logger.exception("%s")
        return 1
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
