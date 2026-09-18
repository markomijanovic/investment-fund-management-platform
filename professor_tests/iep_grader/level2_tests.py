import time

from utilities import equals
from utilities import run_tests
from utilities import set_up_director_headers
from utilities import evaluate_assets_test
from utilities import evaluate_report_test
from utilities import vote_and_wait
from utilities import set_up_wait_for_asset
from data      import get_asset_alpha
from data      import get_asset_alpha_sold
from data      import get_report_alpha_sold


def run_level2_tests(with_authentication, authentication_url, employee_url, director_url, with_blockchain, voter_private_keys, provider_url):
    # Shared mutable stores
    alpha_uuid      = []   # UUID of AssetAlpha buy order
    alpha_sell_uuid = []   # UUID of AssetAlpha sell order
    alpha_asset_id  = []   # MongoDB id of AssetAlpha after approval
    tx_store        = []   # transaction data from /decision response (blockchain mode)

    # Voter addresses (only meaningful in blockchain mode)
    if with_blockchain and voter_private_keys:
        try:
            from web3 import Account
            voter_addresses = [Account.from_key(pk).address for pk in voter_private_keys]
        except Exception:
            voter_addresses = [
                "0x90F8bf6A479f320ead074411a4B0e7944Ea8c9C1",
                "0xFFcf8FDEE72ac11b5c542428B35EEF5769C409f0",
                "0x22d491Bde2303f2f43325b2108D26f1eAbA1e32b",
            ]
    else:
        voter_addresses = [
            "0x90F8bf6A479f320ead074411a4B0e7944Ea8c9C1",
            "0xFFcf8FDEE72ac11b5c542428B35EEF5769C409f0",
            "0x22d491Bde2303f2f43325b2108D26f1eAbA1e32b",
        ]

    # ------------------------------------------------------------------
    # Setup: get pending UUID for AssetAlpha BUY order, approve it
    # ------------------------------------------------------------------
    def set_up_alpha_buy_decision(url, headers, data, files):
        from utilities import director_login, get_pending_orders
        if with_authentication:
            director_login(authentication_url, headers)
        orders = get_pending_orders(with_authentication, authentication_url, director_url)
        buy_orders = [o for o in orders if o.get("order_type") == "BUY"]
        alpha_orders = [o for o in buy_orders if o.get("name") == "AssetAlpha"]
        assert alpha_orders, (
            f"Expected a pending BUY order for 'AssetAlpha', got buy orders: "
            f"{[o.get('name') for o in buy_orders]}"
        )
        chosen = alpha_orders[0]
        data["uuid"] = chosen["uuid"]
        if with_blockchain:
            data["voters"] = voter_addresses[:3]
        else:
            data["approved"] = True
        alpha_uuid.clear()
        alpha_uuid.append(chosen["uuid"])
        return (url, None, False)

    # ------------------------------------------------------------------
    # Setup: get AssetAlpha id from search and prepare sell order
    # ------------------------------------------------------------------
    def set_up_alpha_sell_order(url, headers, data, files):
        from utilities import employee_login
        emp_headers = {}
        if with_authentication:
            employee_login(authentication_url, emp_headers)
        from requests import request as _request
        response = _request(
            method  = "post",
            url     = employee_url + "/search",
            headers = emp_headers,
            json    = {"name": "AssetAlpha"},
        )
        assets = response.json().get("assets", [])
        alpha = next((a for a in assets if a.get("name") == "AssetAlpha"), None)
        assert alpha is not None, (
            f"Expected AssetAlpha in /search results after approval, got: "
            f"{[a.get('name') for a in assets]}"
        )
        alpha_asset_id.clear()
        alpha_asset_id.append(alpha["id"])
        data["id"]            = alpha["id"]
        data["selling_price"] = 75000
        if with_authentication:
            employee_login(authentication_url, headers)
        return (url, None, False)

    # ------------------------------------------------------------------
    # Setup: sell order missing selling_price validation
    # ------------------------------------------------------------------
    def set_up_alpha_sell_missing_price(url, headers, data, files):
        from utilities import employee_login
        emp_headers = {}
        if with_authentication:
            employee_login(authentication_url, emp_headers)
        from requests import request as _request
        response = _request(
            method  = "post",
            url     = employee_url + "/search",
            headers = emp_headers,
            json    = {"name": "AssetAlpha"},
        )
        assets = response.json().get("assets", [])
        alpha = next((a for a in assets if a.get("name") == "AssetAlpha"), None)
        assert alpha is not None, (
            f"Expected AssetAlpha in /search results, got: {[a.get('name') for a in assets]}"
        )
        data["id"] = alpha["id"]
        # deliberately no selling_price
        if with_authentication:
            employee_login(authentication_url, headers)
        return (url, None, False)

    # ------------------------------------------------------------------
    # Setup: sell order invalid selling_price
    # ------------------------------------------------------------------
    def set_up_alpha_sell_invalid_price(url, headers, data, files):
        from utilities import employee_login
        emp_headers = {}
        if with_authentication:
            employee_login(authentication_url, emp_headers)
        from requests import request as _request
        response = _request(
            method  = "post",
            url     = employee_url + "/search",
            headers = emp_headers,
            json    = {"name": "AssetAlpha"},
        )
        assets = response.json().get("assets", [])
        alpha = next((a for a in assets if a.get("name") == "AssetAlpha"), None)
        assert alpha is not None, (
            f"Expected AssetAlpha in /search results, got: {[a.get('name') for a in assets]}"
        )
        data["id"]            = alpha["id"]
        data["selling_price"] = 0
        if with_authentication:
            employee_login(authentication_url, headers)
        return (url, None, False)

    # ------------------------------------------------------------------
    # Setup: get pending SELL UUID for AssetAlpha, approve it
    # ------------------------------------------------------------------
    def set_up_alpha_sell_decision(url, headers, data, files):
        from utilities import director_login, get_pending_orders
        if with_authentication:
            director_login(authentication_url, headers)
        orders = get_pending_orders(with_authentication, authentication_url, director_url)
        sell_orders = [o for o in orders if o.get("order_type") == "SELL"]
        assert sell_orders, (
            f"Expected a pending SELL order for AssetAlpha, got orders: "
            f"{[(o.get('order_type'), o.get('name')) for o in orders]}"
        )
        chosen = sell_orders[0]
        data["uuid"] = chosen["uuid"]
        if with_blockchain:
            data["voters"] = voter_addresses[:3]
        else:
            data["approved"] = True
        alpha_sell_uuid.clear()
        alpha_sell_uuid.append(chosen["uuid"])
        return (url, None, False)

    # ------------------------------------------------------------------
    # Setup: wait for AssetAlpha to have selling_price in search
    # ------------------------------------------------------------------
    def set_up_wait_alpha_sold(url, headers, data, files):
        from utilities import employee_login
        emp_headers = {}
        if with_authentication:
            employee_login(authentication_url, emp_headers)
        from requests import request as _request
        deadline = time.monotonic() + 30
        last_assets = []
        while time.monotonic() < deadline:
            response = _request(
                method  = "post",
                url     = employee_url + "/search",
                headers = emp_headers,
                json    = {"name": "AssetAlpha"},
            )
            try:
                assets = response.json().get("assets", [])
                last_assets = assets
                alpha = next((a for a in assets if a.get("name") == "AssetAlpha"), None)
                if alpha and "selling_price" in alpha:
                    if with_authentication:
                        employee_login(authentication_url, headers)
                    return (url, None, False)
            except Exception:
                pass
            time.sleep(1)
        assert False, (
            f"AssetAlpha did not show a selling_price in /search within 30s "
            f"after sell approval. Last seen: {last_assets}"
        )

    # ------------------------------------------------------------------
    # Decision step response: blockchain mode returns a contract deploy
    # response and needs real votes signed/sent; no-blockchain mode applies
    # the decision immediately and returns an empty body.
    # ------------------------------------------------------------------
    if with_blockchain:
        decision_expected_response  = {}
        buy_decision_cleanup        = vote_and_wait(with_blockchain, voter_private_keys, provider_url, True, 2, tx_store)
        sell_decision_cleanup       = vote_and_wait(with_blockchain, voter_private_keys, provider_url, True, 2, tx_store)
    else:
        decision_expected_response  = None
        buy_decision_cleanup        = equals
        sell_decision_cleanup       = equals

    tests = [
        # ------------------------------------------------------------------
        # Step 1: Director approves AssetAlpha BUY order
        # ------------------------------------------------------------------
        ["post", director_url + "/decision",
         set_up_alpha_buy_decision,
         {}, {}, {},
         200, decision_expected_response,
         buy_decision_cleanup,
         5],

        # ------------------------------------------------------------------
        # Step 2: Search for AssetAlpha after approval (polls until found)
        # ------------------------------------------------------------------
        ["post", employee_url + "/search",
         set_up_wait_for_asset(with_authentication, authentication_url, employee_url, "AssetAlpha", timeout=30),
         {}, {}, {},
         200, {},
         evaluate_assets_test([get_asset_alpha()]),
         5],

        # ------------------------------------------------------------------
        # Step 3: Create sell order for AssetAlpha (weight 2)
        # ------------------------------------------------------------------
        ["post", employee_url + "/create_sell_order",
         set_up_alpha_sell_order,
         {}, {}, {},
         200, None, equals, 2],

        # ------------------------------------------------------------------
        # Step 4: Sell order validation - missing selling_price (weight 1)
        # ------------------------------------------------------------------
        ["post", employee_url + "/create_sell_order",
         set_up_alpha_sell_missing_price,
         {}, {}, {},
         400, {"message": "Field selling_price is missing."}, equals, 1],

        # ------------------------------------------------------------------
        # Step 5: Sell order validation - invalid selling_price = 0 (weight 1)
        # ------------------------------------------------------------------
        ["post", employee_url + "/create_sell_order",
         set_up_alpha_sell_invalid_price,
         {}, {}, {},
         400, {"message": "Invalid selling price."}, equals, 1],

        # ------------------------------------------------------------------
        # Step 6: Director approves AssetAlpha SELL order
        # ------------------------------------------------------------------
        ["post", director_url + "/decision",
         set_up_alpha_sell_decision,
         {}, {}, {},
         200, decision_expected_response,
         sell_decision_cleanup,
         5],

        # ------------------------------------------------------------------
        # Step 7: Search after sell approval - AssetAlpha has selling_price
        # ------------------------------------------------------------------
        ["post", employee_url + "/search",
         set_up_wait_alpha_sold,
         {}, {}, {},
         200, {},
         evaluate_assets_test([get_asset_alpha_sold()]),
         5],

        # ------------------------------------------------------------------
        # Step 8: Report check (weight 5)
        # ------------------------------------------------------------------
        ["get", director_url + "/report",
         set_up_director_headers(with_authentication, authentication_url),
         {}, {}, {},
         200, get_report_alpha_sold(with_blockchain),
         evaluate_report_test,
         5],
    ]

    percentage = run_tests(tests)
    return percentage
