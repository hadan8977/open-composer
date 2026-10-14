"""Bounded public methodology snapshots; never acquires market data."""

import hashlib
import html
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
SOURCES = [
    (
        "dlsa-paper-v2",
        "https://arxiv.org/html/2106.04028v2",
        "paper",
        "At each time",
        "DLSA PCA uses causal 252-day correlation and 60-day loading estimates; "
        "cost learning is applied to mapped stock allocations. PCA is a source-supported "
        "adaptation, distinct from original characteristic-conditioned IPCA.",
    ),
    (
        "alpaca-bars",
        "https://docs.alpaca.markets/us/reference/stockbars",
        "provider_official_docs",
        "apply all above adjustments",
        "Alpaca all includes split, cash-dividend and spin-off "
        "adjustments; it does not document a delisting-total-return field or historical first "
        "publication timestamp. Current-vintage prices need episode/terminal reconciliation.",
    ),
    (
        "historical-membership",
        "https://raw.githubusercontent.com/fja05680/sp500/master/README.md",
        "provider_official_docs",
        "Historical",
        "The maintained historical index lists support "
        "a fixed historical cohort without current-winner selection; retrospective ticker "
        "labels are not permanent share-class evidence and may be revised.",
    ),
    (
        "independent-pca",
        (
            "https://raw.githubusercontent.com/Rutgers-Quant-Finance-Club/Equi"
            "ties_Arbitrage/main/README.md"
        ),
        "practitioner_first_person",
        "survivorship bias",
        "An independent PCA implementation "
        "self-reports delisting loss, survivorship bias and substantial cost drag. Its reported "
        "performance is not reliable DLSA replication or evidence to omit terminal stocks.",
    ),
]


def main():
    dest = OUT / "sources"
    dest.mkdir(exist_ok=True)
    receipts, cards = [], []
    for name, url, kind, needle, claim in SOURCES:
        p = dest / (name + ".txt")
        response = requests.get(url, timeout=40)
        at = datetime.now(UTC).isoformat()
        receipt = {
            "name": name,
            "source_url": url,
            "status_code": response.status_code,
            "fetched_at": at,
            "bytes": len(response.content),
        }
        receipts.append(receipt)
        if response.status_code != 200 or len(response.content) > 3_000_000:
            continue
        p.write_bytes(response.content)
        normalized = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", response.text)).split())
        hit = re.search(re.escape(needle), normalized, re.IGNORECASE)
        if not hit:
            receipt["quote_status"] = "needle_absent; source not canonically claimed"
            continue
        quote = normalized[hit.start() : hit.start() + len(needle)]
        receipt["sha256"] = hashlib.sha256(response.content).hexdigest()
        cards.append(
            {
                "claim_id": name,
                "source_url": url,
                "source_type": kind,
                "claim": claim,
                "quote": quote,
                "fetched_at": at,
                "source_sha256": receipt["sha256"],
                "verification_status": "source_verified",
                "snapshot_path": str(p.relative_to(ROOT)),
                "scope": (
                    "public methodology; no entitlement, readiness or performance certification"
                ),
            }
        )
    (OUT / "sources/source-fetch-receipt.json").write_text(json.dumps(receipts, indent=2) + "\n")
    (OUT / "source-cards.jsonl").write_text(
        "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cards)
    )
    print(
        json.dumps(
            {
                "actual_http_requests": len(receipts),
                "verified_cards": len(cards),
                "bytes": sum(x["bytes"] for x in receipts),
            }
        )
    )


if __name__ == "__main__":
    main()
