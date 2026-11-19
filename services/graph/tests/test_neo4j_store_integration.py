import pytest
from graph_service.core.config import Settings
from graph_service.db.neo4j_store import UNIQUE_CONSTRAINTS, GraphStore
from pydantic import ValidationError


@pytest.fixture
def real_store():
    try:
        store = GraphStore(Settings())
    except ValidationError as e:
        # 只有"唯一的问题是没填密码"才算环境不具备；其余配置错误必须报红，不能被悄悄跳过
        only_missing_password = all(
            err["loc"] == ("neo4j_password",) and err["type"] == "missing" for err in e.errors()
        )
        if only_missing_password:
            pytest.skip("未配置 NEO4J_PASSWORD（CI 无 .env）")
        raise
    if not store.ping():
        store.close()
        pytest.skip("Neo4j 不可达")
    yield store
    store.close()


def test_init_schema_is_idempotent(real_store):
    assert real_store.init_schema()
    assert real_store.init_schema()
    records, _, _ = real_store._driver.execute_query("SHOW CONSTRAINTS YIELD name RETURN name")
    names = {r["name"] for r in records}
    assert {c[0] for c in UNIQUE_CONSTRAINTS} <= names
