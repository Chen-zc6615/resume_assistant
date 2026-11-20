"""真实 Neo4j 集成测试（连 neo4j-test 容器 :57687，tmpfs，每个测试前后全库清空）。

假驱动测不出 Cypher 语法、MERGE/CREATE 真实行为和事务回滚，这些只能真连库验证。
"""

import pytest
from graph_service.models.extraction import ExtractedTriple
from graph_service.services.triple_writer import (
    build_delete_query,
    build_write_query,
    to_resume_triple,
    write_resume,
)
from neo4j.exceptions import Neo4jError


def _q(store, query, **params):
    records, _, _ = store._driver.execute_query(query, params, database_=store._database)
    return [dict(r) for r in records]


def _skill(name, snippet="s"):
    return ExtractedTriple(
        relation="HAS_SKILL", tail_type="Skill", tail_name=name, context_snippet=snippet
    )


def _job(position, start, end, company="Tencent"):
    return ExtractedTriple(
        relation="WORKED_AT",
        tail_type="Company",
        tail_name=company,
        context_snippet=f"{company} {position}",
        position=position,
        start_date=start,
        end_date=end,
    )


def test_synonyms_merge_into_one_node(neo4j_test_store):
    """消歧 + 节点 MERGE：JS / Javascript 落到同一个 JavaScript 节点，原文各自留在关系上。"""
    write_resume(neo4j_test_store, 900001, [_skill("JS")])
    write_resume(neo4j_test_store, 900002, [_skill("Javascript")])

    nodes = _q(neo4j_test_store, "MATCH (s:Skill) RETURN s.name AS name")
    assert nodes == [{"name": "JavaScript"}]
    raws = _q(neo4j_test_store, "MATCH (:Candidate)-[r:HAS_SKILL]->(:Skill) RETURN r.raw_name AS raw")
    assert sorted(r["raw"] for r in raws) == ["JS", "Javascript"]


def test_two_stints_at_same_company_are_two_relationships(neo4j_test_store):
    """关系 CREATE：同一人在同一家公司的两段经历不能被合并覆盖。"""
    write_resume(
        neo4j_test_store,
        900001,
        [_job("后端工程师", "2018-07", "2020-06"), _job("架构师", "2022-03", None)],
    )

    assert _q(neo4j_test_store, "MATCH (c:Company) RETURN count(c) AS n") == [{"n": 1}]
    rels = _q(
        neo4j_test_store,
        "MATCH (:Candidate)-[r:WORKED_AT]->(:Company) "
        "RETURN r.position AS position, r.start_date AS start, r.end_date AS end "
        "ORDER BY r.start_date",
    )
    assert rels == [
        {"position": "后端工程师", "start": "2018-07", "end": "2020-06"},
        {"position": "架构师", "start": "2022-03", "end": None},  # 未提及的字段没有这个属性
    ]


def test_sync_twice_does_not_duplicate_and_drops_stale(neo4j_test_store):
    """先删后建：重复同步数量不翻倍；新抽取结果里没有的旧关系被清掉。"""
    triples = [_skill("Python"), _skill("Redis")]
    write_resume(neo4j_test_store, 900001, triples)
    write_resume(neo4j_test_store, 900001, triples)
    count = "MATCH (:Candidate {resume_id: 900001})-[r]->() RETURN count(r) AS n"
    assert _q(neo4j_test_store, count) == [{"n": 2}]

    write_resume(neo4j_test_store, 900001, [_skill("Python"), _skill("Go")])
    skills = _q(
        neo4j_test_store,
        "MATCH (:Candidate {resume_id: 900001})-[:HAS_SKILL]->(s:Skill) RETURN s.name AS n",
    )
    assert sorted(s["n"] for s in skills) == ["Go", "Python"]  # Redis 已清除
    # 共享节点保留：Redis 节点本身还在，只是候选人不再连它
    assert {"n": "Redis"} in _q(neo4j_test_store, "MATCH (s:Skill) RETURN s.name AS n")


def test_replace_does_not_touch_other_candidates(neo4j_test_store):
    write_resume(neo4j_test_store, 900001, [_skill("Python")])
    write_resume(neo4j_test_store, 900002, [_skill("Python")])
    write_resume(neo4j_test_store, 900001, [_skill("Go")])

    rows = _q(
        neo4j_test_store,
        "MATCH (c:Candidate)-[:HAS_SKILL]->(s:Skill) "
        "RETURN c.resume_id AS c, s.name AS s ORDER BY c, s",
    )
    assert rows == [
        {"c": 900001, "s": "Go"},
        {"c": 900002, "s": "Python"},
    ]


def test_failure_mid_transaction_rolls_back(neo4j_test_store):
    """事务：中途出错，旧关系还在（整体回滚），异常要抛出来而不是被吞。"""
    write_resume(neo4j_test_store, 900001, [_skill("Python"), _skill("Redis")])

    good = build_write_query(to_resume_triple(900001, _skill("Go")))
    broken = ("THIS IS NOT CYPHER", {})
    with pytest.raises(Neo4jError):
        neo4j_test_store.execute_in_transaction([build_delete_query(900001), good, broken])

    skills = _q(
        neo4j_test_store,
        "MATCH (:Candidate {resume_id: 900001})-[:HAS_SKILL]->(s:Skill) RETURN s.name AS n",
    )
    assert sorted(s["n"] for s in skills) == ["Python", "Redis"]  # 删除没生效，Go 也没写入


def test_empty_triples_does_not_wipe_existing(neo4j_test_store):
    """抽取为空（失败/没抽到）不能清空已有数据。"""
    write_resume(neo4j_test_store, 900001, [_skill("Python")])
    assert write_resume(neo4j_test_store, 900001, []) == 0
    assert _q(neo4j_test_store, "MATCH (:Candidate)-[r:HAS_SKILL]->() RETURN count(r) AS n") == [{"n": 1}]


def test_props_syntax_valid_on_real_neo4j(neo4j_test_store):
    """SET r += $props 在 5.26 上合法，且未提及的字段不会变成 null 属性。"""
    write_resume(neo4j_test_store, 900001, [_skill("Python", snippet="熟练使用 Python")])
    rel = _q(neo4j_test_store, "MATCH ()-[r:HAS_SKILL]->() RETURN properties(r) AS p")[0]["p"]
    assert rel == {"raw_name": "Python", "context_snippet": "熟练使用 Python"}
