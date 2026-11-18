"""Private bound inputs for the versioned cash/quote readers; no research corpus."""

import hashlib
import json
from pathlib import Path

# Preserve the existing bounded quantity fixture's28-symbol identity and order.
SYMBOLS = [
    "MMM",
    "AMGN",
    "AAPL",
    "BA",
    "CAT",
    "CVX",
    "CSCO",
    "KO",
    "DOW",
    "GS",
    "HD",
    "HON",
    "INTC",
    "IBM",
    "JNJ",
    "JPM",
    "MCD",
    "MRK",
    "MSFT",
    "NKE",
    "PG",
    "CRM",
    "TRV",
    "UNH",
    "VZ",
    "V",
    "WBA",
    "DIS",
]
PROGRAM = Path("reports/research/program/owner-profit-delivery-plan-20261017")


def source_reference(root):
    """Keep metadata/contract checks real and all financial state under tmp_path.

    Scientific code is loaded by source_module from the hash-verified package.
    These invented JSON inputs grant no account, research or order authority.
    """

    def put(relative, value):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, sort_keys=True) + "\n")
        raw = path.read_bytes()
        return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())

    put(
        PROGRAM / "candidate-contribution/future-input-receiver/accepted-integration-contract.json",
        dict(output_identity=SYMBOLS, invented=True),
    )
    metadata = {
        f"quote_conditions_{tape}": put(
            Path("metadata") / f"conditions-{tape}.json", {"R": "invented regular quote"}
        )
        for tape in "ABC"
    }
    metadata["exchanges"] = put(Path("metadata/exchanges.json"), {"Q": "invented accepted venue"})
    put(PROGRAM / "paper-delivery/runtime-reader-bindings.json", dict(bindings=metadata))
    return root
