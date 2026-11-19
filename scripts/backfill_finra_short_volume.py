"""Build the pre-CNMS exchange-listed Reg SHO files from FINRA's TRF/ADF files."""

import csv
import gzip
import io
from datetime import date, timedelta

from open_composer.market_sessions import us_equity_session_dates
from scripts.collect_finra_short_volume import (
    BASE_URL,
    FIRST_AVAILABLE_DATE,
    RAW_HEADER_COLUMNS,
    RAW_ROOT,
    FinraCdnClient,
)

LEGACY_ROOT = RAW_ROOT / "trf_adf"


def backfill_legacy_volume():
    LEGACY_ROOT.mkdir(parents=True, exist_ok=True)
    days = us_equity_session_dates(date(2016, 1, 1), FIRST_AVAILABLE_DATE - timedelta(days=1))
    client = FinraCdnClient(min_interval=0.25)
    missing_adf = []
    try:
        for index, day in enumerate(days, 1):
            path = LEGACY_ROOT / f"{day}.txt.gz"
            if path.exists():
                continue
            volumes = {}
            for facility in ("FNSQ", "FNYX", "FNRA"):
                url = f"{BASE_URL}/{facility}shvol{day:%Y%m%d}.txt"
                status, payload, _ = client.get(url, retries=1 if facility == "FNRA" else 4)
                if facility == "FNRA" and status == 403:
                    missing_adf.append(day)
                    continue
                if status != 200:
                    raise RuntimeError(f"FINRA returned HTTP {status} for {url}")
                lines = payload.decode("utf-8-sig").splitlines()
                for _, symbol, short, exempt, total, market in csv.reader(
                    lines[1:-1], delimiter="|"
                ):
                    row = volumes.setdefault(symbol, [0, 0, 0, []])
                    row[0] += int(short)
                    row[1] += int(exempt)
                    row[2] += int(total)
                    row[3].append(market)
            result = io.StringIO()
            writer = csv.writer(result, delimiter="|", lineterminator="\n", quoting=csv.QUOTE_NONE)
            writer.writerow(RAW_HEADER_COLUMNS)
            for symbol, (short, exempt, total, markets) in sorted(volumes.items()):
                writer.writerow((f"{day:%Y%m%d}", symbol, short, exempt, total, ",".join(markets)))
            writer.writerow((len(volumes),))
            temporary = path.with_suffix(".part")
            with gzip.open(temporary, "wt", encoding="utf-8", compresslevel=1) as output:
                output.write(result.getvalue())
            temporary.replace(path)
            if index % 50 == 0 or index == len(days):
                print(f"{index}/{len(days)} sessions through {day}", flush=True)
    finally:
        client.close()
    if missing_adf:
        print(
            f"ADF unavailable on {len(missing_adf)} downloaded sessions "
            f"from {missing_adf[0]} to {missing_adf[-1]}"
        )


if __name__ == "__main__":
    backfill_legacy_volume()
