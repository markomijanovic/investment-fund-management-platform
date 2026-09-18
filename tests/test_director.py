from datetime import datetime, timezone

from common.orders import add_order, get_vote
from services.director.app import create_app
from tests.conftest import TEST_SECRET, authorization, token_for


VOTERS = [
    "0x1111111111111111111111111111111111111111",
    "0x2222222222222222222222222222222222222222",
    "0x3333333333333333333333333333333333333333",
]


class FakeBlockchain:
    sender = "0x90f8bf6a479f320ead074411a4b0e7944ea8c9c1"

    def __init__(self):
        self.deployments = []

    def deploy(self, voters):
        self.deployments.append(voters)
        return "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

    def transaction_payloads(self, address):
        return {
            "approve_transaction": {"to": address, "data": "0xapprove"},
            "reject_transaction": {"to": address, "data": "0xreject"},
            "veto_transaction": {"to": address, "data": "0xveto", "from": self.sender},
        }


def make_app(mongo_database, redis_client, blockchain=None):
    return create_app(
        {"TESTING": True, "JWT_SECRET_KEY": TEST_SECRET},
        mongo_db=mongo_database,
        redis_client=redis_client,
        blockchain_gateway=blockchain or FakeBlockchain(),
    )


def test_decision_returns_three_transactions(mongo_database, redis_client):
    order_uuid = add_order(
        redis_client,
        {"order_type": "BUY", "name": "Zlato", "categories": ["metal"], "buying_price": 10, "info": {}},
    )
    blockchain = FakeBlockchain()
    app = make_app(mongo_database, redis_client, blockchain)
    response = app.test_client().post(
        "/decision",
        json={"uuid": order_uuid, "voters": VOTERS},
        headers=authorization(token_for(app, role="director")),
    )
    assert response.status_code == 200
    assert set(response.json) == {
        "approve_transaction",
        "reject_transaction",
        "veto_transaction",
    }
    assert response.json["veto_transaction"]["from"] == blockchain.sender
    assert get_vote(redis_client, order_uuid)["order"]["name"] == "Zlato"


def test_decision_validation_order(mongo_database, redis_client):
    app = make_app(mongo_database, redis_client)
    headers = authorization(token_for(app, role="director"))
    client = app.test_client()
    assert client.post("/decision", json={}, headers=headers).json == {
        "message": "Field uuid is missing."
    }
    assert client.post("/decision", json={"uuid": "bad"}, headers=headers).json == {
        "message": "Invalid uuid."
    }

    order_uuid = add_order(redis_client, {"order_type": "BUY"})
    assert client.post("/decision", json={"uuid": order_uuid}, headers=headers).json == {
        "message": "Field voters is missing."
    }
    assert client.post(
        "/decision",
        json={"uuid": order_uuid, "voters": VOTERS[:2]},
        headers=headers,
    ).json == {"message": "Even number of voters."}


def test_report_sorting_and_category_expansion(mongo_database, redis_client):
    now = datetime.now(timezone.utc)
    mongo_database.assets.insert_many(
        [
            {
                "name": "A",
                "categories": ["metal", "zlato"],
                "buying_price": 100,
                "buying_date": now,
                "selling_price": 200,
                "selling_date": now,
                "info": {},
            },
            {
                "name": "B",
                "categories": ["metal"],
                "buying_price": 50,
                "buying_date": now,
                "info": {},
            },
        ]
    )
    app = make_app(mongo_database, redis_client)
    response = app.test_client().get(
        "/report",
        headers=authorization(token_for(app, role="director")),
    )
    assert response.status_code == 200
    assert response.json["statistics"] == [
        {"category": "zlato", "spent": 100, "earned": 200},
        {"category": "metal", "spent": 150, "earned": 200},
    ]

