import json
import os
from pathlib import Path

from web3 import Web3


DEFAULT_ARTIFACT = Path(__file__).resolve().parents[2] / "blockchain" / "Voting.json"


class BlockchainGateway:
    def __init__(self, web3=None, artifact_path=None, sender=None):
        self.web3 = web3 or Web3(Web3.HTTPProvider(os.getenv("BLOCKCHAIN_URL", "http://ganache:8545")))
        self.sender = sender or os.getenv(
            "BLOCKCHAIN_SENDER", "0x90f8bf6a479f320ead074411a4b0e7944ea8c9c1"
        )
        path = Path(artifact_path or os.getenv("CONTRACT_ARTIFACT", str(DEFAULT_ARTIFACT)))
        artifact = json.loads(path.read_text(encoding="utf-8"))
        self.abi = artifact["abi"]
        self.bytecode = artifact["bytecode"]

    def deploy(self, voters: list[str]) -> str:
        sender = Web3.to_checksum_address(self.sender)
        checksummed_voters = [Web3.to_checksum_address(voter) for voter in voters]
        factory = self.web3.eth.contract(abi=self.abi, bytecode=self.bytecode)
        transaction_hash = factory.constructor(checksummed_voters).transact({"from": sender})
        receipt = self.web3.eth.wait_for_transaction_receipt(transaction_hash)
        if receipt.status != 1:
            raise RuntimeError("Contract deployment failed.")
        return receipt.contractAddress

    def transaction_payloads(self, contract_address: str) -> dict:
        address = Web3.to_checksum_address(contract_address)
        contract = self.web3.eth.contract(address=address, abi=self.abi)
        gas = int(os.getenv("VOTE_TRANSACTION_GAS", "120000"))
        base = {"to": address, "gas": gas, "value": 0}
        return {
            "approve_transaction": {
                **base,
                "data": contract.functions.approve()._encode_transaction_data(),
            },
            "reject_transaction": {
                **base,
                "data": contract.functions.reject()._encode_transaction_data(),
            },
            "veto_transaction": {
                **base,
                "from": Web3.to_checksum_address(self.sender),
                "data": contract.functions.veto()._encode_transaction_data(),
            },
        }

    def status(self, contract_address: str) -> dict:
        contract = self.web3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=self.abi,
        )
        return {
            "ended": contract.functions.ended().call(),
            "approved": contract.functions.approved().call(),
            "vetoed": contract.functions.vetoed().call(),
        }

