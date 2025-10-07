import logging

SUCCESS_LEVEL = 69
logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")


class CustomLogger(logging.Logger):
    """Custom logger with a SUCCESS level."""

    def success(self, message: str, *args, **kwargs):
        """Log a message with SUCCESS level"""
        if self.isEnabledFor(SUCCESS_LEVEL):
            self._log(SUCCESS_LEVEL, message, args, **kwargs)
