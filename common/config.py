import os


def env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def sql_uri() -> str:
    explicit = os.getenv("SQLALCHEMY_DATABASE_URI")
    if explicit:
        return explicit

    user = os.getenv("SQL_USER", "iep")
    password = os.getenv("SQL_PASSWORD", "iep-password")
    host = os.getenv("SQL_HOST", "mysql")
    port = env_int("SQL_PORT", 3306)
    database = os.getenv("SQL_DATABASE", "users")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"


def mongo_uri() -> str:
    return os.getenv("MONGO_URI", "mongodb://mongo:27017")


def mongo_database() -> str:
    return os.getenv("MONGO_DATABASE", "investment_fund")


def redis_kwargs() -> dict:
    return {
        "host": os.getenv("REDIS_HOST", "redis"),
        "port": env_int("REDIS_PORT", 6379),
        "db": env_int("REDIS_DB", 0),
        "decode_responses": True,
    }

