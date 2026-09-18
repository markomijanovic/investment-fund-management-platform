import re
from datetime import datetime, timezone
from numbers import Real

from dateutil.parser import isoparse


ETHEREUM_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")


def is_missing(payload: dict, field: str) -> bool:
    if field not in payload or payload[field] is None:
        return True
    return isinstance(payload[field], str) and len(payload[field]) == 0


def missing_message(field: str) -> str:
    return f"Field {field} is missing."


def positive_number(value) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool) and value > 0


def parse_iso8601(value: str) -> datetime:
    parsed = isoparse(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def valid_ethereum_address(value) -> bool:
    return isinstance(value, str) and ETHEREUM_ADDRESS.fullmatch(value) is not None

