from copy import deepcopy

from open_composer.research.iteration_dossier import _external_brief_blockers


def payload():
    fields = {
        "url": "https://author.example/method",
        "published_or_updated_at": "2026-01-10",
        "credibility": "first-person",
        "core_claim": "source method",
        "project_applicability": "conditional case",
        "reflection": "selected seen",
    }
    return {
        "schema_version": 3,
        "current_source_card_paths": ["bound.jsonl"],
        "source_evidence_bindings": [{"bound": True}],
        "sources": [
            {
                **fields,
                "source_type": "practitioner_first_person",
                "source_kind": "authored_public_method",
            },
            {**fields, "source_type": "platform_docs"},
        ],
        "topic_coverage": list("abcdef"),
        "candidate_matrix_revisions": ["explicitconditional adaptation"],
    }


def test_authored_method_is_applicable_only_to_validated_component():
    p = payload()
    assert _external_brief_blockers(p, market_component=True) == []
    assert "external_brief_paper_sources_lt_3:0" in _external_brief_blockers(p)
    assert "external_brief_paper_sources_lt_1:0" in _external_brief_blockers(p, public_method=True)


def test_doc_or_self_label_does_not_bypass_component_primary_requirement():
    p = payload()
    for key, value in [("source_type", "platform_docs"), ("source_kind", "third_party_method")]:
        changed = deepcopy(p)
        changed["sources"][0][key] = value
        assert "external_brief_paper_sources_lt_1:0" in _external_brief_blockers(
            changed, market_component=True
        )
    missing = deepcopy(p)
    missing["sources"][0].pop("core_claim")
    assert any(
        "missing:core_claim" in b for b in _external_brief_blockers(missing, market_component=True)
    )
    single = deepcopy(p)
    single["sources"] = single["sources"][:1]
    assert "external_brief_sources_lt_2:1" in _external_brief_blockers(
        single, market_component=True
    )


def test_existing_paper_based_routes_keep_their_requirements():
    p = payload()
    p["sources"][0]["source_type"] = "paper"
    assert _external_brief_blockers(p, market_component=True) == []
    p["sources"][1]["source_kind"] = "official_author_implementation"
    assert _external_brief_blockers(p, public_method=True) == []
