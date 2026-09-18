import os
import re
from datetime import timedelta

from email_validator import EmailNotValidError, validate_email
from flask import Flask, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash

from common.config import sql_uri
from common.security import configure_jwt
from common.validation import is_missing, missing_message
from services.auth.models import User, db


REGISTER_FIELDS = ("forename", "surname", "email", "password")
LOGIN_FIELDS = ("email", "password")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


def normalized_email(value: str) -> str:
    if not isinstance(value, str) or EMAIL_PATTERN.fullmatch(value) is None:
        raise EmailNotValidError("Invalid email.")
    return validate_email(value, check_deliverability=False).normalized.lower()


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI=sql_uri(),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        JWT_SECRET_KEY=os.getenv("JWT_SECRET_KEY", "development-secret-change-me"),
        JWT_ACCESS_TOKEN_EXPIRES=timedelta(hours=1),
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    configure_jwt(app)

    @app.post("/register")
    def register():
        payload = request.get_json(silent=True) or {}
        for field in REGISTER_FIELDS:
            if is_missing(payload, field):
                return jsonify(message=missing_message(field)), 400

        try:
            email = normalized_email(payload["email"])
        except (EmailNotValidError, TypeError):
            return jsonify(message="Invalid email."), 400

        if len(email) > 256:
            return jsonify(message="Invalid email."), 400
        if not isinstance(payload["password"], str) or not 8 <= len(payload["password"]) <= 256:
            return jsonify(message="Invalid password."), 400
        if not isinstance(payload["forename"], str) or len(payload["forename"]) > 256:
            return jsonify(message="Invalid forename."), 400
        if not isinstance(payload["surname"], str) or len(payload["surname"]) > 256:
            return jsonify(message="Invalid surname."), 400

        if User.query.filter_by(email=email).first() is not None:
            return jsonify(message="Email already exists."), 400

        user = User(
            forename=payload["forename"],
            surname=payload["surname"],
            email=email,
            password_hash=generate_password_hash(payload["password"]),
            role="employee",
        )
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify(message="Email already exists."), 400
        return "", 200

    @app.post("/login")
    def login():
        payload = request.get_json(silent=True) or {}
        for field in LOGIN_FIELDS:
            if is_missing(payload, field):
                return jsonify(message=missing_message(field)), 400

        try:
            email = normalized_email(payload["email"])
        except (EmailNotValidError, TypeError):
            return jsonify(message="Invalid email."), 400

        user = User.query.filter_by(email=email).first()
        if user is None or not check_password_hash(user.password_hash, payload["password"]):
            return jsonify(message="Invalid credentials."), 400

        claims = {
            "forename": user.forename,
            "surname": user.surname,
            "email": user.email,
            "role": user.role,
        }
        token = create_access_token(identity=user.email, additional_claims=claims)
        return jsonify(accessToken=token), 200

    @app.post("/delete")
    @jwt_required()
    def delete_user():
        user = User.query.filter_by(email=get_jwt_identity()).first()
        if user is None:
            return jsonify(message="Unknown user."), 400
        db.session.delete(user)
        db.session.commit()
        return "", 200

    @app.get("/health")
    def health():
        try:
            User.query.limit(1).all()
        except SQLAlchemyError:
            return jsonify(status="unavailable"), 503
        return jsonify(status="ok"), 200

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
