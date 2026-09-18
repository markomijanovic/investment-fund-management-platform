import datetime
import re
import time
import uuid as uuid_module

from requests import request
from copy     import deepcopy
from data     import get_employee
from data     import get_is_employee_registered
from data     import set_is_employee_registered
from data     import ANY_OBJECT_ID
from data     import ANY_UUID
from data     import ANY_DATE

try:
    from web3 import Account
    from web3 import Web3
    from web3 import HTTPProvider
except ModuleNotFoundError:
    Account = Web3 = HTTPProvider = None


def recursive_compare(expected, received, level='root', preprocess_list=None, preprocess_scalar=None):
    message = ""
    same    = True

    if isinstance(expected, dict) and isinstance(received, dict):
        if sorted(expected.keys()) != sorted(received.keys()):
            expected_key_set = set(expected.keys())
            received_key_set = set(received.keys())

            message += "{:<20} +{} -{}\n".format(level, expected_key_set - received_key_set, received_key_set - expected_key_set)
            same     = False

            common_keys = expected_key_set & received_key_set
        else:
            common_keys = set(expected.keys())

        for key in common_keys:
            result = recursive_compare(
                expected[key],
                received[key],
                "{}.{}".format(level, key),
                preprocess_list,
                preprocess_scalar,
            )
            message += result[0]
            same    &= result[1]

    elif isinstance(expected, list) and isinstance(received, list):
        if len(expected) != len(received):
            message += "{:<20} expected_length={} received_length={}\n".format(level, len(expected), len(received))
            same     = False
        else:
            if preprocess_list:
                (expected, received) = preprocess_list(expected, received, level)

            for i in range(len(expected)):
                result = recursive_compare(
                    expected[i],
                    received[i],
                    '{}[{}]'.format(level, i),
                    preprocess_list,
                    preprocess_scalar,
                )
                message += result[0]
                same    &= result[1]
    else:
        if preprocess_scalar:
            (expected, received) = preprocess_scalar(expected, received, level)

        if expected != received:
            message += "{:<20} {} != {}\n".format(level, expected, received)
            same = False

    return (message, same)


def copy_dictionary(destination, source):
    for key in source:
        destination[key] = deepcopy(source[key])


def are_equal(list0, list1):
    difference = [item for item in (list0 + list1) if (item not in list0) or (item not in list1)]
    return len(difference) == 0


# ---------------------------------------------------------------------------
# Field-level content evaluation
#
# Server-generated fields (Mongo ObjectIds, Redis UUIDs, timestamps) can't be
# pinned to an exact expected value, so fixtures mark them with the ANY_*
# sentinels from data.py; every other field must match exactly.
# ---------------------------------------------------------------------------

_OBJECT_ID_RE = re.compile(r'^[0-9a-fA-F]{24}$')


def _is_valid_object_id(value):
    return isinstance(value, str) and bool(_OBJECT_ID_RE.match(value))


def _is_valid_uuid(value):
    if not isinstance(value, str):
        return False
    try:
        uuid_module.UUID(value)
        return True
    except ValueError:
        return False


def _is_valid_iso_datetime(value):
    if not isinstance(value, str):
        return False
    try:
        datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


_SENTINEL_VALIDATORS = {
    ANY_OBJECT_ID: _is_valid_object_id,
    ANY_UUID:      _is_valid_uuid,
    ANY_DATE:      _is_valid_iso_datetime,
}


def evaluate_fields(expected, actual, label=""):
    """Asserts that `actual` has exactly the same fields as `expected`, and
    that every field's value matches exactly -- except fields whose expected
    value is one of the ANY_* sentinels, which are instead checked for
    presence and correct format (real ObjectId / UUID / ISO 8601 date)."""
    prefix = f"{label}: " if label else ""

    expected_keys = set(expected.keys())
    actual_keys   = set(actual.keys()) if isinstance(actual, dict) else None
    assert isinstance(actual, dict), f"{prefix}expected an object, got {actual!r}"
    assert expected_keys == actual_keys, (
        f"{prefix}field set mismatch.\n"
        f"  expected fields: {sorted(expected_keys)}\n"
        f"  actual fields:   {sorted(actual_keys)}"
    )

    for field, expected_value in expected.items():
        actual_value = actual[field]
        validator = _SENTINEL_VALIDATORS.get(expected_value) if isinstance(expected_value, str) else None
        if validator is not None:
            assert validator(actual_value), (
                f"{prefix}field '{field}' is not a valid value: {actual_value!r}"
            )
        else:
            assert actual_value == expected_value, (
                f"{prefix}field '{field}' mismatch: expected {expected_value!r}, got {actual_value!r}."
            )


def set_up_pass_function(url, headers, data, files):
    return (url, None, False)


def set_up_authorization_error_request(with_authentication):
    def implementation(url, headers, data, files):
        if not with_authentication:
            return (url, None, True)
        return (url, None, False)
    return implementation


