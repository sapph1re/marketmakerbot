from decimal import Decimal
import configparser
from custom_logging import get_logger
logger = get_logger(__name__)

config = configparser.ConfigParser(
    inline_comment_prefixes=('#', ';'),
    converters={'decimal': Decimal}
)
