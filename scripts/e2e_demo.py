"""End-to-end demonstracija: BUY glasanje, Mongo azuriranje i direktorov veto."""

import os
import time
from datetime import datetime, timezone

import requests
from web3 import Web3


AUTH_URL = os.getenv("AUTH_URL", "http://localhost:5000")
EMPLOYEE_URL = os.getenv("EMPLOYEE_URL", "http://localhost:5001")
DIRECTOR_URL = os.getenv("DIRECTOR_URL", "http://localhost:5002")
BLOCKCHAIN_URL = os.getenv("BLOCKCHAIN_URL", "http://localhost:8545")


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def wait_for_blockchain(timeout=35) -> Web3:
    web3 = Web3(Web3.HTTPProvider(BLOCKCHAIN_URL))
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if web3.is_connected():
                return web3
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError("Ganache is unavailable.")


def expect(response, status=200):
    if response.status_code != status:
        raise RuntimeError(f"{response.request.method} {response.url}: {response.status_code} {response.text}")
    return response


def login(email: str, password: str) -> str:
    response = expect(requests.post(
        f"{AUTH_URL}/login",
        json={"email": email, "password": password},
        timeout=10,
    ))
    return response.json()["accessToken"]


def create_buy_order(token: str, name: str):
    expect(requests.post(
        f"{EMPLOYEE_URL}/create_buy_order",
        headers=auth_header(token),
        json={
            "name": name,
            "categories": ["demo", "metal"],
            "buying_price": 1250,
            "info": {"purity": 24, "origin": {"country": "RS"}},
        },
        timeout=10,
    ))


def find_order(director_token: str, name: str) -> str:
    response = expect(requests.get(
        f"{DIRECTOR_URL}/pending_orders",
        headers=auth_header(director_token),
        timeout=10,
    ))
    for order in response.json()["orders"]:
        if order.get("name") == name:
            return order["uuid"]
    raise RuntimeError(f"Order for {name!r} was not found.")


def start_vote(director_token: str, order_uuid: str, voters: list[str]) -> dict:
    response = expect(requests.post(
        f"{DIRECTOR_URL}/decision",
        headers=auth_header(director_token),
        json={"uuid": order_uuid, "voters": voters},
        timeout=30,
    ))
    result = response.json()
    expected = {"approve_transaction", "reject_transaction", "veto_transaction"}
    if set(result) != expected:
        raise RuntimeError(f"Unexpected decision response: {result}")
    return result


def send_transaction(web3: Web3, transaction: dict, sender: str):
    payload = {**transaction, "from": sender}
    transaction_hash = web3.eth.send_transaction(payload)
    receipt = web3.eth.wait_for_transaction_receipt(transaction_hash)
    if receipt.status != 1:
        raise RuntimeError("Blockchain transaction failed.")


def expect_revert(web3: Web3, transaction: dict, sender: str, expected_message: str):
    try:
        web3.eth.send_transaction({**transaction, "from": sender})
    except Exception as error:
        if expected_message not in str(error):
            raise RuntimeError(f"Expected revert {expected_message!r}, got: {error}") from error
        return
    raise RuntimeError(f"Transaction should have reverted with {expected_message!r}.")


def wait_for_asset(employee_token: str, name: str, should_exist: bool, timeout=35):
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = expect(requests.post(
            f"{EMPLOYEE_URL}/search",
            headers=auth_header(employee_token),
            json={"name": name},
            timeout=10,
        ))
        exists = any(asset["name"] == name for asset in response.json()["assets"])
        if exists == should_exist:
            return
        time.sleep(1)
    expectation = "appears" if should_exist else "does not appear"
    raise RuntimeError(f"Timed out waiting until {name!r} {expectation} in MongoDB.")


def wait_for_order_removal(director_token: str, order_uuid: str, timeout=35):
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = expect(requests.get(
            f"{DIRECTOR_URL}/pending_orders",
            headers=auth_header(director_token),
            timeout=10,
        ))
        if all(order["uuid"] != order_uuid for order in response.json()["orders"]):
            return
        time.sleep(1)
    raise RuntimeError(f"Order {order_uuid} was not removed by the checker.")


def main():
    print("1/10 Registrujem demo zaposlenog (idempotentno).")
    registration = {
        "forename": "Demo",
        "surname": "Employee",
        "email": "demo.employee@example.com",
        "password": "demo-password",
    }
    response = requests.post(f"{AUTH_URL}/register", json=registration, timeout=10)
    if response.status_code not in (200, 400) or (
        response.status_code == 400 and response.json().get("message") != "Email already exists."
    ):
        expect(response)

    print("2/10 Prijavljujem zaposlenog i inicijalnog direktora.")
    employee_token = login(registration["email"], registration["password"])
    director_token = login("onlymoney@gmail.com", "evenmoremoney")

    web3 = wait_for_blockchain()
    accounts = web3.eth.accounts
    voters = accounts[1:4]

    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    approved_name = f"Approved demo asset {suffix}"
    vetoed_name = f"Vetoed demo asset {suffix}"

    print("3/10 Kreiram BUY zahtev koji ce biti prihvacen glasanjem.")
    create_buy_order(employee_token, approved_name)
    approved_uuid = find_order(director_token, approved_name)
    transactions = start_vote(director_token, approved_uuid, voters)

    print("4/10 Dva od tri zaposlena glasaju ZA (vecina 2/3).")
    send_transaction(web3, transactions["approve_transaction"], voters[0])
    send_transaction(web3, transactions["approve_transaction"], voters[1])

    print("5/10 Proveravam da je dalje glasanje blokirano porukom 'Voting ended.'.")
    expect_revert(web3, transactions["reject_transaction"], voters[2], "Voting ended.")

    print("6/10 Cekam checker da upise prihvacenu imovinu u MongoDB.")
    wait_for_asset(employee_token, approved_name, should_exist=True)

    print("7/10 Kreiram drugi BUY zahtev i pokrecem glasanje.")
    create_buy_order(employee_token, vetoed_name)
    vetoed_uuid = find_order(director_token, vetoed_name)
    transactions = start_vote(director_token, vetoed_uuid, voters)

    print("8/10 Proveravam da zaposleni ne moze da izvrsi direktorov veto.")
    expect_revert(web3, transactions["veto_transaction"], voters[0], "Only director.")

    print("9/10 Direktor salje veto; dalje glasanje mora biti nemoguce.")
    send_transaction(web3, transactions["veto_transaction"], accounts[0])
    expect_revert(web3, transactions["approve_transaction"], voters[0], "Voting ended.")
    wait_for_order_removal(director_token, vetoed_uuid)
    wait_for_asset(employee_token, vetoed_name, should_exist=False)

    print("10/10 Proveravam direktorov agregirani izvestaj.")
    report = expect(requests.get(
        f"{DIRECTOR_URL}/report",
        headers=auth_header(director_token),
        timeout=10,
    )).json()
    if not any(item["category"] == "demo" for item in report["statistics"]):
        raise RuntimeError("The approved asset is missing from the report.")

    print("USPESNO: glasanje je upisalo BUY, a veto nije imao efekat na MongoDB.")


if __name__ == "__main__":
    main()