def skip_unless_with_authentication(with_authentication, setup_fn):
    """Wraps a setup fn so the whole test is skipped when authentication is
    out of scope (--with-authentication not passed). Use this for rows that
    check role-based rejection (wrong token's role) -- with authentication
    optional, there's no auth/role concept to reject against, so the
    endpoint is expected to just process the request."""
    def implementation(url, headers, data, files):
        if not with_authentication:
            return (url, None, True)
        return setup_fn(url, headers, data, files)
    return implementation


# ---------------------------------------------------------------------------
# Director helpers
# ---------------------------------------------------------------------------

def director_login(authentication_url, headers):
    response = request(
        method  = "post",
        url     = authentication_url + "/login",
        headers = {},
        json    = {
            "email":    "onlymoney@gmail.com",
            "password": "evenmoremoney",
        },
    )
    headers["Authorization"] = "Bearer " + response.json()["accessToken"]


def set_up_director_headers(with_authentication, authentication_url):
    def implementation(url, headers, data, files):
        if with_authentication:
            director_login(authentication_url, headers)
        return (url, None, False)
    return implementation


# ---------------------------------------------------------------------------
# Employee helpers
# ---------------------------------------------------------------------------

def employee_login(authentication_url, headers):
    if not get_is_employee_registered():
        request(
            method  = "post",
            url     = authentication_url + "/register",
            headers = {},
            json    = get_employee(),
        )
        set_is_employee_registered(True)

    response = request(
        method  = "post",
        url     = authentication_url + "/login",
        headers = {},
        json    = {
            "email":    get_employee()["email"],
            "password": get_employee()["password"],
        },
    )
    headers["Authorization"] = "Bearer " + response.json()["accessToken"]


def set_up_employee_headers(with_authentication, authentication_url):
    def implementation(url, headers, data, files):
        if with_authentication:
            employee_login(authentication_url, headers)
        return (url, "", False)
    return implementation


# ---------------------------------------------------------------------------
# Delete helpers
# ---------------------------------------------------------------------------

def set_up_delete_test(with_authentication, authentication_url, tokens):
    def implementation(url, headers, data, files):
        if with_authentication:
            employee_login(authentication_url, headers)
            tokens.append(headers["Authorization"])
        return (url, "", False)
    return implementation


def set_up_delete_error_test(with_authentication, tokens, index):
    def implementation(url, headers, data, files):
        if with_authentication:
            headers["Authorization"] = tokens[index]
        return (url, "", False)
    return implementation


# ---------------------------------------------------------------------------
# Generic comparison helpers
# ---------------------------------------------------------------------------

def equals(set_up_data, expected_response, received_response):
    assert expected_response == received_response, (
        f"Invalid response, expected {expected_response}, received {received_response}."
    )


def find_first(lst, predicate):
    for item in lst:
        if predicate(item):
            return item
    return None


# ---------------------------------------------------------------------------
# Pending orders helpers
# ---------------------------------------------------------------------------

def get_pending_orders(with_authentication, authentication_url, director_url):
    """Returns the list of pending orders from /pending_orders."""
    headers = {}
    if with_authentication:
        director_login(authentication_url, headers)
    response = request(
        method  = "get",
        url     = director_url + "/pending_orders",
        headers = headers,
        json    = {},
    )
    return response.json().get("orders", [])


def set_up_immediate_decision(with_authentication, authentication_url, director_url, approved,
                               order_type_filter=None, name_filter=None, uuid_store=None):
    """Setup fn for the no-blockchain /decision endpoint: finds a matching pending
    order and fills data['uuid'] + data['approved']. The director processes the
    decision synchronously, so no polling/voting is needed afterward."""
    def implementation(url, headers, data, files):
        if with_authentication:
            director_login(authentication_url, headers)

        orders = get_pending_orders(with_authentication, authentication_url, director_url)
        if order_type_filter:
            orders = [o for o in orders if o.get("order_type") == order_type_filter]
        if name_filter:
            orders = [o for o in orders if o.get("name") == name_filter]

        assert orders, (
            f"No pending order found matching order_type={order_type_filter!r} "
            f"name={name_filter!r}."
        )

        chosen = orders[0]
        data["uuid"] = chosen["uuid"]
        data["approved"] = approved
        if uuid_store is not None:
            uuid_store.clear()
            uuid_store.append(chosen["uuid"])

        return (url, None, False)
    return implementation


