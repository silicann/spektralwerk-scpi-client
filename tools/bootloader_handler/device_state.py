import enum
import logging

from spektralwerk_scpi_client.exceptions import (
    SpektralwerkConnectionError,
    SpektralwerkError,
)
from tools.bootloader_handler.spektralwerk_core_bootloader import (
    SpektralwerkCoreBootloader,
)

logger = logging.getLogger(__name__)


class SpektralwerkState(enum.Enum):
    BOOTLOADER = "bootloader"
    APPLICATION = "application"
    UNKNOWN = "unknown"

    @classmethod
    def get_current_state(cls, client: SpektralwerkCoreBootloader, attempts=3):
        """
        Detect the current context of Spektralwerk Core
        """
        for _ in range(attempts):
            try:
                state = client.get_state()
                if state is None:
                    logger.debug("Current state is unknown. Retry.")
                    continue
                break
            except SpektralwerkError:
                state = None
        else:
            state = None

        response = {
            client.STATE_BOOTLOADER: cls.BOOTLOADER,
            client.STATE_APPLICATION: cls.APPLICATION,
            None: cls.UNKNOWN,
        }[state]
        logger.info("Current Spektralwerk state is: %s", response)
        return response

    def switch_to_state(self, spektralwerk: SpektralwerkCoreBootloader):
        try:
            current_state = self.get_current_state(spektralwerk)
        except SpektralwerkConnectionError:
            logger.exception("%s")
        original_state = current_state
        wanted_state = self

        if current_state is SpektralwerkState.UNKNOWN:
            logger.exception(
                "Cannot switch to %s because the current device state is unknown.",
                wanted_state,
            )
            return False
        if current_state is wanted_state:
            return True

        for attempt in range(1, 5):
            try:
                self._switch_state_incrementally(
                    current_state, wanted_state, spektralwerk
                )
            except SpektralwerkConnectionError as exc:
                raise SpektralwerkConnectionError(
                    spektralwerk._host,  # noqa SLF001
                    spektralwerk._port,  # noqa SLF001
                ) from exc
            current_state = self.get_current_state(spektralwerk)

            if current_state is wanted_state:
                logger.info(
                    "Switched from state '%s' to '%s' in %d steps",
                    original_state,
                    wanted_state,
                    attempt,
                )
                return True

        logger.error("Giving up to reach target state after %d attempts", attempt)
        return False

    @classmethod
    def _switch_state_incrementally(
        cls,
        current_state: "SpektralwerkState",
        target_state: "SpektralwerkState",
        spektralwerk: SpektralwerkCoreBootloader,
    ):
        logger.debug(
            "Trying to switch state from '%s' to '%s'", current_state, target_state
        )
        if current_state is cls.APPLICATION:
            if target_state is cls.BOOTLOADER:
                # switch from application state to bootloader state
                spektralwerk.enter_bootloader()
        elif current_state is cls.BOOTLOADER:
            if target_state is cls.APPLICATION:
                # switch from bootloader state to application state
                # bootloader mode can be left by rebooting Spektralwerk
                spektralwerk.exit_bootloader()
                # spektralwerk.reboot_from_bootloader()
        else:
            error_msg = f"I have no idea how to switch from '{current_state}' to {target_state}."
            raise NotImplementedError(error_msg)
