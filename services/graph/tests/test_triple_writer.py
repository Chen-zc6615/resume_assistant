from graph_service.models.extraction import ExtractedTriple
from graph_service.services.triple_writer import (
    build_delete_query,
    build_write_query,
    to_resume_triple,
)


def _skill_triple(tail_name="JS", snippet="熟练使用JS"):
    t = ExtractedTriple(
        relation="HAS_SKILL", tail_type="Skill", tail_name=tail_name, context_snippet=snippet
    )
    return to_resume_triple(1001, t)


def test_build_write_query_skill():
    query, params = build_write_query(_skill_triple())
    assert "MERGE (c:Candidate {resume_id: $resume_id})" in query
    assert "MERGE (t:Skill {name: $name})" in query
    assert "[r:HAS_SKILL]" in query
    assert "SET r += $props" in query
    assert "CREATE (c)-[r:HAS_SKILL]->(t)" in query
    assert params == {
        "resume_id": 1001,
        "name": "JavaScript",  # 消歧后的标准名
        "props": {
            "raw_name": "JS",  # 原文保留在关系上
            "context_snippet": "熟练使用JS",
        },
    }


def test_build_write_query_company_uses_company_label():
    t = ExtractedTriple(
        relation="WORKED_AT",
        tail_type="Company",
        tail_name="Tencent",
        context_snippet="在 Tencent 任职",
    )
    query, params = build_write_query(to_resume_triple(1001, t))
    assert "MERGE (t:Company {name: $name})" in query
    assert "[r:WORKED_AT]" in query
    assert params["name"] == "腾讯"


def test_company_props_include_position_and_dates():
    t = ExtractedTriple(
        relation="WORKED_AT",
        tail_type="Company",
        tail_name="Tencent",
        context_snippet="腾讯 · 后端工程师",
        position="后端工程师",
        start_date="2020-07",
        end_date="2023-06",
    )
    _, params = build_write_query(to_resume_triple(1001, t))
    props = params["props"]
    assert props["position"] == "后端工程师"
    assert props["start_date"] == "2020-07"
    assert props["end_date"] == "2023-06"
    assert props["raw_name"] == "Tencent"  # 原文仍保留，标准名在节点上
    assert "major" not in props  # WORKED_AT 没有专业，空值不应出现


def test_school_props_include_major():
    t = ExtractedTriple(
        relation="STUDIED_AT",
        tail_type="School",
        tail_name="Tsinghua University",
        context_snippet="清华大学 · 计算机科学",
        major="计算机科学",
        start_date="2016-09",
    )
    _, params = build_write_query(to_resume_triple(1001, t))
    props = params["props"]
    assert params["name"] == "清华大学"
    assert props["major"] == "计算机科学"
    assert props["start_date"] == "2016-09"
    assert "position" not in props
    assert "end_date" not in props  # 简历没写的字段不存，不存空值


def test_none_fields_are_not_written():
    # 红线：未提及的字段不编造；这里表现为属性根本不出现，而不是存一个空值
    _, params = build_write_query(_skill_triple())
    assert all(v is not None for v in params["props"].values())
    assert set(params["props"]) == {"raw_name", "context_snippet"}


def test_malicious_tail_name_stays_in_params_not_query():
    evil = "x'}) DETACH DELETE c //"
    query, params = build_write_query(_skill_triple(tail_name=evil, snippet="s"))
    assert "DELETE" not in query
    assert params["props"]["raw_name"] == evil


def test_malicious_position_stays_in_params_not_query():
    evil = "x'}) DETACH DELETE c //"
    t = ExtractedTriple(
        relation="WORKED_AT",
        tail_type="Company",
        tail_name="腾讯",
        context_snippet="s",
        position=evil,
    )
    query, params = build_write_query(to_resume_triple(1001, t))
    assert "DELETE" not in query
    assert params["props"]["position"] == evil


def test_build_delete_query():
    query, params = build_delete_query(1001)
    assert "MATCH (c:Candidate {resume_id: $resume_id})" in query
    assert "HAS_SKILL" in query and "WORKED_AT" in query and "STUDIED_AT" in query
    assert "DELETE r" in query
    assert "DETACH" not in query
    assert params == {"resume_id": 1001}


def test_to_resume_triple_adds_head():
    t = ExtractedTriple(
        relation="HAS_SKILL", tail_type="Skill", tail_name="JS", context_snippet="熟练使用JS"
    )
    triple = to_resume_triple(1001, t)
    assert triple.resume_id == 1001
    assert triple.head_type == "Candidate"
    assert triple.tail_name == "JS"
