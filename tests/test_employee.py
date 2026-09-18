from datetime import datetime, timedelta, timezone

from bson import ObjectId

from common.orders import list_orders
from services.employee.app import create_app
from tests.conftest import TEST_SECRET, authorization, token_for


def make_app(mongo_database, redis_client):
    return create_app(
        {"TESTING": True, "JWT_SECRET_KEY": TEST_SECRET},
        mongo_db=mongo_database,
        redis_client=redis_client,
    )


def test_buy_order_validation_and_storage(mongo_database, redis_client):
    app = make_app(mongo_database, redis_client)
    headers = authorization(token_for(app))
    client = app.test_client()

    missing = client.post("/create_buy_order", json={}, headers=headers)
    assert missing.json == {"message": "Field name is missing."}
    empty = client.post(
        "/create_buy_order",
        json={"name": "Zlato", "categories": [], "buying_price": 10, "info": {}},
        headers=headers,
    )
    assert empty.json == {"message": "Categories list is empty."}

    response = client.post(
        "/create_buy_order",
        json={
            "name": "Zlatna poluga",
            "categories": ["metal", "zlato"],
            "buying_price": 10000,
            "info": {"purity": 24, "origin": {"country": "RS"}},
        },
        headers=headers,
    )
    assert response.status_code == 200
    orders = list_orders(redis_client)
    assert len(orders) == 1
    assert orders[0]["order_type"] == "BUY"


def test_search_uses_all_filters(mongo_database, redis_client):
    now = datetime.now(timezone.utc)
    mongo_database.assets.insert_many(
        [
            {
                "name": "Zlatna poluga",
                "categories": ["metal"],
                "buying_price": 100,
                "buying_date": now,
                "selling_price": 150,
                "selling_date": now + timedelta(days=2),
                "info": {"purity": 24},
            },
            {
                "name": "Srebrna poluga",
                "categories": ["metal"],
                "buying_price": 80,
                "buying_date": now,
                "info": {"purity": 18},
            },
        ]
    )
    app = make_app(mongo_database, redis_client)
    response = app.test_client().post(
        "/search",
        json={
            "name": "zlatna",
            "category": "metal",
            "buying_date": (now - timedelta(days=1)).isoformat(),
            "selling_date": (now + timedelta(days=3)).isoformat(),
            "info_filters": [{"field": "purity", "operator": "gte", "value": 24}],
        },
        headers=authorization(token_for(app)),
    )
    assert response.status_code == 200
    assert [asset["name"] for asset in response.json["assets"]] == ["Zlatna poluga"]
    assert response.json["assets"][0]["selling_price"] == 150


def test_sell_order_requires_existing_object_id(mongo_database, redis_client):
    app = make_app(mongo_database, redis_client)
    headers = authorization(token_for(app))
    client = app.test_client()
    response = client.post(
        "/create_sell_order",
        json={"id": "bad", "selling_price": 20},
        headers=headers,
    )
    assert response.json == {"message": "Invalid id."}

    asset_id = mongo_database.assets.insert_one(
        {
            "name": "Akcija",
            "categories": ["hartije"],
            "buying_price": 10,
            "buying_date": datetime.now(timezone.utc),
            "info": {},
        }
    ).inserted_id
    response = client.post(
        "/create_sell_order",
        json={"id": str(asset_id), "selling_price": 20},
        headers=headers,
    )
    assert response.status_code == 200
    assert list_orders(redis_client)[0]["id"] == str(asset_id)


def test_only_employee_role_is_allowed(mongo_database, redis_client):
    app = make_app(mongo_database, redis_client)
    response = app.test_client().post(
        "/search",
        json={},
        headers=authorization(token_for(app, role="director")),
    )
    assert response.status_code == 401
    assert response.json == {"msg": "Missing Authorization Header"}