def evaluate_pending_orders_content(expected_buy_orders):
    """Returns a test fn verifying that /pending_orders contains exactly the
    given BUY orders (by name), with every field validated -- not just that
    *some* orders with the right shape exist."""
    def implementation(set_up_data, expected_response, received_response):
        orders = received_response.get("orders", [])

        expected_names = sorted(o["name"] for o in expected_buy_orders)
        actual_names   = sorted(o.get("name") for o in orders if o.get("order_type") == "BUY")
        assert actual_names == expected_names, (
            f"Pending BUY order names mismatch.\n"
            f"  expected: {expected_names}\n"
            f"  actual:   {actual_names}"
        )

        by_name = {o.get("name"): o for o in orders if o.get("order_type") == "BUY"}
        for expected_order in expected_buy_orders:
            name = expected_order["name"]
            full_expected = {"uuid": ANY_UUID, "order_type": "BUY", **expected_order}
            evaluate_fields(full_expected, by_name[name], label=f"pending order '{name}'")
    return implementation


def evaluate_assets_test(expected_assets):
    """Returns a test fn that checks each full expected asset (from data.py,
    e.g. get_asset_alpha()) is present in the response with every field
    matching exactly (id/buying_date/selling_date via ANY_* sentinels). Other,
    unrelated assets may also be present in the response -- this only
    verifies the named ones, since /search isn't always filtered to a single
    asset in every call site."""
    def implementation(set_up_data, expected_response, received_response):
        assets = received_response.get("assets", [])
        by_name = {a.get("name"): a for a in assets}
        for expected_asset in expected_assets:
            name = expected_asset["name"]
            assert name in by_name, (
                f"Expected asset '{name}' not found in response. Got: {sorted(by_name)}"
            )
            evaluate_fields(expected_asset, by_name[name], label=f"asset '{name}'")
    return implementation


_ETH_ADDRESS_RE = re.compile(r'^0x[0-9a-fA-F]{40}$')


def _is_valid_call_data(value):
    if not isinstance(value, str) or not value.startswith("0x"):
        return False
    try:
        bytes.fromhex(value[2:])
        return True
    except ValueError:
        return False


def _find_contract_creation_tx(web3, contract_address):
    """Scans the chain (newest block first) for a contract-creation
    transaction (to=None) whose receipt's contractAddress matches
    contract_address. Returns the transaction hash if found, else None.

    This confirms a real CREATE happened on-chain, regardless of what the
    deployed contract's ABI/functions/argument encoding look like -- students
    can implement the voting contract however they want."""
    target = Web3.to_checksum_address(contract_address)
    latest = web3.eth.block_number
    for block_num in range(latest, -1, -1):
        block = web3.eth.get_block(block_num, full_transactions=True)
        for tx in block.transactions:
            if tx["to"] is None:
                receipt = web3.eth.get_transaction_receipt(tx["hash"])
                if receipt.contractAddress and Web3.to_checksum_address(receipt.contractAddress) == target:
                    return tx["hash"]
    return None


def evaluate_decision_response(provider_url=None):
    """Returns a test fn checking that approve_transaction/reject_transaction
    are well-formed, unsigned Ethereum transactions targeting the same
    address with two distinct payloads -- without assuming anything about
    the contract's ABI, function names, or argument encoding, since the
    project spec doesn't dictate the contract's internal design.

    When provider_url is given, also inspects the blockchain directly for a
    contract-creation transaction whose receipt deployed a contract at that
    exact address, confirming /decision actually performed a real on-chain
    deployment rather than just returning a plausible-looking address."""
    def implementation(set_up_data, expected_response, received_response):
        assert "approve_transaction" in received_response, (
            "Response missing 'approve_transaction' field."
        )
        assert "reject_transaction" in received_response, (
            "Response missing 'reject_transaction' field."
        )

        approve_tx = received_response["approve_transaction"]
        reject_tx  = received_response["reject_transaction"]

        for tx_key, tx in (("approve_transaction", approve_tx), ("reject_transaction", reject_tx)):
            assert isinstance(tx, dict), f"'{tx_key}' should be a JSON object, got {tx!r}."
            assert "to" in tx, f"'{tx_key}' missing 'to' field."
            assert _ETH_ADDRESS_RE.match(str(tx["to"])), (
                f"'{tx_key}.to' is not a valid Ethereum address: {tx['to']!r}"
            )
            if tx.get("data") not in (None, "", "0x"):
                assert _is_valid_call_data(tx["data"]), (
                    f"'{tx_key}.data' does not look like valid call data: {tx['data']!r}"
                )

        assert approve_tx["to"] == reject_tx["to"], (
            "approve_transaction and reject_transaction should target the same deployed "
            f"contract, got {approve_tx['to']!r} vs {reject_tx['to']!r}."
        )
        assert approve_tx != reject_tx, (
            "approve_transaction and reject_transaction must encode different actions, "
            "but the two transaction objects are identical."
        )

        if provider_url is not None:
            web3 = Web3(HTTPProvider(provider_url))
            creation_tx = _find_contract_creation_tx(web3, approve_tx["to"])
            assert creation_tx is not None, (
                f"No contract-creation transaction found on the configured blockchain "
                f"provider that deployed a contract at {approve_tx['to']!r} -- /decision "
                "did not actually deploy a contract there."
            )

    return implementation


