import os
import uuid as uuid_module

from flask import Flask, jsonify, request

from common.clients import create_mongo_database, create_redis_client
from common.orders import get_order, get_vote, list_orders, store_vote
from common.security import configure_jwt, role_required
from common.validation import valid_ethereum_address
from services.director.blockchain import BlockchainGateway


def valid_uuid(value) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(uuid_module.UUID(value)) == value.lower()
    except (ValueError, AttributeError):
        return False


def create_app(test_config=None, mongo_db=None, redis_client=None, blockchain_gateway=None):
    app = Flask(__name__)
    app.config.update(JWT_SECRET_KEY=os.getenv("JWT_SECRET_KEY", "development-secret-change-me"))
    if test_config:
        app.config.update(test_config)
    configure_jwt(app)

    database = mongo_db if mongo_db is not None else create_mongo_database()
    cache = redis_client if redis_client is not None else create_redis_client()
    chain = blockchain_gateway if blockchain_gateway is not None else BlockchainGateway()
    app.extensions["mongo_database"] = database
    app.extensions["redis_client"] = cache
    app.extensions["blockchain_gateway"] = chain

    @app.get("/pending_orders")
    @role_required("director")
    def pending_orders():
        return jsonify(orders=list_orders(cache)), 200

    @app.post("/decision")
    @role_required("director")
    def decision():
        payload = request.get_json(silent=True) or {}

        if "uuid" not in payload or payload["uuid"] in (None, ""):
            return jsonify(message="Field uuid is missing."), 400
        order_uuid = payload["uuid"]
        order = get_order(cache, order_uuid) if valid_uuid(order_uuid) else None
        if order is None:
            return jsonify(message="Invalid uuid."), 400

        if "voters" not in payload or not isinstance(payload["voters"], list) or not payload["voters"]:
            return jsonify(message="Field voters is missing."), 400
        voters = payload["voters"]
        if not all(valid_ethereum_address(voter) for voter in voters) or len(
            {voter.lower() for voter in voters}
        ) != len(voters):
            return jsonify(message="Invalid voter address."), 400
        if len(voters) % 2 == 0:
            return jsonify(message="Even number of voters."), 400

        existing = get_vote(cache, order_uuid)
        if existing is not None:
            return jsonify(chain.transaction_payloads(existing["contract_address"])), 200

        try:
            contract_address = chain.deploy(voters)
        except Exception as error:
            app.logger.exception("Blockchain deployment failed: %s", error)
            return jsonify(message="Blockchain unavailable."), 503

        store_vote(
            cache,
            order_uuid,
            {
                "uuid": order_uuid,
                "contract_address": contract_address,
                "director_address": chain.sender,
                "voters": voters,
                "order": order,
            },
        )
        return jsonify(chain.transaction_payloads(contract_address)), 200

    @app.get("/report")
    @role_required("director")
    def report():
        pipeline = [
            {"$unwind": "$categories"},
            {
                "$group": {
                    "_id": "$categories",
                    "spent": {"$sum": "$buying_price"},
                    "earned": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$and": [
                                        {"$ne": [{"$ifNull": ["$selling_date", None]}, None]},
                                        {"$ne": [{"$ifNull": ["$selling_price", None]}, None]},
                                    ]
                                },
                                "$selling_price",
                                0,
                            ]
                        }
                    },
                }
            },
            {"$sort": {"earned": -1, "spent": 1, "_id": 1}},
        ]
        statistics = [
            {"category": item["_id"], "spent": item["spent"], "earned": item["earned"]}
            for item in database.assets.aggregate(pipeline)
        ]
        return jsonify(statistics=statistics), 200

    @app.get("/health")
    def health():
        try:
            database.command("ping")
            cache.ping()
            if not chain.web3.is_connected():
                raise RuntimeError("Blockchain unavailable.")
        except Exception:
            return jsonify(status="unavailable"), 503
        return jsonify(status="ok"), 200

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
