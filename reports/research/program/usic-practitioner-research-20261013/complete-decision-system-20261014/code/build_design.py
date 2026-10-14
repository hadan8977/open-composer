"""Source-to-decision definitions and a draft spec; no price calculations."""

import hashlib
import json
import resource
import time
from pathlib import Path

import yaml

P = Path(__file__).resolve().parents[1]
ROOT = Path.cwd()
IID = "martin_complete_system_20261014_dev"
CID = "martin_complete_system_20261014"


def binding(path):
    raw = path.read_bytes()
    return dict(
        path=str(path.relative_to(ROOT)), sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw)
    )


def save(path, obj):
    path.parent.mkdir(exist_ok=True, parents=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def main():
    start = time.process_time()
    # The recorded native pre-discovery result must be OK before generation.
    from open_composer.research.campaign import validate_campaign_contract

    check = validate_campaign_contract(CID, root=ROOT, stage="pre-discovery")
    assert check.status == "ok", check
    sources = {
        "G": dict(
            url="https://tradingresourcehub.substack.com/p/martin-luk-283-usic-2024-key-lessons",
            snapshot=P.parent.parent / "martin-luk-usic-20261013/sources/guest2024-original.html",
            version="2024 retrospective guest essay published2025-02-01",
        ),
        "S": dict(
            url="https://tradingresourcehub.substack.com/p/martin-luk-study-process",
            snapshot=P.parent
            / "public-decision-replay/study-figure-source/authored_short_study_html.bin",
            version="2026-01-10 retrospective short study",
        ),
        "I": dict(
            url="https://youtubetotranscript.com/transcript?current_language_code=en&v=VKNEJA5r8zw",
            snapshot=P / "sources/primary-passages-01.json",
            version="2025 retrospective interview, published2026; auto-transcription",
        ),
        "IQ": dict(
            url="https://youtubetotranscript.com/transcript?current_language_code=en&v=VKNEJA5r8zw",
            snapshot=P / "sources/primary-open-01.json",
            version="Same interview context/anchors",
        ),
        "IC": dict(
            url="https://youtubetotranscript.com/transcript?current_language_code=en&v=VKNEJA5r8zw",
            snapshot=P / "sources/interview-retained-passages.json",
            version="Retained targeted interview excerpts; not full audiovisual review",
        ),
        "Q": dict(
            url="https://qullamaggie.com/my-3-timeless-setups-that-have-made-me-tens-of-millions/",
            snapshot=P / "sources/primary-passages-01.json",
            version="Original2021 author setup post",
        ),
        "N": dict(
            url="https://qullamaggie.com/lessons-from-a-140k-loss/",
            snapshot=P / "sources/primary-passages-01.json",
            version="2020 author negative same-day multiple attempts",
        ),
    }
    units = [
        (
            "ML_watchlist",
            "G",
            "P0087-P0097",
            (
                "Previous-day performers, premarket gaps and30day leaders feed streng"
                "th lists; emerging groups matter."
            ),
            (
                "Causal observations keyed by decision date; rank relative strength, "
                "dollar turnover and group upgrades; list is not entry."
            ),
            (
                "Scanner percentiles and sector clustering are local hypotheses. Miss"
                "ing historical group labels disable group-score contribution, not fi"
                "ll with future themes."
            ),
        ),
        (
            "ML_ADR",
            "G",
            "P0055,P0083",
            "HighADR preference, stop generally<=halfADR and1-5%; ADR>5% not a hard filter.",
            (
                "ADR20 and volume are trailing only; soft score rather than a univers"
                "alADR>5 rejection."
            ),
            "20day window and relative scoring are adaptation, no claim original fixed formula.",
        ),
        (
            "ML_context",
            "IQ",
            "L185-L218",
            (
                "Chop/declining breadth/failed followthrough lead to less trading; sp"
                "eculation weakness need not mean whole market weakness."
            ),
            (
                "QQQ/IWM state plus trailing own closed-trade evidence; do not infer "
                "regime from current trade future."
            ),
            (
                "Index-state/breadth proxy and feedback thresholds must be tested sep"
                "arately. General index never substitutes actual theme state."
            ),
        ),
        (
            "ML_shape",
            "I",
            "L366-L390",
            (
                "Within-base or first retest with higher lows preferred; extended sup"
                "portless entries and weak downtrends cited as failures."
            ),
            (
                "Confirmed pivots have explicit recognition time; base age/depth/cont"
                "raction measured before session; first touch counter."
            ),
            (
                "Exact age/depth/contraction cutoffs are ours, not trader rules. Do n"
                "ot retrospectively move base beginning."
            ),
        ),
        (
            "ML_anchor",
            "IQ",
            "L227-L265",
            (
                "Base swing extrema and high-volume gap anchors; speaker also adjusts"
                " anchors to prior price respect."
            ),
            (
                "<=3 known anchor candidates; pivot recognition delay; rank by past-o"
                "nly support/rejection touches, freeze before decision."
            ),
            (
                "Retrospective chart adjustment is not itself a causal profitable rul"
                "e. Ranking surrogate tested vs fixed anchor and noAVWAP; no post-tri"
                "gger or future-return anchor choice."
            ),
        ),
        (
            "ML_confluence",
            "IQ",
            "L229-L234",
            (
                "EMA/AVWAP/prior swing levels together form potential support; lower "
                "timeframe execution distinguishes setup from trigger."
            ),
            (
                "Support clusters scaled by trailingADR; wick touch then reclaim; sta"
                "le/future support rejected."
            ),
            "Confluence radius and support count are local adaptations; not EMA-only system.",
        ),
        (
            "ML_clock",
            "I",
            "L373-L380",
            (
                "Previous completed lower-timeframe bar-high breakout; early1minute a"
                "nd later5minute tactics; LOD or bar-low stop varies with width."
            ),
            (
                "First15minutes use1m completed bars, minutes15-60 use5m, minutes60-1"
                "20 use15m; intent known only at completed bar end, next-minute marke"
                "t/capped order."
            ),
            (
                "60-120 use15m and fixed two-hour cutoff are bounded adaptations; tra"
                "nscript first15minute wording is noisy. Completed-close trigger dela"
                "ys source live crossing; prearmed crossing evaluated separately only"
                " with native adapter."
            ),
        ),
        (
            "ML_stop",
            "G",
            "P0055,P0136",
            (
                "Stop defined before entry; hard stop after fill. Planned percent ris"
                "k is distinct from stock stop distance."
            ),
            (
                "Choose LOD when valid<=halfADR, otherwise prior completed confirmati"
                "on-bar low; floor tick; freeze quantity and initialR before fill."
            ),
            (
                "The breakout-bar future low cannot size a prearmed order. Gap losses"
                " and fees can exceed plannedR; no clipping."
            ),
        ),
        (
            "ML_reentry",
            "G",
            "P0059-P0061",
            (
                "Reentry caught winners but frequent attempts caused long losing stre"
                "aks; market condition matters."
            ),
            (
                "Stopout requires fresh support visit and new completed confirmation;"
                " cumulative attempts/costs retained per epoch and session."
            ),
            (
                "3/day and8/epoch are research protection hypotheses, not original th"
                "resholds. All rejected attempts logged."
            ),
        ),
        (
            "ML_long_exit",
            "IC",
            "L527,L532,L555-L559,L619-L633",
            (
                "Longs may trim strength and follow9EMA or stop below it; premature d"
                "iscretionary full sale also acknowledged."
            ),
            (
                "Initial hard stop plus daily-close9EMA exit queued next observed ses"
                "sion; optional15%3R trim neutral market; strong-market no trim; no w"
                "eak-followthrough after2sessions exit."
            ),
            (
                "Neutral/strong definitions,2session time stop and partial schedule a"
                "re adaptation. Hold until real exit; no EOD force-flat; open tail ma"
                "rked, not liquidated terminally."
            ),
        ),
        (
            "ML_short_exit",
            "S",
            "P0170-P0176",
            (
                "Shorts quick swings;15%>3R and support trims; hourly50EMA/extension "
                "exit, not weeks-long home run."
            ),
            (
                "Separate short-side model interface; requires actualETB/borrow/SSR b"
                "efore economic short strategy."
            ),
            (
                "Not executed in this first long implementation. Old four-case short "
                "grid stays closed. Short component not claimed absent from original "
                "performance."
            ),
        ),
        (
            "ML_feedback",
            "G",
            "P0121-P0129",
            "Long losing streaks/drawdown led to smaller initial size and progressive exposure.",
            (
                "Risk0.125%-0.5% from own prior completed trades and currentNAV; caps"
                " at35%name/100%gross/2%initial aggregate risk; monthly new-entry ris"
                "k room5%."
            ),
            (
                "Caps and finite-state transitions are local test policies; no realiz"
                "ed NAV floor or claim trader used identical controller."
            ),
        ),
        (
            "ML_break_EP",
            "Q",
            "L51-L109",
            (
                "Breakout and news EP are different source setups; news catalyst and "
                "unexpected revaluation matter to EP."
            ),
            (
                "Matched breakout comparator; no price-only gap called faithfulEP. Re"
                "tain separate EP dependency pendingPIT catalyst packets."
            ),
            (
                "OriginalQullamaggie3-5day trim is not Martin15%3R; source versions n"
                "ever fused as universal rule."
            ),
        ),
        (
            "ML_counterevidence",
            "N",
            "L23-L32",
            "Repeated scale-in/out on resistant vehicle accumulated140k selfreportedloss.",
            (
                "Stop/reentry friction and nonfollowing opportunities count in joint "
                "account; wrong vehicle selection can dominate timing."
            ),
            (
                "Anecdote challenges all-bounce and unlimited-reentry inference; does"
                " not establish population null or exact loss distribution."
            ),
        ),
    ]
    catalog = []
    cards = []
    for claim, src, locator, fact, observable, limit in units:
        s = sources[src]
        b = binding(s["snapshot"])
        catalog.append(
            dict(
                claim_id=claim,
                source_version=s["version"],
                source_url=s["url"],
                snapshot=b,
                locator=locator,
                source_mechanism=fact,
                executable_expression=observable,
                adaptation_and_limits=limit,
                status="source_grounded_translation_not_economic_validation",
            )
        )
        cards.append(
            dict(
                claim_id=claim,
                claim=fact,
                source_url=s["url"],
                source_type="practitioner_first_person",
                accessed_at="2026-10-14",
                applies_to=["public_method_replication", "martin_complete_system"],
                impact_on_spec=observable,
                limitations=limit,
                snapshot_path=b["path"],
                snapshot_sha256=b["sha256"],
                evidence_locator=locator,
            )
        )
    save(
        P / "mechanism-catalog.json",
        dict(
            schema_version=1,
            units=catalog,
            source_examples_seen=True,
            private_complete_account_reproduction=False,
        ),
    )
    cardpath = ROOT / "reports/harness/source_cards" / (CID + ".jsonl")
    assert not cardpath.exists()
    cardpath.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cards))
    behavior = dict(
        schema_version=1,
        scope=(
            "Long complete-system prototype; public-case continuous development c"
            "ontrols nonpromotable"
        ),
        ema_periods=[9, 21, 50],
        adr_sessions=20,
        leadership_sessions=30,
        warmup_sessions=150,
        pivot_left=2,
        pivot_right=2,
        base_min_sessions=5,
        base_max_sessions=60,
        base_max_depth_ADR=5.0,
        contraction_ratio_max=0.75,
        support_radius_ADR=0.15,
        minimum_confluence=2,
        anchor_cap=3,
        anchor_touch_lookback=20,
        entry_clock=[[0, 15, 1], [15, 60, 5], [60, 120, 15]],
        entry_cutoff_minute=120,
        risk_normal=0.005,
        risk_probe=0.00125,
        position_cap=0.35,
        gross_cap=1.0,
        aggregate_risk_cap=0.02,
        monthly_new_risk_cap=0.05,
        attempts_per_day=3,
        attempts_per_epoch=8,
        max_stop_ADR=0.5,
        max_stop_pct=0.05,
        price_tick=0.01,
        minimum_stop_bps=30,
        entry_price_cap_bps=20,
        participation_fraction=0.01,
        partial_R=3.0,
        partial_fraction=0.15,
        failure_sessions=2,
        feedback_closed_trades=5,
        feedback_probe_if_net_R_below=0.0,
        feedback_pause_drawdown=0.05,
        feedback_pause_sessions=3,
        primary_cost_per_side_bps=20,
        stress_cost_per_side_bps=40,
        initial_R=(
            "reference entry minus frozen initial stop; never rewritten by fill, trim or stop raise"
        ),
        trail=(
            "Daily completed close belowEMA9 => next session first valid observed"
            " price exit; explicit missing-active-data unknown"
        ),
        novel_thresholds=(
            "All numeric shape/score/policy thresholds are our preregistered adap"
            "tations; parameters not fitted yet"
        ),
        tick_and_order=(
            "0.01 tick conditional research convention, not all-symbol executable"
            " tick certification"
        ),
    )
    spec = dict(
        name=CID,
        description=(
            "Source-led complete long decision prototype, manual research only; s"
            "tructured causal decisions in notes.decision_system"
        ),
        timeframe="1m",
        universe=["COIN", "GME", "LMND", "SMCI", "SOFI", "SOUN"],
        lifecycle="draft",
        position_direction="long_only",
        entry=dict(all=["signal_ready > 0"], any=[]),
        exit=dict(all=[], any=["exit_ready > 0"]),
        risk=dict(
            max_trades_per_day=3, max_position_weight=0.35, stop_loss_pct=None, take_profit_pct=None
        ),
        portfolio=dict(
            mode="single_symbol",
            max_symbols_per_day=4,
            gross_exposure_limit=1.0,
            max_symbol_weight=0.35,
            same_day_flatten=False,
        ),
        costs=dict(
            commission_pct=0, slippage_bps=20, impact_model="linear", impact_eta=0, impact_gamma=0
        ),
        execution=dict(
            backend="python_reference",
            mode="manual_signal",
            signal_on="bar_close",
            fill_assumption="next_bar_open",
            broker="none",
        ),
        data=dict(
            source="alpaca",
            symbol="COIN",
            path=str(P.relative_to(ROOT) / "inputs/accepted-minute.csv"),
            feed="sip",
        ),
        data_assumptions=dict(
            source="alpaca",
            adjusted=False,
            timezone="America/New_York",
            acquisition_tier="research_replay_cache",
        ),
        factors={
            x: dict(
                source="feature_packet",
                field=x,
                default=0,
                description="Causal deterministic state-machine emission, not LLM/news",
            )
            for x in ["signal_ready", "exit_ready"]
        },
        llm_review=dict(enabled=False),
        required_capabilities=["market.alpaca_bars"],
        notes=dict(
            intent=(
                "Implement full public long decision flow; do not claim source-select"
                "ed universe as profitableAlpha"
            ),
            decision_system=behavior,
            research_design=dict(
                iter_id=IID,
                candidate_cap=8,
                method_variants=(
                    "Eight preregistered campaign ablations; compare identical input and costs"
                ),
                parameter_ranges=dict(
                    base_min_sessions=[5, 10],
                    support_radius_ADR=[0.10, 0.15, 0.20],
                    contraction_ratio_max=[0.5, 0.75],
                    clock_policy=["source_clock"],
                    stop_policy=["LOD_then_bar_low"],
                    anchor_policy=["fixed", "prior_respect"],
                    reentry=[False, True],
                    partial=[False, True],
                    feedback=[False, True],
                ),
                search_space=(
                    "The exact8campaign configurations only; ranges document uncertainty,"
                    " NOT permission for Cartesian expansion"
                ),
                selection_objective=(
                    "Matched development contribution, errors, fill losses and costs; no "
                    "winner selection for promotion"
                ),
            ),
            open_questions=[
                (
                    "PIT universe/permanentidentity/delist chain needed for selectable de"
                    "ployment branch"
                ),
                (
                    "Exact fullbrokerledger and subjective themes unavailable; no champio"
                    "nship-account reproduction"
                ),
                (
                    "Raw/action/minute alignment and adjusted-cache coverage require actu"
                    "al independent input acceptance"
                ),
                (
                    "Nautilus execution adapter integration needed for intrabar restingst"
                    "op rather than confirmed-close adaptation"
                ),
            ],
        ),
    )
    sp = ROOT / "strategy_specs/drafts" / (CID + ".yaml")
    assert not sp.exists()
    sp.write_text(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True))
    save(
        P / "design-bindings.json",
        dict(
            spec=binding(sp),
            source_cards=binding(cardpath),
            mechanisms=binding(P / "mechanism-catalog.json"),
            campaign=binding(
                ROOT / "reports/research/campaigns" / CID / "research-campaign-contract.json"
            ),
            CPU=time.process_time() - start,
            max_RSS_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            economic_execution=False,
        ),
    )
    print(sp)


if __name__ == "__main__":
    main()
