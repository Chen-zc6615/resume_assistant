import os

import pytest
from graph_service.core.config import Settings
from graph_service.db.graph_store import GraphStore


class FakeStore:
    def __init__(self, reachable: bool = True) -> None:
        self.reachable = reachable
        self.schema_init = False
        self.closed = False

    def ping(self) -> bool:
        return self.reachable

    def init_schema(self) -> bool:
        self.schema_init = True
        return True

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def fake_store() -> FakeStore:
    return FakeStore()


# ---- 图服务集成测试专用库 ----
# 与 compose.yaml 的 neo4j-test 对应：独立容器 + 独立端口 + tmpfs。
# 测试会全库清空，所以只允许连这个端口；地址不对一律拒绝执行，绝不跳过。
TEST_NEO4J_URI = os.environ.get("NEO4J_TEST_URI", "bolt://127.0.0.1:57687")
TEST_NEO4J_PASSWORD = "test-password-123"


@pytest.fixture
def neo4j_test_store():
    if ":57687" not in TEST_NEO4J_URI:
        pytest.exit(
            f"拒绝执行：NEO4J_TEST_URI={TEST_NEO4J_URI} 不是测试库端口 :57687，"
            "集成测试会清空整个图，严禁指向主库。",
            returncode=4,
        )
    store = GraphStore(
        Settings(neo4j_uri=TEST_NEO4J_URI, neo4j_password=TEST_NEO4J_PASSWORD)  # pyright: ignore[reportArgumentType]
    )
    if not store.ping():
        store.close()
        pytest.skip("neo4j-test 不可达：先运行 docker compose up -d neo4j-test")
    store._driver.execute_query("MATCH (n) DETACH DELETE n", database_=store._database)
    store.init_schema()
    yield store
    store._driver.execute_query("MATCH (n) DETACH DELETE n", database_=store._database)
    store.close()
