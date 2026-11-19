import pytest


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
