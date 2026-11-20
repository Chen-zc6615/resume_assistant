from graph_service.models.extraction import RELATION_TAIL, ExtractedTriple, ResumeTriple
from graph_service.services.entity_normalizer import canonicalize


def to_resume_triple(resume_id: int, t: ExtractedTriple) -> ResumeTriple:
    """给 LLM 抽取的三元组补上头实体（候选人）。"""
    return ResumeTriple(resume_id=resume_id, **t.model_dump())


def build_write_query(triple: ResumeTriple) -> tuple[str, dict]:
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
        f"MERGE (c:{triple.head_type} {{resume_id: $resume_id}})\n"
        f"MERGE (t:{triple.tail_type} {{name: $name}})\n"
        f"CREATE (c)-[r:{triple.relation}]->(t)\n"
        "SET r += $props"
    )
    params = {
        "resume_id": triple.resume_id,
        "name": name,
        "props": props,
    }
    return query, params


def build_delete_query(resume_id: int) -> tuple[str, dict]:
    rel_types = "|".join(RELATION_TAIL)
    query = (
        f"MATCH (c:Candidate {{resume_id: $resume_id}})-[r:{rel_types}]->()\n"
        "DELETE r"
    )
    params = {
        "resume_id": resume_id,
    }
    return query, params


def write_resume(store, resume_id: int, triples: list[ExtractedTriple]) -> int:
    """整批替换：先删该候选人旧关系，再按本次抽取结果重建，二者在同一个事务里。

    顺序不能反：DELETE 分不出新旧，先建后删会把新关系一并删掉。
    triples 为空时不做任何事：抽取失败或没抽到东西，不应清空候选人已有的图数据
    （信息不足不等于没有）。返回写入的三元组条数。
    """
    if not triples:
        return 0
    queries = [build_delete_query(resume_id)]
    for t in triples:
        queries.append(build_write_query(to_resume_triple(resume_id, t)))
    store.execute_in_transaction(queries)
    return len(triples)

