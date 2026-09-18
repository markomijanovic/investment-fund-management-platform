# Sentinel values used in expected-result fixtures for fields whose actual
# value is generated dynamically by the server (MongoDB ObjectIds, Redis
# UUIDs, timestamps). The comparator in utilities.py checks these fields for
# presence + correct format instead of exact equality.
ANY_OBJECT_ID = "<ANY_OBJECT_ID>"
ANY_UUID      = "<ANY_UUID>"
ANY_DATE      = "<ANY_DATE>"


# AUTHENTICATION DATA
employee = {
    "forename": "John",
    "surname":  "Doe",
    "email":    "john@gmail.com",
    "password": "aA123456",
}

is_registered = False


def get_employee():
    global employee
    return employee


def get_is_employee_registered():
    global is_registered
    return is_registered


def set_is_employee_registered(value):
    global is_registered
    is_registered = value


# BUY ORDER DATA
def get_buy_order0():
    return {
        "name":          "AssetAlpha",
        "categories":    ["Technology", "Finance"],
        "buying_price":  50000,
        "info":          {"region": "EU", "risk_level": "high"},
    }


def get_buy_order1():
    return {
        "name":          "AssetBeta",
        "categories":    ["Real Estate"],
        "buying_price":  120000,
        "info":          {"location": "NYC", "floors": 5},
    }

def get_buy_order2():
    return {
        "name":          "AssetZeta",
        "categories":    ["Energy"],
        "buying_price":  80000,
        "info":          {"region": "APAC", "risk_level": "medium"},
    }

def get_buy_order3():
    return {
        "name":          "AssetGamma",
        "categories":    ["Technology"],
        "buying_price":  30000,
        "info":          {"region": "US", "risk_level": "low"},
    }



def get_buy_order4():
    # Nested info object, used to exercise info_filters dot-path queries
    # (e.g. "geo.country", "specs.power_mw") against more than one level of
    # nesting.
    return {
        "name":          "AssetEpsilon",
        "categories":    ["Energy", "Technology"],
        "buying_price":  95000,
        "info": {
            "geo":   {"country": "Germany", "city": "Berlin"},
            "specs": {"power_mw": 50, "renewable": True},
        },
    }


# SEARCH RESULT DATA
def get_search_empty():
    return {"assets": []}


# Full expected asset shapes, used for field-by-field result evaluation.
# id/buying_date/selling_date are server-generated, so they use sentinels
# (checked for presence + valid format, not exact value).
def get_asset_alpha():
    return {
        "id":           ANY_OBJECT_ID,
        "name":         "AssetAlpha",
        "categories":   ["Technology", "Finance"],
        "buying_date":  ANY_DATE,
        "buying_price": 50000,
        "info":         {"region": "EU", "risk_level": "high"},
    }


def get_asset_alpha_sold():
    asset = get_asset_alpha()
    asset["selling_price"] = 75000
    asset["selling_date"]  = ANY_DATE
    return asset


def get_asset_beta():
    return {
        "id":           ANY_OBJECT_ID,
        "name":         "AssetBeta",
        "categories":   ["Real Estate"],
        "buying_date":  ANY_DATE,
        "buying_price": 120000,
        "info":         {"location": "NYC", "floors": 5},
    }


def get_asset_delta():
    return {
        "id":           ANY_OBJECT_ID,
        "name":         "AssetDelta",
        "categories":   ["Finance", "Real Estate"],
        "buying_date":  ANY_DATE,
        "buying_price": 200000,
        "info":         {"sector": "commercial", "floors": 10},
    }


def get_asset_epsilon():
    return {
        "id":           ANY_OBJECT_ID,
        "name":         "AssetEpsilon",
        "categories":   ["Energy", "Technology"],
        "buying_date":  ANY_DATE,
        "buying_price": 95000,
        "info": {
            "geo":   {"country": "Germany", "city": "Berlin"},
            "specs": {"power_mw": 50, "renewable": True},
        },
    }


# BUY ORDER ERROR DATA
def get_buy_order_error0():
    return {}


def get_buy_order_error1():
    return {"name": ""}


def get_buy_order_error2():
    return {"name": "A"}


def get_buy_order_error3():
    return {"name": "A", "categories": ["C"]}


def get_buy_order_error4():
    return {"name": "A", "categories": ["C"], "buying_price": 100}


def get_buy_order_error5():
    return {"name": "A", "categories": [], "buying_price": 100, "info": {}}


def get_buy_order_error6():
    return {"name": "A", "categories": ["C"], "buying_price": 0, "info": {}}


def get_buy_order_error7():
    return {"name": "A", "categories": ["C"], "buying_price": -100, "info": {}}


# SELL ORDER ERROR DATA
def get_sell_order_error0():
    return {}


def get_sell_order_error1():
    return {"id": ""}


def get_sell_order_error2():
    return {"id": "not-valid-objectid", "selling_price": 20000}


def get_sell_order_error3():
    return {"id": "5f43a0d1c2a4b12345678901", "selling_price": 20000}


# REPORT EXPECTED RESULTS
def get_report_alpha_sold(with_blockchain):
    """level2 report: Finance+Technology from AssetAlpha (sold). In
    no-blockchain mode, AssetBeta (Real Estate) was already approved
    synchronously back in level1, so it also shows up here; in blockchain
    mode that contract is left unvoted and never finalizes."""
    statistics = [
        {"category": "Finance",    "spent": 50000, "earned": 75000},
        {"category": "Technology", "spent": 50000, "earned": 75000},
    ]
    if not with_blockchain:
        statistics.append({"category": "Real Estate", "spent": 120000, "earned": 0})
    return {"statistics": statistics}


def get_report_full(with_blockchain):
    """Full level3 report: Technology+Finance from AssetAlpha (sold) and
    AssetDelta; Real Estate from AssetDelta plus AssetBeta. In blockchain
    mode, AssetBeta's level1 contract is left unvoted and never finalizes,
    so it doesn't contribute to Real Estate; in no-blockchain mode it was
    approved synchronously back in level1, so it does."""
    real_estate_spent = 200000 if with_blockchain else 200000 + 120000
    return {
        "statistics": [
            {"category": "Technology",  "spent": 50000,             "earned": 75000},
            {"category": "Finance",     "spent": 250000,            "earned": 75000},
            {"category": "Real Estate", "spent": real_estate_spent, "earned": 0},
        ]
    }


def get_report_full_with_epsilon(with_blockchain):
    """Same as get_report_full, but after AssetEpsilon (Energy + Technology,
    95000, unsold) is also approved: Technology's spent grows by AssetEpsilon's
    contribution, and a new Energy category appears."""
    real_estate_spent = 200000 if with_blockchain else 200000 + 120000
    return {
        "statistics": [
            {"category": "Technology",  "spent": 50000 + 95000,    "earned": 75000},
            {"category": "Finance",     "spent": 250000,           "earned": 75000},
            {"category": "Energy",      "spent": 95000,            "earned": 0},
            {"category": "Real Estate", "spent": real_estate_spent, "earned": 0},
        ]
    }
