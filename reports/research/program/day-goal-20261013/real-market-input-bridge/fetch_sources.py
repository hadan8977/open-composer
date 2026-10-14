"""One-shot bounded public source snapshots; no market/account requests."""

import hashlib
import json
import resource
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent
SOURCES = {
    "rename": "https://www.elevancehealth.com/newsroom/anthem-inc-shareholders-approve-corporate-rebranding-new-name",
    "apple_split_dividend": "https://www.apple.com/newsroom/2020/07/apple-reports-third-quarter-results/",
    "WW_plan": "https://corporate.ww.com/news/news-details/2025/WeightWatchers-Reorganization-Plan-Confirmed-Clears-Path-for-Elimination-of-Majority-of-Legacy-Debt-Burden-and-Execution-of-Transformation-Plan/default.aspx",
    "SNOW_old_terminal": "https://www.sec.gov/Archives/edgar/data/1587755/000120919117046703/xslF345X03/doc4.xml",
    "ATVI_terminal": "https://investor.activision.com/static-files/6439fa79-7018-4f4d-adf5-192a2cd2007b",
    "WW_emergence": "https://www.sec.gov/Archives/edgar/data/105319/000119312525146171/d906370d8k.htm",
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def main():
    started = time.monotonic()
    p = OUT / "public-source-ledger.json"
    # This is a one-shot task entry. Existing attempts are never silently reset.
    assert not p.exists(), "source ledger already exists; no automatic rerun"
    rows = []
    total_bytes = 0
    opener = urllib.request.build_opener(NoRedirect())
    for name, url in SOURCES.items():
        r = {
            "id": name,
            "url": url,
            "requested_at_utc": datetime.now(UTC).isoformat(),
            "retries": 0,
            "redirects_followed": 0,
        }
        try:
            try:
                response = opener.open(
                    urllib.request.Request(
                        url, headers={"User-Agent": "Mozilla/5.0 OpenComposer-Bounded-Source-Audit"}
                    ),
                    timeout=25,
                )
            except urllib.error.HTTPError as exc:
                response = exc
            with response:
                data = response.read(1048576 + 1)
                assert len(data) <= 1048576, "single response cap"
                total_bytes += len(data)
                r.update(
                    {
                        "http_status": response.code,
                        "content_type": response.headers.get("Content-Type"),
                        "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                )
                suffix = ".pdf" if data.startswith(b"%PDF") else ".html"
                path = OUT / "sources" / (name + suffix)
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(data)
                r["snapshot"] = str(path.relative_to(OUT))
                r["usable_snapshot"] = response.code == 200
        except Exception as exc:
            r["failure"] = repr(exc)
            r["usable_snapshot"] = False
        rows.append(r)
        p.write_text(
            json.dumps(
                {
                    "new_web_search_units": 7,
                    "new_web_open_units": 7,
                    "web_transport_bytes_not_exposed": True,
                    "web_byte_charge_upper": 9437184,
                    "direct_requests": rows,
                    "direct_bytes": total_bytes,
                    "request_units_counted": 14 + len(rows),
                    "byte_budget_charge": 9437184 + total_bytes,
                    "old_model_request_ledger_unchanged": "40/40",
                    "market_requests": 0,
                    "automatic_retries": 0,
                },
                indent=2,
            )
            + "\n"
        )
        print(json.dumps(r), flush=True)
    usage = resource.getrusage(resource.RUSAGE_SELF)
    (OUT / "source-intake-receipt.json").write_text(
        json.dumps(
            {
                "cpu_seconds": usage.ru_utime + usage.ru_stime,
                "wall_seconds": time.monotonic() - started,
                "max_rss_kib": usage.ru_maxrss,
                "requests": len(rows),
                "bytes": total_bytes,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
