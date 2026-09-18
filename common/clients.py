from pymongo import MongoClient
from redis import Redis

from common.config import mongo_database, mongo_uri, redis_kwargs


def create_redis_client():
    return Redis(**redis_kwargs())


def create_mongo_database():
    return MongoClient(mongo_uri())[mongo_database()]

