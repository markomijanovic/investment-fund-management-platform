import json
import os
import time
import uuid
from datetime import datetime, timezone

from bson import ObjectId

from common.clients import create_mongo_database, create_redis_client
from common.orders import (
    ACTIVE_VOTES_KEY,
    get_vote,
    remove_order,
    remove_vote,
)
from services.director.blockchain import BlockchainGateway


def outcome_from_status(status: dict) -> str:
    if status.get("vetoed"):
        return "VETOED"
    if status.get("approved"):
        return "APPROVED"
    return "REJECTED"


def apply_final_outcome(database, metadata: dict, status: dict):
    order_uuid = metadata["uuid"]
    outcome = outcome_from_status(status)
    now = datetime.now(timezone.utc)

    database.processed_votes.update_one(
        {"_id": order_uuid},
        {
            "$setOnInsert": {
                "outcome": outcome,
                "processed_at": now,
                "applied": False,
                "contract_address": metadata["contract_address"],
            }
        },
        upsert=True,
    )
    marker = database.processed_votes.find_one({"_id": order_uuid})
    if marker.get("applied"):
        return

    order = metadata["order"]
    if outcome == "APPROVED" and order["order_type"] == "BUY":
        database.assets.update_one(
            {"vote_uuid": order_uuid},
            {
                "$setOnInsert": {
                    "name": order["name"],
                    "categories": order["categories"],
                    "buying_price": order["buying_price"],
                    "buying_date": marker["processed_at"],
                    "info": order.get("info", {}),
                    "vote_uuid": order_uuid,
                }
            },
            upsert=True,
        )
    elif outcome == "APPROVED" and order["order_type"] == "SELL":
        database.assets.update_one(
            {"_id": ObjectId(order["id"])},
            {
                "$set": {
                    "selling_price": order["selling_price"],
                    "selling_date": marker["processed_at"],
                    "sale_vote_uuid": order_uuid,
                }
            },
        )

    database.processed_votes.update_one(
        {"_id": order_uuid},
        {"$set": {"applied": True}},
    )


def release_lock(redis_client, lock_key: str, token: str):
    with redis_client.pipeline() as pipeline:
        while True:
            try:
                pipeline.watch(lock_key)
                if pipeline.get(lock_key) != token:
                    pipeline.unwatch()
                    return
                pipeline.multi()
                pipeline.delete(lock_key)
                pipeline.execute()
                return
            except Exception as error:
                if error.__class__.__name__ != "WatchError":
                    raise


def check_contracts(redis_client, database, blockchain):
    processed = 0
    for order_uuid in redis_client.zrange(ACTIVE_VOTES_KEY, 0, -1):
        metadata = get_vote(redis_client, order_uuid)
        if metadata is None:
            redis_client.zrem(ACTIVE_VOTES_KEY, order_uuid)
            continue

        lock_key = f"checker-lock:{order_uuid}"
        lock_token = str(uuid.uuid4())
        if not redis_client.set(lock_key, lock_token, nx=True, ex=55):
            continue
        try:
            status = blockchain.status(metadata["contract_address"])
            if not status["ended"]:
                continue
            apply_final_outcome(database, metadata, status)
            remove_order(redis_client, order_uuid)
            remove_vote(redis_client, order_uuid)
            processed += 1
        finally:
            release_lock(redis_client, lock_key, lock_token)
    return processed


def main():
    redis_client = create_redis_client()
    database = create_mongo_database()
    blockchain = BlockchainGateway()
    once = os.getenv("CHECK_ONCE", "true").lower() in {"1", "true", "yes"}
    interval = int(os.getenv("CHECK_INTERVAL_SECONDS", "10"))

    while True:
        processed = check_contracts(redis_client, database, blockchain)
        print(json.dumps({"processed_contracts": processed}), flush=True)
        if once:
            return
        time.sleep(interval)


if __name__ == "__main__":
    main()
