import logging
import string


class GracefulStringFormatter(string.Formatter):
    """
    Avoids exceptions when an unexpected value is passed to logger,
    substitutes the "bad" values with the specified text instead.
    """
    def __init__(self, missing='NONE', bad_fmt='BADFORMAT'):
        """
        :param missing: text to display when the value is None
        :param bad_fmt: text to display when the value can't be formatted
        """
        self.missing = missing
        self.bad_fmt = bad_fmt

    def get_field(self, field_name, args, kwargs):
        # Handle a key not found
        try:
            val = super().get_field(field_name, args, kwargs)
        except (KeyError, AttributeError):
            val = None, field_name
        return val

    def format_field(self, value, spec):
        # handle an invalid format
        if value is None:
            return self.missing
        try:
            return super().format_field(value, spec)
        except ValueError:
            if self.bad_fmt is not None:
                return self.bad_fmt
            else:
                raise


string_formatter = GracefulStringFormatter(missing='NONE', bad_fmt='BADFORMAT')


class GracefulFormatter(logging.Formatter):
    """
    Formatter that uses the above failsafe string formatting
    """
    def __init__(self, fmt=None, datefmt=None, style='{'):
        super().__init__(fmt, datefmt, style)

    def formatMessage(self, record):
        return string_formatter.format(self._fmt, **record.__dict__)


class Message(object):
    def __init__(self, fmt, args):
        self.fmt = fmt
        self.args = args

    def __str__(self):
        return string_formatter.format(self.fmt, *self.args)


class StyleAdapter(logging.LoggerAdapter):
    """
    Use this adapter to enable the "{}" notation for parameters
    """
    def __init__(self, logger, extra=None):
        super(StyleAdapter, self).__init__(logger, extra or {})

    def log(self, level, msg, *args, **kwargs):
        if self.isEnabledFor(level):
            msg, kwargs = self.process(msg, kwargs)
            self.logger._log(level, Message(msg, args), (), **kwargs)


format_main_info = '{asctime}\t{levelname}\t[{filename}]\t{message}'
log_formatter_info = GracefulFormatter(format_main_info)
handler_console = logging.StreamHandler()
handler_console.setLevel(logging.INFO)
handler_console.setFormatter(log_formatter_info)


def get_logger(name):
    """
    Usage: logger = get_logger(__name__)
    logger.info('Some log message here: {}', message)
    :param name: logger name, usually __name__ is fine
    :return: logger
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # writing a general log to console
    logger.addHandler(handler_console)

    logger = StyleAdapter(logger)
    return logger
