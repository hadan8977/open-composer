"""Original production attention features on retained current packet vintage."""
import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

WT = Path('/root/codex-test/wt-paper-continuity-20261014')
P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT))
spec = importlib.util.spec_from_file_location('news_builder', WT / 'scripts/build_news_attention_features.py')
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)
out = WT / 'data/features/_current_components/news_attention'
sessions, opens = m.build_sessions(date(2026, 10, 13))
universe = m.load_universe_panel(m.UNIVERSE_ROOT)
index = m.stage_articles(out_root=out, sessions=sessions, opens=opens, universe_panel=universe, top_n=1000, shuffle_seed=None, shuffle_mode=m.DEFAULT_SHUFFLE_MODE, force=False)
frame = m.build_year(2026, articles_dir=m._articles_dir(out), sessions=sessions, universe_panel=universe, top_n=1000, archive_first_session=int(index['first_session_index'] or 0))
frame.to_parquet(out / '2026.parquet', index=False, compression='zstd')
r = {'rows': len(frame), 'max_trade_date': str(frame.trade_date.max()), 'output': str(out / '2026.parquet'), 'source_requests': 0, 'formulas_changed': False, 'source_vintage': 'current packet normalization receipt; original provider-created+15min clock preserved, current_fetched_at retained separately; historical first local visibility not certified'}
(P / 'current-news-result.json').write_text(json.dumps(r, indent=2) + '\n')
print(r, flush=True)
