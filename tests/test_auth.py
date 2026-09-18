from services.auth.app import create_app
from services.auth.models import db
from tests.conftest import TEST_SECRET, authorization


def make_app():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "JWT_SECRET_KEY": TEST_SECRET,
        }
    )
    with app.app_context():
        db.create_all()
    return app


def test_register_login_and_delete_flow():
    app = make_app()
    client = app.test_client()
    registration = {
        "forename": "Paja",
        "surname": "Patak",
        "email": "paja@example.com",
        "password": "very-secret",
    }

    assert client.post("/register", json=registration).status_code == 200
    duplicate = client.post("/register", json=registration)
    assert duplicate.status_code == 400
    assert duplicate.json == {"message": "Email already exists."}

    response = client.post(
        "/login",
        json={"email": registration["email"], "password": registration["password"]},
    )
    assert response.status_code == 200
    assert isinstance(response.json["accessToken"], str)

    deleted = client.post("/delete", headers=authorization(response.json["accessToken"]))
    assert deleted.status_code == 200
    invalid = client.post(
        "/login",
        json={"email": registration["email"], "password": registration["password"]},
    )
    assert invalid.json == {"message": "Invalid credentials."}


def test_auth_validation_order_and_missing_header():
    client = make_app().test_client()
    response = client.post("/register", json={"surname": "Patak"})
    assert response.json == {"message": "Field forename is missing."}

    response = client.post("/register", json={
        "forename": "Paja",
        "surname": "Patak",
        "email": "not-an-email",
        "password": "short",
    })
    assert response.json == {"message": "Invalid email."}

    response = client.post("/register", json={
        "forename": "John",
        "surname": "Doe",
        "email": "john@gmail.a",
        "password": " ",
    })
    assert response.json == {"message": "Invalid email."}

    response = client.post("/login", json={
        "email": "john@gmail.a",
        "password": " ",
    })
    assert response.json == {"message": "Invalid email."}

    response = client.post("/delete")
    assert response.status_code == 401
    assert response.json == {"msg": "Missing Authorization Header"}
