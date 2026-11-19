from graph_service.models.extraction import ExtractedTriple
from graph_service.services.triple_writer import build_triple_query, to_triple


def _skill_triple(tail_name="JS", snippet="熟练使用JS"):
    t = ExtractedTriple(
        relation="HAS_SKILL", tail_type="Skill", tail_name=tail_name, context_snippet=snippet
    )
    return to_triple("cand-1", t)


def test_build_triple_query_skill():
    query, params = build_triple_query(_skill_triple())
    assert "MATCH (c:Candidate {candidate_id: $candidate_id})" in query
    assert "MERGE (t:Skill {name: $name})" in query
    assert "[r:HAS_SKILL]" in query
    assert "SET r.raw_name = $raw_name, r.context_snippet = $context_snippet" in query
    assert params == {
        "candidate_id": "cand-1",
        "name": "JavaScript",  # 消歧后的标准名
        "raw_name": "JS",  # 原文保留
        "context_snippet": "熟练使用JS",
    }


def test_build_triple_query_company_uses_company_label():
    t = ExtractedTriple(
        relation="WORKED_AT",
        tail_type="Company",
        tail_name="Tencent",
        context_snippet="在 Tencent 任职",
    )
    query, params = build_triple_query(to_triple("cand-1", t))
    assert "MERGE (t:Company {name: $name})" in query
    assert "[r:WORKED_AT]" in query
    assert params["name"] == "腾讯"


def test_malicious_tail_name_stays_in_params_not_query():
    evil = "x'}) DETACH DELETE c //"
    query, params = build_triple_query(_skill_triple(tail_name=evil, snippet="s"))
    assert "DELETE" not in query
    assert params["raw_name"] == evil
