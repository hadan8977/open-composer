#!/usr/bin/env bash
# Bring the Form 4 insider tables up to date for the paper rehearsal
# (us_insider_buy_broad_monthly): EDGAR daily-index tail stages to the latest
# filing day, then rebuild ONLY the current-year insider feature file(s) with
# --as-of <today>, for the narrow root (data/features/insider) and/or the broad
# root (data/features/insider_broad).
#
# Why a wrapper: scripts/build_insider_features.py rebuilds every year in
# range when --force is passed. To refresh one year without disturbing a
# reader of the root (another executor may be reading it), the current-year
# file is built in a private temp out-root whose prior-year files are symlinks
# (so the builder skips them and the session index / visibility history still
# start in 2016), then swapped in with an atomic rename.
#
# Tail-fetch is run WITHOUT the top-1000 CIK filter (--tail-universe-top-n 0):
# a fetched day is never re-fetched, so a day fetched narrow would permanently
# lack the broad universe's filings. Cost is ~3x the requests for the new days
# only (a few minutes per day at the SEC fair-access rate). Days already
# fetched narrow before 2026-09-18 (through 20260915) stay narrow -- re-fetch
# them by deleting data/raw/insider/tail/parsed/<yyyymmdd>.parquet first.
#
# Usage:
#   scripts/refresh_insider_features_for_paper.sh [--root narrow|broad|both]
#       [--as-of YYYY-MM-DD] [--skip-tail] [--allow-broad-while-building]
#
# Memory: run the whole thing under scripts/run_capped.sh (1.8G) and detached:
#   OC_ALREADY_CAPPED=1 nohup ./scripts/run_capped.sh --mem 1.8G -- \
#       bash scripts/refresh_insider_features_for_paper.sh --root narrow \
#       > logs/refresh_insider_narrow_$(date -u +%Y%m%dT%H%M%SZ).log 2>&1 &
# (OC_ALREADY_CAPPED=1 tells the script not to nest a second capped scope.)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PATH="$HOME/.local/bin:$PATH"

TARGETS="narrow"
AS_OF="$(date -u +%F)"
SKIP_TAIL=0
ALLOW_BROAD_WHILE_BUILDING=0
while [ $# -gt 0 ]; do
    case "$1" in
        --root) TARGETS="$2"; shift 2 ;;
        --as-of) AS_OF="$2"; shift 2 ;;
        --skip-tail) SKIP_TAIL=1; shift ;;
        --allow-broad-while-building) ALLOW_BROAD_WHILE_BUILDING=1; shift ;;
        -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done
case "$TARGETS" in narrow|broad|both) ;; *) echo "--root must be narrow|broad|both" >&2; exit 2 ;; esac
YEAR="${AS_OF%%-*}"
mkdir -p logs

log() { echo "[$(date -u +%FT%TZ)] $*"; }

CAP=(./scripts/run_capped.sh --mem 1.8G --)
if [ "${OC_ALREADY_CAPPED:-0}" = "1" ]; then
    CAP=()
fi

if [ "$SKIP_TAIL" -eq 0 ]; then
    log "EDGAR tail-index through $AS_OF"
    uv run python scripts/collect_sec_insider_transactions.py --stage tail-index --tail-end "$AS_OF"
    log "EDGAR tail-fetch (every Form 4 issuer; --tail-universe-top-n 0)"
    uv run python scripts/collect_sec_insider_transactions.py --stage tail-fetch --tail-universe-top-n 0
    log "tail parsed through: $(ls data/raw/insider/tail/parsed/*.parquet 2>/dev/null | tail -1 | xargs -r basename)"
fi

rebuild_root() {
    # $1 out root, $2 universe root, $3 --top-n, $4 --weekly-top-n
    local out="$1" uni="$2" topn="$3" wtop="$4"
    if ! ls "$out"/[0-9][0-9][0-9][0-9].parquet >/dev/null 2>&1; then
        log "SKIP $out: no yearly files yet (full build has not finished); nothing to refresh"
        return 0
    fi
    if ! ls "$uni"/[0-9][0-9][0-9][0-9].parquet >/dev/null 2>&1; then
        log "SKIP $out: universe root $uni has no yearly files"
        return 0
    fi
    local tmp="$out/_refresh_${YEAR}_$$"
    rm -rf "$tmp"
    mkdir -p "$tmp"
    local f y
    for f in "$out"/[0-9][0-9][0-9][0-9].parquet; do
        y="$(basename "$f" .parquet)"
        [ "$y" = "$YEAR" ] && continue
        ln -s "$(realpath "$f")" "$tmp/$y.parquet"
    done
    log "rebuild $out/$YEAR.parquet as of $AS_OF (universe $uni, top-n $topn) in $tmp"
    "${CAP[@]}" uv run python scripts/build_insider_features.py \
        --universe-root "$uni" --top-n "$topn" --weekly-top-n "$wtop" \
        --out-root "$tmp" --as-of "$AS_OF" --end-year "$YEAR" --skip-weekly-panel
    if [ ! -s "$tmp/$YEAR.parquet" ]; then
        log "FAILED $out: $tmp/$YEAR.parquet was not produced; leaving $out untouched"
        return 1
    fi
    # Atomic swap: a reader that already opened the old file keeps it.
    mv -f "$tmp/$YEAR.parquet" "$out/$YEAR.parquet"
    if [ -f "$tmp/_build_manifest.json" ]; then
        sed "s#$tmp#$out#g" "$tmp/_build_manifest.json" > "$out/_build_manifest.json"
    fi
    printf '{"refreshed_at": "%s", "as_of": "%s", "year": %s, "universe_root": "%s", "top_n": %s}\n' \
        "$(date -u +%FT%TZ)" "$AS_OF" "$YEAR" "$uni" "$topn" > "$out/_refresh_manifest.json"
    rm -rf "$tmp"
    log "refreshed $out/$YEAR.parquet"
}

if [ "$TARGETS" = "narrow" ] || [ "$TARGETS" = "both" ]; then
    rebuild_root data/features/insider data/features/universe 1000 500
fi
if [ "$TARGETS" = "broad" ] || [ "$TARGETS" = "both" ]; then
    if [ "$ALLOW_BROAD_WHILE_BUILDING" -eq 0 ] && pgrep -f "build_insider_features.py.*insider_broad" >/dev/null 2>&1; then
        log "SKIP broad: the full insider_broad build is still running (pass --allow-broad-while-building to override)"
    elif [ "$ALLOW_BROAD_WHILE_BUILDING" -eq 0 ] && ! grep -q "insider broad done" logs/build_broad_features.log 2>/dev/null; then
        log "SKIP broad: logs/build_broad_features.log does not report 'insider broad done' yet"
    else
        rebuild_root data/features/insider_broad data/features/universe_broad 1000000 1000000
    fi
fi
log "done"
