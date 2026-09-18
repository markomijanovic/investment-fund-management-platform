import time

from utilities import equals
from utilities import run_tests
from utilities import evaluate_assets_test
from utilities import evaluate_report_test
from utilities import evaluate_fields
from utilities import vote_and_wait
from data      import get_buy_order3
from data      import get_buy_order4
from data      import get_asset_alpha_sold
from data      import get_asset_delta
from data      import get_asset_epsilon
from data      import get_report_full
from data      import get_report_full_with_epsilon


def run_level3_tests(with_authentication, authentication_url, employee_url, director_url, with_blockchain, voter_private_keys, provider_url):
    tx_store = []

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
    # Helpers
    # ------------------------------------------------------------------

    def get_buy_order_uuid_by_name(asset_name):
        """Returns UUID of the BUY order for the given asset name from
        /pending_orders. The order must actually be pending -- there is no
        fallback to "some other order", since that would silently approve
        the wrong asset."""
        from utilities import get_pending_orders
        orders = get_pending_orders(with_authentication, authentication_url, director_url)
        buy_orders = [o for o in orders if o.get("order_type") == "BUY"]
        matched    = [o for o in buy_orders if o.get("name") == asset_name]
        assert matched, (
            f"Expected a pending BUY order for '{asset_name}', got buy orders: "
            f"{[o.get('name') for o in buy_orders]}"
        )
        return matched[0]["uuid"]

    # ------------------------------------------------------------------
    # Step 1: Create buy order for AssetGamma (rejection test)
    # ------------------------------------------------------------------
    def set_up_buy_gamma(url, headers, data, files):
        from utilities import employee_login
        if with_authentication:
            employee_login(authentication_url, headers)
        return (url, None, False)

    # ------------------------------------------------------------------
    # Step 2: Director decision for AssetGamma - REJECT
    # ------------------------------------------------------------------
    def set_up_gamma_decision(url, headers, data, files):
        from utilities import director_login
        if with_authentication:
            director_login(authentication_url, headers)
        data["uuid"] = get_buy_order_uuid_by_name("AssetGamma")
        if with_blockchain:
            data["voters"] = voter_addresses[:3]
        else:
            data["approved"] = False
        return (url, None, False)

    # ------------------------------------------------------------------
    # Step 3: After rejection, AssetGamma not in search results
    # ------------------------------------------------------------------
    def set_up_wait_then_search_gamma(url, headers, data, files):
        from utilities import employee_login
        if with_authentication:
            employee_login(authentication_url, headers)
        if with_blockchain:
            # give the background event listener time to process the vote
            time.sleep(10)
        return (url, None, False)

    def evaluate_gamma_rejected(set_up_data, expected_response, received_response):
        assets = received_response.get("assets", [])
        names  = [a.get("name") for a in assets]
        assert "AssetGamma" not in names, (
            f"AssetGamma should NOT be in assets after rejection, but got: {names}"
        )

    # ------------------------------------------------------------------
    # Step 4: Create buy order for AssetDelta
    # ------------------------------------------------------------------
    asset_delta = {
        "name":         "AssetDelta",
        "categories":   ["Finance", "Real Estate"],
        "buying_price": 200000,
        "info":         {"sector": "commercial", "floors": 10},
    }

    def set_up_buy_delta(url, headers, data, files):
        from utilities import employee_login
        if with_authentication:
            employee_login(authentication_url, headers)
        return (url, None, False)

    # ------------------------------------------------------------------
    # Step 5: Director decision for AssetDelta - APPROVE
    # ------------------------------------------------------------------
    def set_up_delta_decision(url, headers, data, files):
        from utilities import director_login
        if with_authentication:
            director_login(authentication_url, headers)
        data["uuid"] = get_buy_order_uuid_by_name("AssetDelta")
        if with_blockchain:
            data["voters"] = voter_addresses[:3]
        else:
            data["approved"] = True
        return (url, None, False)

    # ------------------------------------------------------------------
    # Step 6: Search with name filter - wait for AssetDelta first
    # ------------------------------------------------------------------
    def set_up_wait_for_delta(url, headers, data, files):
        from utilities import employee_login
        emp_headers = {}
        if with_authentication:
            employee_login(authentication_url, emp_headers)
        from requests import request as _request
        deadline = time.monotonic() + 30
        last_names = []
        while time.monotonic() < deadline:
            response = _request(
                method  = "post",
                url     = employee_url + "/search",
                headers = emp_headers,
                json    = {},
            )
            try:
                assets = response.json().get("assets", [])
                last_names = [a.get("name") for a in assets]
                if "AssetDelta" in last_names:
                    if with_authentication:
                        employee_login(authentication_url, headers)
                    return (url, None, False)
            except Exception:
                pass
            time.sleep(1)
        assert False, f"AssetDelta did not appear in /search within 30s. Last seen: {last_names}"

    # ------------------------------------------------------------------
    # Step 7: Search with category filter
    # ------------------------------------------------------------------
    def set_up_category_search(url, headers, data, files):
        from utilities import employee_login
        if with_authentication:
            employee_login(authentication_url, headers)
        data["category"] = "Real Estate"
        return (url, None, False)

    def evaluate_category_search(set_up_data, expected_response, received_response):
        assets = received_response.get("assets", [])
        by_name = {a.get("name"): a for a in assets}
        assert "AssetDelta" in by_name, (
            f"AssetDelta should appear in 'Real Estate' search, got: {sorted(by_name)}"
        )
        evaluate_fields(get_asset_delta(), by_name["AssetDelta"], label="asset 'AssetDelta'")
        assert "AssetAlpha" not in by_name, (
            f"AssetAlpha should NOT appear in 'Real Estate' search, got: {sorted(by_name)}"
        )

    # ------------------------------------------------------------------
    # Step 8: Search with buying_date filter
    # ------------------------------------------------------------------
    def set_up_buying_date_search(url, headers, data, files):
        from utilities import employee_login
        if with_authentication:
            employee_login(authentication_url, headers)
        data["buying_date"] = "2020-01-01T00:00:00.000Z"
        return (url, None, False)

    # ------------------------------------------------------------------
    # Step 9: Search with selling_date filter
    # ------------------------------------------------------------------
    def set_up_selling_date_search(url, headers, data, files):
        from utilities import employee_login
        if with_authentication:
            employee_login(authentication_url, headers)
        data["selling_date"] = "2099-01-01T00:00:00.000Z"
        return (url, None, False)

    # ------------------------------------------------------------------
    # Step 10: Search with info_filters
    # ------------------------------------------------------------------
    def set_up_info_filters_search(url, headers, data, files):
        from utilities import employee_login
        if with_authentication:
            employee_login(authentication_url, headers)
        data["info_filters"] = [{"field": "sector", "operator": "eq", "value": "commercial"}]
        return (url, None, False)

    # ------------------------------------------------------------------
    # Step 11: Report with multiple categories
    # ------------------------------------------------------------------
    def set_up_report(url, headers, data, files):
        from utilities import director_login
        if with_authentication:
            director_login(authentication_url, headers)
        return (url, None, False)

    # ------------------------------------------------------------------
    # Step 12: Create buy order for AssetEpsilon (nested info object)
    # ------------------------------------------------------------------
    def set_up_buy_epsilon(url, headers, data, files):
        from utilities import employee_login
        if with_authentication:
            employee_login(authentication_url, headers)
        return (url, None, False)

    # ------------------------------------------------------------------
    # Step 13: Director approves AssetEpsilon
    # ------------------------------------------------------------------
    def set_up_epsilon_decision(url, headers, data, files):
        from utilities import director_login
        if with_authentication:
            director_login(authentication_url, headers)
        data["uuid"] = get_buy_order_uuid_by_name("AssetEpsilon")
        if with_blockchain:
            data["voters"] = voter_addresses[:3]
        else:
            data["approved"] = True
        return (url, None, False)

    # ------------------------------------------------------------------
    # Step 14: Wait for AssetEpsilon in search
    # ------------------------------------------------------------------
    def set_up_wait_for_epsilon(url, headers, data, files):
        from utilities import employee_login
        emp_headers = {}
        if with_authentication:
            employee_login(authentication_url, emp_headers)
        from requests import request as _request
        deadline = time.monotonic() + 30
        last_names = []
        while time.monotonic() < deadline:
            response = _request(
                method  = "post",
                url     = employee_url + "/search",
                headers = emp_headers,
                json    = {},
            )
            try:
                assets = response.json().get("assets", [])
                last_names = [a.get("name") for a in assets]
                if "AssetEpsilon" in last_names:
                    if with_authentication:
                        employee_login(authentication_url, headers)
                    return (url, None, False)
            except Exception:
                pass
            time.sleep(1)
        assert False, f"AssetEpsilon did not appear in /search within 30s. Last seen: {last_names}"

    # ------------------------------------------------------------------
    # Step 15: Search with a nested info_filters field (geo.country)
    # ------------------------------------------------------------------
    def set_up_nested_geo_filter_search(url, headers, data, files):
        from utilities import employee_login
        if with_authentication:
            employee_login(authentication_url, headers)
        data["info_filters"] = [{"field": "geo.country", "operator": "eq", "value": "Germany"}]
        return (url, None, False)

    # ------------------------------------------------------------------
    # Step 16: Search combining two nested info_filters (AND semantics)
    # ------------------------------------------------------------------
    def set_up_nested_specs_filter_search(url, headers, data, files):
        from utilities import employee_login
        if with_authentication:
            employee_login(authentication_url, headers)
        data["info_filters"] = [
            {"field": "specs.power_mw",  "operator": "gt", "value": 10},
            {"field": "specs.renewable", "operator": "eq", "value": True},
        ]
        return (url, None, False)

    # ------------------------------------------------------------------
    # Step 17: Search combining a top-level filter (category) with a nested
    # info_filters field, to confirm the two filter types AND together.
    # ------------------------------------------------------------------
    def set_up_category_and_nested_filter_search(url, headers, data, files):
        from utilities import employee_login
        if with_authentication:
            employee_login(authentication_url, headers)
        data["category"]     = "Energy"
        data["info_filters"] = [{"field": "geo.city", "operator": "eq", "value": "Berlin"}]
        return (url, None, False)

    def evaluate_category_and_nested_filter_search(set_up_data, expected_response, received_response):
        assets = received_response.get("assets", [])
        by_name = {a.get("name"): a for a in assets}
        assert "AssetEpsilon" in by_name, (
            f"AssetEpsilon should appear in 'Energy' + geo.city='Berlin' search, got: {sorted(by_name)}"
        )
        evaluate_fields(get_asset_epsilon(), by_name["AssetEpsilon"], label="asset 'AssetEpsilon'")
        assert "AssetDelta" not in by_name, (
            f"AssetDelta should NOT appear in 'Energy' search, got: {sorted(by_name)}"
        )

    # ------------------------------------------------------------------
    # Decision step response: blockchain mode returns a contract deploy
    # response and needs real votes signed/sent; no-blockchain mode applies
    # the decision immediately and returns an empty body.
    # ------------------------------------------------------------------
    if with_blockchain:
        decision_expected_response = {}
        gamma_decision_cleanup     = vote_and_wait(with_blockchain, voter_private_keys, provider_url, False, 2, tx_store)
        delta_decision_cleanup     = vote_and_wait(with_blockchain, voter_private_keys, provider_url, True, 2, tx_store)
        epsilon_decision_cleanup   = vote_and_wait(with_blockchain, voter_private_keys, provider_url, True, 2, tx_store)
    else:
        decision_expected_response = None
        gamma_decision_cleanup     = equals
        delta_decision_cleanup     = equals
        epsilon_decision_cleanup   = equals

    tests = [
        # ------------------------------------------------------------------
        # Step 1: Create buy order for AssetGamma
        # ------------------------------------------------------------------
        ["post", employee_url + "/create_buy_order",
         set_up_buy_gamma,
         {}, get_buy_order3(), {},
         200, None, equals, 1],

        # ------------------------------------------------------------------
        # Step 2: Director rejects AssetGamma
        # ------------------------------------------------------------------
        ["post", director_url + "/decision",
         set_up_gamma_decision,
         {}, {}, {},
         200, decision_expected_response,
         gamma_decision_cleanup,
         2],

        # ------------------------------------------------------------------
        # Step 3: After rejection, AssetGamma not in search results (weight 3)
        # ------------------------------------------------------------------
        ["post", employee_url + "/search",
         set_up_wait_then_search_gamma,
         {}, {}, {},
         200, {},
         evaluate_gamma_rejected,
         3],

        # ------------------------------------------------------------------
        # Step 4: Create buy order for AssetDelta
        # ------------------------------------------------------------------
        ["post", employee_url + "/create_buy_order",
         set_up_buy_delta,
         {}, asset_delta, {},
         200, None, equals, 1],

        # ------------------------------------------------------------------
        # Step 5: Director approves AssetDelta
        # ------------------------------------------------------------------
        ["post", director_url + "/decision",
         set_up_delta_decision,
         {}, {}, {},
         200, decision_expected_response,
         delta_decision_cleanup,
         2],

        # ------------------------------------------------------------------
        # Step 6: Search with name filter (weight 3) - wait for AssetDelta
        # ------------------------------------------------------------------
        ["post", employee_url + "/search",
         set_up_wait_for_delta,
         {}, {"name": "Delta"}, {},
         200, {},
         evaluate_assets_test([get_asset_delta()]),
         3],

        # ------------------------------------------------------------------
        # Step 7: Search with category filter (weight 3)
        # ------------------------------------------------------------------
        ["post", employee_url + "/search",
         set_up_category_search,
         {}, {}, {},
         200, {},
         evaluate_category_search,
         3],

        # ------------------------------------------------------------------
        # Step 8: Search with buying_date filter (weight 3)
        # Both AssetAlpha (sold) and AssetDelta were bought well after 2020.
        # ------------------------------------------------------------------
        ["post", employee_url + "/search",
         set_up_buying_date_search,
         {}, {}, {},
         200, {},
         evaluate_assets_test([get_asset_alpha_sold(), get_asset_delta()]),
         3],

        # ------------------------------------------------------------------
        # Step 9: Search with selling_date filter (weight 3)
        # AssetAlpha was sold (in level2) well before 2099.
        # ------------------------------------------------------------------
        ["post", employee_url + "/search",
         set_up_selling_date_search,
         {}, {}, {},
         200, {},
         evaluate_assets_test([get_asset_alpha_sold()]),
         3],

        # ------------------------------------------------------------------
        # Step 10: Search with info_filters (weight 3)
        # ------------------------------------------------------------------
        ["post", employee_url + "/search",
         set_up_info_filters_search,
         {}, {}, {},
         200, {},
         evaluate_assets_test([get_asset_delta()]),
         3],

        # ------------------------------------------------------------------
        # Step 11: Report with multiple categories (weight 5)
        # ------------------------------------------------------------------
        ["get", director_url + "/report",
         set_up_report,
         {}, {}, {},
         200, get_report_full(with_blockchain),
         evaluate_report_test,
         5],

        # ------------------------------------------------------------------
        # Step 12: Create buy order for AssetEpsilon (nested info object) (weight 1)
        # ------------------------------------------------------------------
        ["post", employee_url + "/create_buy_order",
         set_up_buy_epsilon,
         {}, get_buy_order4(), {},
         200, None, equals, 1],

        # ------------------------------------------------------------------
        # Step 13: Director approves AssetEpsilon (weight 2)
        # ------------------------------------------------------------------
        ["post", director_url + "/decision",
         set_up_epsilon_decision,
         {}, {}, {},
         200, decision_expected_response,
         epsilon_decision_cleanup,
         2],

        # ------------------------------------------------------------------
        # Step 14: Wait for AssetEpsilon in search, full nested field check (weight 3)
        # ------------------------------------------------------------------
        ["post", employee_url + "/search",
         set_up_wait_for_epsilon,
         {}, {}, {},
         200, {},
         evaluate_assets_test([get_asset_epsilon()]),
         3],

        # ------------------------------------------------------------------
        # Step 15: Search with a nested info_filters field (geo.country) (weight 3)
        # ------------------------------------------------------------------
        ["post", employee_url + "/search",
         set_up_nested_geo_filter_search,
         {}, {}, {},
         200, {},
         evaluate_assets_test([get_asset_epsilon()]),
         3],

        # ------------------------------------------------------------------
        # Step 16: Search combining two nested info_filters - AND semantics (weight 3)
        # ------------------------------------------------------------------
        ["post", employee_url + "/search",
         set_up_nested_specs_filter_search,
         {}, {}, {},
         200, {},
         evaluate_assets_test([get_asset_epsilon()]),
         3],

        # ------------------------------------------------------------------
        # Step 17: Search combining a top-level filter (category) with a
        # nested info_filters field (weight 3)
        # ------------------------------------------------------------------
        ["post", employee_url + "/search",
         set_up_category_and_nested_filter_search,
         {}, {}, {},
         200, {},
         evaluate_category_and_nested_filter_search,
         3],

        # ------------------------------------------------------------------
        # Step 18: Report after AssetEpsilon - new Energy category, and
        # Technology's spent total grows (weight 5)
        # ------------------------------------------------------------------
        ["get", director_url + "/report",
         set_up_report,
         {}, {}, {},
         200, get_report_full_with_epsilon(with_blockchain),
         evaluate_report_test,
         5],
    ]

    percentage = run_tests(tests)
    return percentage
