from utilities import equals
from utilities import run_tests
from utilities import set_up_authorization_error_request
from utilities import skip_unless_with_authentication
from utilities import set_up_director_headers
from utilities import set_up_employee_headers
from utilities import set_up_immediate_decision
from utilities import evaluate_pending_orders_content
from utilities import evaluate_decision_response
from utilities import evaluate_report_test
from utilities import vote_and_wait
from data      import get_buy_order0
from data      import get_buy_order1
from data      import get_buy_order2


# Placeholder Ethereum addresses used when blockchain is not enabled but we need
# odd-count voter lists for /decision success tests.
_PLACEHOLDER_VOTERS = [
    "0x90F8bf6A479f320ead074411a4B0e7944Ea8c9C1",
    "0xFFcf8FDEE72ac11b5c542428B35EEF5769C409f0",
    "0x22d491Bde2303f2f43325b2108D26f1eAbA1e32b",
]


def run_level1_tests(with_authentication, authentication_url, employee_url, director_url, with_blockchain, voter_private_keys, provider_url):
    # voter addresses: use real ones from voter_private_keys when blockchain is on,
    # otherwise use placeholders
    if with_blockchain and voter_private_keys:
        try:
            from web3 import Account
            voter_addresses = [Account.from_key(pk).address for pk in voter_private_keys]
        except Exception:
            voter_addresses = _PLACEHOLDER_VOTERS
    else:
        voter_addresses = _PLACEHOLDER_VOTERS

    def set_up_decision_voters_missing(url, headers, data, files):
        """Fetch a real UUID but send empty voters list."""
        from utilities import director_login, get_pending_orders
        if with_authentication:
            director_login(authentication_url, headers)
        orders = get_pending_orders(with_authentication, authentication_url, director_url)
        assert orders, "Expected at least one pending order from level0, got none."
        data["uuid"]   = orders[0]["uuid"]
        data["voters"] = []
        return (url, None, False)

    def set_up_decision_invalid_voter(url, headers, data, files):
        """Fetch a real UUID, send one invalid voter address."""
        from utilities import director_login, get_pending_orders
        if with_authentication:
            director_login(authentication_url, headers)
        orders = get_pending_orders(with_authentication, authentication_url, director_url)
        assert orders, "Expected at least one pending order from level0, got none."
        data["uuid"]   = orders[0]["uuid"]
        data["voters"] = ["not-an-address"]
        return (url, None, False)

    def set_up_decision_even_voters(url, headers, data, files):
        """Fetch a real UUID, send two (even) voter addresses."""
        from utilities import director_login, get_pending_orders
        if with_authentication:
            director_login(authentication_url, headers)
        orders = get_pending_orders(with_authentication, authentication_url, director_url)
        assert orders, "Expected at least one pending order from level0, got none."
        data["uuid"]   = orders[0]["uuid"]
        data["voters"] = [
            "0x90F8bf6A479f320ead074411a4B0e7944Ea8c9C1",
            "0xFFcf8FDEE72ac11b5c542428B35EEF5769C409f0",
        ]
        return (url, None, False)

    def set_up_decision_success(url, headers, data, files):
        """Fetch the AssetBeta buy-order UUID (deterministic target, so the
        outcome can be verified by name) and add 3 voter addresses."""
        from utilities import director_login, get_pending_orders
        if with_authentication:
            director_login(authentication_url, headers)
        orders = get_pending_orders(with_authentication, authentication_url, director_url)
        buy_orders = [o for o in orders if o.get("order_type") == "BUY"]
        beta_orders = [o for o in buy_orders if o.get("name") == "AssetBeta"]
        assert beta_orders, (
            f"Expected a pending BUY order for 'AssetBeta', got buy orders: "
            f"{[o.get('name') for o in buy_orders]}"
        )
        data["uuid"]   = beta_orders[0]["uuid"]
        data["voters"] = voter_addresses[:3]
        return (url, None, False)

    def set_up_decision_missing_approved(url, headers, data, files):
        """Fetch a real uuid but omit the 'approved' field (no-blockchain mode)."""
        from utilities import director_login, get_pending_orders
        if with_authentication:
            director_login(authentication_url, headers)
        orders = get_pending_orders(with_authentication, authentication_url, director_url)
        assert orders, "Expected at least one pending order from level0, got none."
        data["uuid"] = orders[0]["uuid"]
        return (url, None, False)

    def set_up_decision_invalid_approved(url, headers, data, files):
        """Fetch a real uuid and send a non-boolean 'approved' value (no-blockchain mode)."""
        from utilities import director_login, get_pending_orders
        if with_authentication:
            director_login(authentication_url, headers)
        orders = get_pending_orders(with_authentication, authentication_url, director_url)
        assert orders, "Expected at least one pending order from level0, got none."
        data["uuid"]     = orders[0]["uuid"]
        data["approved"] = "yes"
        return (url, None, False)

    # ------------------------------------------------------------------
    # /decision validation + success tests (tests 9-11/12, weight as below)
    # Branches on whether the director runs with blockchain support.
    # ------------------------------------------------------------------
    if with_blockchain:
        decision_validation_and_success_tests = [
            # missing voters (empty list) - need real uuid
            ["post", director_url + "/decision", set_up_decision_voters_missing, {}, {}, {}, 400, {"message": "Field voters is missing."}, equals, 1],
            # invalid voter address - need real uuid
            ["post", director_url + "/decision", set_up_decision_invalid_voter,  {}, {}, {}, 400, {"message": "Invalid voter address."},   equals, 1],
            # even voters - need real uuid
            ["post", director_url + "/decision", set_up_decision_even_voters,    {}, {}, {}, 400, {"message": "Even number of voters."},   equals, 1],
            # success (weight 5)
            ["post", director_url + "/decision", set_up_decision_success,        {}, {}, {}, 200, {}, evaluate_decision_response(provider_url), 5],
        ]
    else:
        def _evaluate_beta_no_longer_pending(set_up_data, expected_response, received_response):
            """Content check: confirms the AssetBeta order from the previous
            row was actually applied (removed from Redis), not just that the
            decision endpoint returned 200."""
            names = [o.get("name") for o in received_response.get("orders", [])]
            assert "AssetBeta" not in names, (
                f"AssetBeta should have been removed from pending orders after approval, "
                f"but it is still pending. Remaining order names: {names}"
            )

        decision_validation_and_success_tests = [
            # missing approved field - need real uuid
            ["post", director_url + "/decision", set_up_decision_missing_approved, {}, {}, {}, 400, {"message": "Field approved is missing."}, equals, 1],
            # invalid approved type - need real uuid
            ["post", director_url + "/decision", set_up_decision_invalid_approved, {}, {}, {}, 400, {"message": "Invalid decision."},          equals, 1],
            # success: approve the AssetBeta BUY order immediately (deterministic
            # target, so the outcome can be verified by name) (weight 5)
            ["post", director_url + "/decision",
             set_up_immediate_decision(with_authentication, authentication_url, director_url, True,
                                        order_type_filter="BUY", name_filter="AssetBeta"),
             {}, {}, {}, 200, None, equals, 5],
            # content check: AssetBeta must have actually disappeared from pending orders (weight 2)
            ["get", director_url + "/pending_orders", set_up_director_headers(with_authentication, authentication_url),
             {}, {}, {}, 200, {}, _evaluate_beta_no_longer_pending, 2],
        ]

    tests = [
        # ------------------------------------------------------------------
        # /pending_orders auth errors (tests 1-2, weight 1 each)
        # ------------------------------------------------------------------
        ["get", director_url + "/pending_orders", set_up_authorization_error_request(with_authentication),                                                                {}, {}, {}, 401, {"msg": "Missing Authorization Header"}, equals, 1],
        ["get", director_url + "/pending_orders", skip_unless_with_authentication(with_authentication, set_up_employee_headers(with_authentication, authentication_url)), {}, {}, {}, 401, {"msg": "Missing Authorization Header"}, equals, 1],

        # ------------------------------------------------------------------
        # /pending_orders success (test 3, weight 5)
        # Employee created 3 buy orders in level0 (AssetAlpha, AssetBeta,
        # AssetZeta); verify each one's actual content, not just shape.
        # ------------------------------------------------------------------
        ["get", director_url + "/pending_orders", set_up_director_headers(with_authentication, authentication_url), {}, {}, {}, 200, {},
         evaluate_pending_orders_content([get_buy_order0(), get_buy_order1(), get_buy_order2()]), 5],

        # ------------------------------------------------------------------
        # /decision auth errors (tests 4-5, weight 1 each)
        # ------------------------------------------------------------------
        ["post", director_url + "/decision", set_up_authorization_error_request(with_authentication),                                                                {}, {}, {}, 401, {"msg": "Missing Authorization Header"}, equals, 1],
        ["post", director_url + "/decision", skip_unless_with_authentication(with_authentication, set_up_employee_headers(with_authentication, authentication_url)), {}, {}, {}, 401, {"msg": "Missing Authorization Header"}, equals, 1],

        # ------------------------------------------------------------------
        # /decision validation errors (tests 6-8, weight 1 each)
        # These checks happen before the blockchain/non-blockchain branch.
        # ------------------------------------------------------------------
        # missing uuid: empty body
        ["post", director_url + "/decision", set_up_director_headers(with_authentication, authentication_url), {}, {},                                               {}, 400, {"message": "Field uuid is missing."}, equals, 1],
        # invalid uuid format
        ["post", director_url + "/decision", set_up_director_headers(with_authentication, authentication_url), {}, {"uuid": "not-a-uuid"},                           {}, 400, {"message": "Invalid uuid."},          equals, 1],
        # valid uuid format not in Redis
        ["post", director_url + "/decision", set_up_director_headers(with_authentication, authentication_url), {}, {"uuid": "550e8400-e29b-41d4-a716-446655440000"}, {}, 400, {"message": "Invalid uuid."},          equals, 1],

        # ------------------------------------------------------------------
        # /decision validation + success (tests 9-11, blockchain or no-blockchain
        # variant chosen above based on blockchain_enabled)
        # ------------------------------------------------------------------
        *decision_validation_and_success_tests,

        # ------------------------------------------------------------------
        # /report auth errors (tests 13-14, weight 1 each)
        # ------------------------------------------------------------------
        ["get", director_url + "/report", set_up_authorization_error_request(with_authentication),                                                                {}, {}, {}, 401, {"msg": "Missing Authorization Header"}, equals, 1],
        ["get", director_url + "/report", skip_unless_with_authentication(with_authentication, set_up_employee_headers(with_authentication, authentication_url)), {}, {}, {}, 401, {"msg": "Missing Authorization Header"}, equals, 1],

        # ------------------------------------------------------------------
        # /report content (test 15, weight 3)
        # In blockchain mode nothing has actually been finalized yet (the
        # AssetBeta contract above is still awaiting votes), so the report is
        # empty. In no-blockchain mode the AssetBeta decision above is applied
        # synchronously, so it already shows up under its own category.
        # ------------------------------------------------------------------
        ["get", director_url + "/report", set_up_director_headers(with_authentication, authentication_url), {}, {}, {}, 200,
         {"statistics": []} if with_blockchain else
         {"statistics": [{"category": "Real Estate", "spent": 120000, "earned": 0}]},
         evaluate_report_test, 3],
    ]

    percentage = run_tests(tests)
    return percentage
