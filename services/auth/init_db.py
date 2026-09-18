import os
import time

from sqlalchemy.exc import OperationalError
from werkzeug.security import generate_password_hash

from services.auth.app import create_app
from services.auth.models import User, db


DIRECTOR = {
    "forename": "Scrooge",
    "surname": "McDuck",
    "email": "onlymoney@gmail.com",
    "password": "evenmoremoney",
}


def initialize():
    attempts = int(os.getenv("DB_INIT_ATTEMPTS", "30"))
    delay = float(os.getenv("DB_INIT_DELAY", "2"))
    app = create_app()

    for attempt in range(1, attempts + 1):
        try:
            with app.app_context():
                db.create_all()
                director = User.query.filter_by(email=DIRECTOR["email"]).first()
                if director is None:
                    director = User(
                        forename=DIRECTOR["forename"],
                        surname=DIRECTOR["surname"],
                        email=DIRECTOR["email"],
                        password_hash=generate_password_hash(DIRECTOR["password"]),
                        role="director",
                    )
                    db.session.add(director)
                else:
                    director.role = "director"
                db.session.commit()
            print("SQL database initialized successfully.", flush=True)
            return
        except OperationalError as error:
            if attempt == attempts:
                raise
            print(f"Database unavailable ({attempt}/{attempts}): {error}", flush=True)
            time.sleep(delay)


if __name__ == "__main__":
    initialize()
