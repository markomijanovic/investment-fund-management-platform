import fakeredis
import mongomock
import pytest
from flask_jwt_extended import create_access_token


TEST_SECRET = "test-secret-with-enough-entropy-12345"


@pytest.fixture
def mongo_database():
    return mongomock.MongoClient().investment_fund


@pytest.fixture
def redis_client():
    return fakeredis.FakeRedis(decode_responses=True)


def token_for(app, role="employee", email="user@example.com"):
    with app.app_context():
        return create_access_token(
            identity=email,
            additional_claims={
                "forename": "Test",
                "surname": "User",
                "email": email,
                "role": role,
            },
        )


def authorization(token):
    return {"Authorization": f"Bearer {token}"}
