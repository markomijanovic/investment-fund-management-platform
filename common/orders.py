import json
import time
import uuid


PENDING_ORDERS_KEY = "pending_orders"
ACTIVE_VOTES_KEY = "active_votes"


def order_key(order_uuid: str) -> str:
    return f"order:{order_uuid}"


def vote_key(order_uuid: str) -> str:
    return f"vote:{order_uuid}"


def add_order(redis_client, order: dict) -> str:
    order_uuid = str(uuid.uuid4())
    stored = {"uuid": order_uuid, **order}
    pipeline = redis_client.pipeline(transaction=True)
    pipeline.set(order_key(order_uuid), json.dumps(stored))
    pipeline.zadd(PENDING_ORDERS_KEY, {order_uuid: time.time()})
    pipeline.execute()
    return order_uuid


def get_order(redis_client, order_uuid: str):
    raw = redis_client.get(order_key(order_uuid))
    return json.loads(raw) if raw else None


def list_orders(redis_client) -> list[dict]:
    result = []
    stale = []
    for order_uuid in redis_client.zrange(PENDING_ORDERS_KEY, 0, -1):
        order = get_order(redis_client, order_uuid)
        if order is None:
            stale.append(order_uuid)
        else:
            result.append(order)
    if stale:
        redis_client.zrem(PENDING_ORDERS_KEY, *stale)
    return result


def remove_order(redis_client, order_uuid: str):
    pipeline = redis_client.pipeline(transaction=True)
    pipeline.delete(order_key(order_uuid))
    pipeline.zrem(PENDING_ORDERS_KEY, order_uuid)
    pipeline.execute()


def store_vote(redis_client, order_uuid: str, metadata: dict):
    pipeline = redis_client.pipeline(transaction=True)
    pipeline.set(vote_key(order_uuid), json.dumps(metadata))
    pipeline.zadd(ACTIVE_VOTES_KEY, {order_uuid: time.time()})
    pipeline.execute()


def get_vote(redis_client, order_uuid: str):
    raw = redis_client.get(vote_key(order_uuid))
    return json.loads(raw) if raw else None


def remove_vote(redis_client, order_uuid: str):
    pipeline = redis_client.pipeline(transaction=True)
    pipeline.delete(vote_key(order_uuid))
    pipeline.zrem(ACTIVE_VOTES_KEY, order_uuid)
    pipeline.execute()

