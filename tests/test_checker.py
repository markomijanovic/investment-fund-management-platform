from bson import ObjectId

from jobs.contract_checker import apply_final_outcome


def buy_metadata(order_uuid="11111111-1111-4111-8111-111111111111"):
    return {
        "uuid": order_uuid,
        "contract_address": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "order": {
            "uuid": order_uuid,
            "order_type": "BUY",
            "name": "Zlato",
            "categories": ["metal"],
            "buying_price": 100,
            "info": {"purity": 24},
        },
    }


def test_approved_buy_is_applied_idempotently(mongo_database):
    metadata = buy_metadata()
    status = {"ended": True, "approved": True, "vetoed": False}
    apply_final_outcome(mongo_database, metadata, status)
    apply_final_outcome(mongo_database, metadata, status)
    assert mongo_database.assets.count_documents({}) == 1
    assert mongo_database.assets.find_one({})["name"] == "Zlato"
    assert mongo_database.processed_votes.find_one({"_id": metadata["uuid"]})["applied"] is True


def test_veto_has_no_asset_effect(mongo_database):
    metadata = buy_metadata("22222222-2222-4222-8222-222222222222")
    apply_final_outcome(
        mongo_database,
        metadata,
        {"ended": True, "approved": False, "vetoed": True},
    )
    assert mongo_database.assets.count_documents({}) == 0
    assert mongo_database.processed_votes.find_one({"_id": metadata["uuid"]})["outcome"] == "VETOED"


def test_approved_sell_updates_existing_asset(mongo_database):
    asset_id = mongo_database.assets.insert_one({"name": "Akcija"}).inserted_id
    order_uuid = "33333333-3333-4333-8333-333333333333"
    metadata = {
        "uuid": order_uuid,
        "contract_address": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "order": {
            "uuid": order_uuid,
            "order_type": "SELL",
            "id": str(asset_id),
            "selling_price": 250,
        },
    }
    apply_final_outcome(
        mongo_database,
        metadata,
        {"ended": True, "approved": True, "vetoed": False},
    )
    asset = mongo_database.assets.find_one({"_id": ObjectId(str(asset_id))})
    assert asset["selling_price"] == 250
    assert asset["sale_vote_uuid"] == order_uuid

