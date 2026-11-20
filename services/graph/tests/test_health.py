from fastapi.testclient import TestClient
from graph_service.app import create_app


def test_health_ok(fake_store):
    with TestClient(create_app(store=fake_store)) as client:
        r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "healthy", "neo4j": "ok"}


def test_health_neo4j_down(fake_store):
    fake_store.reachable = False
    with TestClient(create_app(store=fake_store)) as client:
        r = client.get("/health")
    assert r.status_code == 503
    assert r.json()["neo4j"] == "unreachable"


def test_lifespan_inits_schema_and_closes(fake_store):
    with TestClient(create_app(store=fake_store)):
        assert fake_store.schema_init
    assert fake_store.closed
