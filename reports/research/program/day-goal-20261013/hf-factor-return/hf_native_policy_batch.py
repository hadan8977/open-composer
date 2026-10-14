"""Reuse identical parsed source-policy thresholds only within each native collection."""
import functools
import hashlib
import json
from pathlib import Path


def install(log):
    import open_composer.models.source_card as source
    import open_composer.research.knowledge_memory as knowledge

    original_collect = knowledge._collect_sources

    def collect(root):
        policy = Path(root) / 'harness/source_policy.yaml'
        before = policy.read_bytes() if policy.exists() else None
        original_threshold = source._staleness_threshold
        cache = functools.lru_cache(maxsize=None)(original_threshold)
        # Native SourceCard validation/age/expiry/check logic remains exactly unchanged.
        source._staleness_threshold = cache
        try:
            rows = original_collect(root)
        finally:
            source._staleness_threshold = original_threshold
        after = policy.read_bytes() if policy.exists() else None
        if before != after:
            raise RuntimeError('Source policy changed during collection; do not accept index')
        log.append(dict(native_collection='_collect_sources', source_rows=len(rows),
                        policy_path=str(policy), policy_sha256=hashlib.sha256(before).hexdigest() if before is not None else None,
                        policy_bytes_before_after_equal=True, cache_hits=cache.cache_info().hits,
                        cache_misses=cache.cache_info().misses, all_native_card_validations_executed=True,
                        freshness_or_guard_checks_skipped=False, cache_lifetime='This single collector call only'))
        return rows

    knowledge._collect_sources = collect
    return knowledge


def synthetic_parity():
    import datetime
    import open_composer.models.source_card as source

    root = Path.cwd()
    kinds = ['broker_official_docs','exchange_official_docs','provider_official_docs','regulatory_docs',
             'paper','platform_docs','industry_standard','unverified']
    cards = [source.SourceCard(claim_id=str(i), claim='synthetic source policy parity', source_url='https://example.com',
               source_type=kind, accessed_at='2026-10-13' if i%2 else '2020-01-01', expires_at='2020-01-02' if i%3==0 else None)
             for i,kind in enumerate(kinds)]
    today = datetime.date(2026,10,13)
    baseline = [source.check_source_card(card,root,today=today) for card in cards]
    old=source._staleness_threshold
    source._staleness_threshold=functools.lru_cache(maxsize=None)(old)
    try:
        actual=[source.check_source_card(card,root,today=today) for card in cards]
    finally:
        source._staleness_threshold=old
    assert baseline==actual
    return dict(cases=len(cards),types=kinds,actual_native_status_dataclass_equal=True,
                changes_to_claim_data_models_native_guards=False)
