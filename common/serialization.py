from datetime import datetime, timezone


def iso8601(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def serialize_asset(document: dict) -> dict:
    result = {
        "id": str(document["_id"]),
        "name": document["name"],
        "categories": document["categories"],
        "buying_date": iso8601(document["buying_date"]),
        "buying_price": document["buying_price"],
        "info": document.get("info", {}),
    }
    if document.get("selling_date") is not None:
        result["selling_date"] = iso8601(document["selling_date"])
    if document.get("selling_price") is not None:
        result["selling_price"] = document["selling_price"]
    return result