def vote_and_wait(with_blockchain, voter_private_keys, provider_url, vote_approve, num_votes, tx_store):
    """Returns test_and_cleanup_function that signs+sends vote transactions."""
    def implementation(set_up_data, expected_response, received_response):
        if not with_blockchain:
            return

        evaluate_decision_response(provider_url)(set_up_data, expected_response, received_response)

        tx_key = "approve_transaction" if vote_approve else "reject_transaction"
        tx_data = received_response[tx_key]

        if tx_store is not None:
            tx_store.clear()
            tx_store.append(tx_data)

        web3 = Web3(HTTPProvider(provider_url))

        for i in range(num_votes):
            pk = voter_private_keys[i]
            account = Account.from_key(pk)
            nonce = web3.eth.get_transaction_count(account.address)

            transaction = {
                "to":       tx_data["to"],
                "data":     tx_data["data"],
                "gas":      300000,
                "gasPrice": web3.to_wei("1", "gwei"),
                "nonce":    nonce,
                "chainId":  web3.eth.chain_id,
            }
            signed = web3.eth.account.sign_transaction(transaction, pk)
            tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
            web3.eth.wait_for_transaction_receipt(tx_hash)

    return implementation


def set_up_wait_for_asset(with_authentication, authentication_url, employee_url, asset_name, timeout=20):
    """Setup fn: polls /search until asset_name appears. If it never shows up
    within timeout, that's a real failure (the decision/vote above should
    have created it), not a skip."""
    def implementation(url, headers, data, files):
        emp_headers = {}
        if with_authentication:
            employee_login(authentication_url, emp_headers)

        deadline = time.monotonic() + timeout
        last_names = []
        while time.monotonic() < deadline:
            response = request(
                method  = "post",
                url     = employee_url + "/search",
                headers = emp_headers,
                json    = {},
            )
            try:
                assets = response.json().get("assets", [])
                last_names = [a.get("name") for a in assets]
                if asset_name in last_names:
                    if with_authentication:
                        employee_login(authentication_url, headers)
                    return (url, None, False)
            except Exception:
                pass
            time.sleep(1)

        assert False, (
            f"Asset '{asset_name}' did not appear in /search within {timeout}s. "
            f"Last seen assets: {last_names}"
        )
    return implementation


def evaluate_report_test(set_up_data, expected_response, received_response):
    """Checks report content matches expected_response exactly, not just shape."""
    assert "statistics" in received_response, "Response missing 'statistics' field."
    statistics = received_response["statistics"]
    assert isinstance(statistics, list), "'statistics' must be a list."
    for item in statistics:
        assert "category" in item, f"Statistics item missing 'category': {item}"
        assert "spent"    in item, f"Statistics item missing 'spent': {item}"
        assert "earned"   in item, f"Statistics item missing 'earned': {item}"

    expected_statistics = expected_response.get("statistics", [])
    assert statistics == expected_statistics, (
        f"Report content mismatch.\n  expected: {expected_statistics}\n  received: {statistics}"
    )


# ---------------------------------------------------------------------------
# run_tests  (unchanged interface)
# ---------------------------------------------------------------------------

def run_tests(tests):
    max_   = 0
    total  = 0

    for index, test in enumerate(tests):
        method                    = test[0]
        url                       = test[1]
        preparation_function      = test[2]
        headers                   = test[3]
        data                      = test[4]
        files                     = test[5]
        expected_status_code      = test[6]
        expected_response         = test[7]
        test_and_cleanup_function = test[8]
        score                     = test[9]

        try:
            (url, set_up_data, skip_test) = preparation_function(url, headers, data, files)

            if not skip_test:
                max_  += score
                total += score

                response = request(
                    method  = method,
                    url     = url,
                    headers = headers,
                    json    = data,
                    files   = files,
                )

                for key in files:
                    files[key].close()

                assert response.status_code == expected_status_code, (
                    f"Invalid status code, expected {expected_status_code}, received {response.status_code}"
                )

                if expected_response is not None:
                    received_response = response.json()
                else:
                    expected_response = {}
                    received_response = {}

                test_and_cleanup_function(set_up_data, expected_response, received_response)
            else:
                print(f"SKIPPED {index}")

        except Exception as error:
            response_data = "DUMMY"
            try:
                response_data = response.json()
            except Exception:
                pass

            print(
                f"Failed test number {index}\n"
                f"\t method = {method}\n"
                f"\t url = {url}\n"
                f"\t headers = {headers}\n"
                f"\t data = {data}\n"
                f"\t files = {files}\n"
                f"\t response = {response_data}\n"
                f"\t error: {error}"
            )
            total -= score

    return total / max_ if max_ != 0 else 0
