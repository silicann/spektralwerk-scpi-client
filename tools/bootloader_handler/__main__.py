import argparse
import enum
import logging

from spektralwerk_scpi_client.exceptions import SpektralwerkConnectionError
from tools.bootloader_handler.device_state import SpektralwerkState
from tools.bootloader_handler.spektralwerk_core_bootloader import (
    SpektralwerkCoreBootloader,
)

logger = logging.getLogger(__name__)


class SpektralwerkAction(enum.Enum):
    ENTER_BOOTLOADER = "enter-bootloader"
    ENTER_APPLICATION = "enter-application"
    UPLOAD_APPLICATION = "upload-application"
    FIRMWARE_VERSION = "get-firmware-version"

    def execute(self, spektralwerk: SpektralwerkCoreBootloader, args):
        if self is self.ENTER_BOOTLOADER:
            # enter bootloader context
            return SpektralwerkState.BOOTLOADER.switch_to_state(spektralwerk)
        if self is self.ENTER_APPLICATION:
            # enter application context
            return SpektralwerkState.APPLICATION.switch_to_state(spektralwerk)
        if self is self.UPLOAD_APPLICATION:
            # TODO: enter bootloader context and upload a file
            upload_file = args.upload_file
            if upload_file is None:
                logger.error("Missing '--upload-file' argument for this action.")
                return False
            # switch to bootloader context
            if not SpektralwerkState.BOOTLOADER.switch_to_state(spektralwerk):
                logger.error(
                    "Failed to enter bootloader state before uploading firmware."
                )
                return False
            spektralwerk.upload_firmware(upload_file)
            spektralwerk.reboot_from_bootloader()
            return True
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
        else:
            raise NotImplementedError(f"Missing implementation for action: {self}")


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
    except SpektralwerkConnectionError as exc:
        logger.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
