from graph_service.models.extraction import ExtractedTriple, ResumeTriple
from graph_service.services.entity_normalizer import canonicalize


def to_triple(candidate_id: str, t: ExtractedTriple) -> ResumeTriple:
    """给 LLM 抽取的三元组补上头实体（候选人）。"""
    return ResumeTriple(head_id=candidate_id, **t.model_dump())


def build_triple_query(triple: ResumeTriple) -> tuple[str, dict]:
    """生成写入一条三元组的 Cypher 语句和参数（不连数据库）。

    安全：拼进语句的只有 head_type / tail_type / relation，它们都是 Literal 白名单，
    且来自已通过校验的 ResumeTriple；其余外部内容一律走参数。
    """
    name = canonicalize(triple.tail_type, triple.tail_name)

    raw_props = {
        "raw_name": triple.tail_name,
        "context_snippet": triple.context_snippet,
        "position": triple.position,
        "major": triple.major,
        "start_date": triple.start_date,
        "end_date": triple.end_date,
    }
    props = {k: v for k, v in raw_props.items() if v is not None}

    query = (
        f"MERGE (c:{triple.head_type} {{candidate_id: $candidate_id}})\n"
        f"MERGE (t:{triple.tail_type} {{name: $name}})\n"
        f"MERGE (c)-[r:{triple.relation}]->(t)\n"
        "SET r += $props"
    )
    params = {
        "candidate_id": triple.head_id,
        "name": name,
        "props": props,
    }
    return query, params
