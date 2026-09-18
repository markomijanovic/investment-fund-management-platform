import os
import re

from bson import ObjectId
from bson.errors import InvalidId
from flask import Flask, jsonify, request

from common.clients import create_mongo_database, create_redis_client
from common.orders import add_order
from common.security import configure_jwt, role_required
from common.serialization import serialize_asset
from common.validation import is_missing, missing_message, parse_iso8601, positive_number


BUY_FIELDS = ("name", "categories", "buying_price", "info")
SELL_FIELDS = ("id", "selling_price")
OPERATORS = {
    "eq": "$eq",
    "ne": "$ne",
    "gt": "$gt",
    "gte": "$gte",
    "lt": "$lt",
    "lte": "$lte",
    "in": "$in",
    "nin": "$nin",
}
FIELD_PATH = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


def create_app(test_config=None, mongo_db=None, redis_client=None):
    app = Flask(__name__)
    app.config.update(JWT_SECRET_KEY=os.getenv("JWT_SECRET_KEY", "development-secret-change-me"))
    if test_config:
        app.config.update(test_config)
    configure_jwt(app)

    database = mongo_db if mongo_db is not None else create_mongo_database()
    cache = redis_client if redis_client is not None else create_redis_client()
    app.extensions["mongo_database"] = database
    app.extensions["redis_client"] = cache

    @app.post("/search")
    @role_required("employee")
    def search():
        payload = request.get_json(silent=True) or {}
        clauses = []

        if "name" in payload and payload["name"] not in (None, ""):
            if not isinstance(payload["name"], str) or len(payload["name"]) > 256:
                return jsonify(message="Invalid name."), 400
            clauses.append({"name": {"$regex": re.escape(payload["name"]), "$options": "i"}})

        if "category" in payload and payload["category"] not in (None, ""):
            if not isinstance(payload["category"], str) or len(payload["category"]) > 256:
                return jsonify(message="Invalid category."), 400
            clauses.append({"categories": payload["category"]})

        if "buying_date" in payload and payload["buying_date"] not in (None, ""):
            try:
                buying_date = parse_iso8601(payload["buying_date"])
            except (TypeError, ValueError, OverflowError):
                return jsonify(message="Invalid buying date."), 400
            clauses.append({"buying_date": {"$gt": buying_date}})

        if "selling_date" in payload and payload["selling_date"] not in (None, ""):
            try:
                selling_date = parse_iso8601(payload["selling_date"])
            except (TypeError, ValueError, OverflowError):
                return jsonify(message="Invalid selling date."), 400
            clauses.append(
                {
                    "selling_date": {
                        "$exists": True,
                        "$ne": None,
                        "$lt": selling_date,
                    }
                }
            )

        filters = payload.get("info_filters", [])
        if filters is None:
            filters = []
        if not isinstance(filters, list):
            return jsonify(message="Invalid info filters."), 400
        for item in filters:
            if not isinstance(item, dict):
                return jsonify(message="Invalid info filter."), 400
            field = item.get("field")
            operator = item.get("operator")
            if not isinstance(field, str) or FIELD_PATH.fullmatch(field) is None:
                return jsonify(message="Invalid info filter."), 400
            if operator not in OPERATORS or "value" not in item:
                return jsonify(message="Invalid info filter."), 400
            clauses.append({f"info.{field}": {OPERATORS[operator]: item["value"]}})

        query = {"$and": clauses} if clauses else {}
        assets = [serialize_asset(document) for document in database.assets.find(query)]
        return jsonify(assets=assets), 200

    @app.post("/create_buy_order")
    @role_required("employee")
    def create_buy_order():
        payload = request.get_json(silent=True) or {}
        for field in BUY_FIELDS:
            if is_missing(payload, field):
                return jsonify(message=missing_message(field)), 400

        categories = payload["categories"]
        if not isinstance(categories, list) or len(categories) == 0:
            return jsonify(message="Categories list is empty."), 400
        if not all(isinstance(category, str) and 0 < len(category) <= 256 for category in categories):
            return jsonify(message="Invalid categories."), 400
        if not positive_number(payload["buying_price"]):
            return jsonify(message="Invalid buying price."), 400
        if not isinstance(payload["name"], str) or len(payload["name"]) > 256:
            return jsonify(message="Invalid name."), 400
        if not isinstance(payload["info"], dict):
            return jsonify(message="Invalid info."), 400

        add_order(
            cache,
            {
                "order_type": "BUY",
                "name": payload["name"],
                "categories": categories,
                "buying_price": payload["buying_price"],
                "info": payload["info"],
            },
        )
        return "", 200

    @app.post("/create_sell_order")
    @role_required("employee")
    def create_sell_order():
        payload = request.get_json(silent=True) or {}
        for field in SELL_FIELDS:
            if is_missing(payload, field):
                return jsonify(message=missing_message(field)), 400

        try:
            asset_id = ObjectId(payload["id"])
        except (InvalidId, TypeError, ValueError):
            return jsonify(message="Invalid id."), 400
        if database.assets.find_one({"_id": asset_id}) is None:
            return jsonify(message="Invalid id."), 400
        if not positive_number(payload["selling_price"]):
            return jsonify(message="Invalid selling price."), 400

        add_order(
            cache,
            {
                "order_type": "SELL",
                "id": str(asset_id),
                "selling_price": payload["selling_price"],
            },
        )
        return "", 200

    @app.get("/health")
    def health():
        try:
            database.command("ping")
            cache.ping()
        except Exception:
            return jsonify(status="unavailable"), 503
        return jsonify(status="ok"), 200

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
