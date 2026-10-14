"""Narrow existing-record prefix case plus actual post-install disk projection."""
import json
import sys
from pathlib import Path
import duckdb
import pyarrow.parquet as pq

ROOT = Path('/root/codex-test/open-composer')
WT = Path('/root/codex-test/wt-paper-continuity-20261014')
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(WT / 'scripts'))
from prepare_host_forward_version import compose, sha256
from forward_refresh_io import disk_admission
import refresh_equity_book_live as rf


def main():
    source = WT / 'data/features/daily_broad/2026.parquet'
    con = duckdb.connect()
    con.execute("SET threads=1; SET memory_limit='80MB'; SET max_temp_directory_size='32MB'")
    key = con.execute("SELECT symbol,trade_date,count(*) FROM read_parquet(?) GROUP BY symbol,trade_date HAVING count(*)>1 ORDER BY symbol,trade_date LIMIT 1", [str(source)]).fetchone()
    assert key and key[2] > 1
    old = HERE / 'actual-duplicate-prefix.parquet'
    candidate = HERE / 'actual-one-row-suffix.parquet'
    output = HERE / 'actual-prefix-composed.parquet'
    for p in (old, candidate, output):
        assert not p.exists(), 'prior attempt must remain'
    # Retain original occurrences and order; filter does not recompute a feature.
    table = pq.read_table(source, filters=[('symbol', '=', key[0]), ('trade_date', '=', key[1])])
    pq.write_table(table, old)
    nextrow = con.execute("SELECT symbol,trade_date FROM read_parquet(?) WHERE trade_date>? AND symbol='AAPL' ORDER BY trade_date LIMIT 1", [str(source), key[1]]).fetchone()
    assert nextrow
    suffix = pq.read_table(source, filters=[('symbol', '=', nextrow[0]), ('trade_date', '=', nextrow[1])])
    assert suffix.num_rows == 1
    pq.write_table(suffix, candidate)
    result = compose(old, candidate, output, expected_baseline_sha256=sha256(old), prefix_end=str(key[1])[:10], suffix_end=str(nextrow[1])[:10], source_manifest=HERE.parent.parent/'current-feature-input-manifest.json', version_id='maintenance-actual-subrecord-check')
    assert result['prefix_verification']['rows'] == key[2]
    assert result['legacy_duplicate_occurrences_preserved'] == key[2]-1
    result.update(input_source_path=str(source), input_source_sha256_reused_from_accepted_manifest='62038b26a8834c1c3f4bac2aba19a13ad154771e4fa5e8d9f407aac3696169a9', actual_prefix_key=[key[0], str(key[1])], actual_suffix_key=[nextrow[0], str(nextrow[1])], full_price_or_target_replay=False, price_values_or_feature_formulas_recomputed=False, equal_full_occurrences=all(table.slice(0,1).equals(table.slice(i,1)) for i in range(1,table.num_rows)))
    (HERE/'actual-duplicate-prefix-verification.json').write_text(json.dumps(result, indent=2)+'\n')
    cfg={'version_directory':'reports/research/program/paper-continuity-20261014/revisions/continuity-v2/capacity', 'disk_spill_bound_bytes':2*1024**3}
    try:
        disk_admission(WT, cfg, source_root=ROOT, tables=list(rf.UPSTREAM), live=WT/'data/live/equity_book', stages=list(rf.LIVE_STAGES), year=2026, fetch=True)
    except OSError:
        pass
    admission = sorted((WT/cfg['version_directory']/'admissions').glob('*.json'))[-1]
    value=json.loads(admission.read_text())
    value.update(scope='Actual Root raw/archive sizes and current accepted private products; conservative next-normal-refresh bound after installing these products', actual_installed_now=False, private_broker_files_read=0)
    install=json.loads((HERE.parent.parent/'reviewable-data-installation-manifest.json').read_text())
    value['installation_input_bytes']=sum(v['bytes'] for v in install['entries'])
    value['projected_available_after_initial_install_bytes']=value['actual_available_bytes']-value['installation_input_bytes']
    value['projected_additional_space_required_for_install_and_refresh_bytes']=max(0,value['required_available_bytes']-value['projected_available_after_initial_install_bytes'])
    (HERE/'actual-disk-admission.json').write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps({'actual_duplicate_rows':key[2],'numeric_replay':False,'disk':value},default=str))


if __name__=='__main__':
    main()
