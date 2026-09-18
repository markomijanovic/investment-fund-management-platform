import json
from pathlib import Path


def test_compiled_contract_contains_veto_and_nonempty_bytecode():
    root = Path(__file__).resolve().parents[1]
    source = (root / "blockchain" / "Voting.sol").read_text(encoding="utf-8")
    artifact = json.loads((root / "blockchain" / "Voting.json").read_text(encoding="utf-8"))
    function_names = {item.get("name") for item in artifact["abi"] if item.get("type") == "function"}

    assert {"approve", "reject", "veto", "ended", "approved", "vetoed"} <= function_names
    assert len(artifact["bytecode"]) > 100
    assert 'require(msg.sender == director, "Only director.")' in source
    assert 'require(!ended, "Voting ended.")' in source
