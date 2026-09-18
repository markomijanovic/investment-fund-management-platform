from functools import wraps
from datetime import timedelta

from flask import jsonify
from flask_jwt_extended import JWTManager, get_jwt, jwt_required


def configure_jwt(app):
    app.config.setdefault("JWT_SECRET_KEY", "development-secret-change-me")
    app.config.setdefault("JWT_ACCESS_TOKEN_EXPIRES", timedelta(hours=1))
    jwt = JWTManager(app)

    @jwt.unauthorized_loader
    def missing_token(reason):
        if reason == "Missing Authorization Header":
            return jsonify(msg="Missing Authorization Header"), 401
        return jsonify(msg=reason), 401

    return jwt


def role_required(role: str):
    def decorator(function):
        @wraps(function)
        @jwt_required()
        def wrapped(*args, **kwargs):
            if get_jwt().get("role") != role:
                return jsonify(msg="Missing Authorization Header"), 401
            return function(*args, **kwargs)

        return wrapped

    return decorator
