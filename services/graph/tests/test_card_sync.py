from graph_service.core.config import Settings
from graph_service.services.card_sync import sync_card_to_graph

CARD = "## 专业技能\n\n- Python\n- Redis"

GOOD = (
    '{"triples": [{"relation": "HAS_SKILL", "tail_type": "Skill", '
    '"tail_name": "Python", "context_snippet": "- Python"}]}'
)


class _FakeChat:
    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = []

    def __call__(self, settings, system_prompt, user_prompt, schema=None):
        self.calls.append((system_prompt, user_prompt))
        return self.outputs[len(self.calls) - 1]


class _FakeStore:
    def __init__(self):
        self.transactions = []

    def execute_in_transaction(self, queries):
        self.transactions.append(queries)


def _settings():
    return Settings(
        neo4j_password="test-password-123",
        llm_api_key="k",
        llm_base_url="http://llm.test/v1",
        graph_llm_model="qwen-plus",
    )


def test_happy_path_writes_verified_triples():
    store = _FakeStore()
    report = sync_card_to_graph(_settings(), store, 1001, CARD, chat=_FakeChat(GOOD))

    assert report.extracted == 1
    assert report.rejected == 0
    assert report.written == 1
    assert len(store.transactions) == 1          # 只开了一次事务
    assert len(store.transactions[0]) == 2


# 模型输出两条：Python 在卡片里有，Java 卡片里没有（编造）
MIXED = (
    '{"triples": ['
    '{"relation": "HAS_SKILL", "tail_type": "Skill", "tail_name": "Python", "context_snippet": "- Python"},'
    '{"relation": "HAS_SKILL", "tail_type": "Skill", "tail_name": "Java", "context_snippet": "- Java"}'
    "]}"
)


def test_fabricated_triple_is_rejected_and_not_written():
    store = _FakeStore()
    report = sync_card_to_graph(_settings(), store, 1001, CARD, chat=_FakeChat(MIXED))

    assert report.extracted == 2
    assert report.rejected == 1  # Java 在卡片里找不到依据，被丢弃
    assert report.written == 1  # 只写入 Python
    assert len(store.transactions[0]) == 2  # 1 条删除 + 1 条写入（不是 2 条写入）


# 模型输出只有 Java，卡片里没有
ALL_FAKE = (
    '{"triples": ['
    '{"relation": "HAS_SKILL", "tail_type": "Skill", "tail_name": "Java", "context_snippet": "- Java"}'
    "]}"
)


def test_all_rejected_does_not_touch_graph():
    store = _FakeStore()
    report = sync_card_to_graph(_settings(), store, 1001, CARD, chat=_FakeChat(ALL_FAKE))

    assert report.extracted == 1
    assert report.rejected == 1
    assert report.written == 0
    assert store.transactions == []  # 一次事务都没开：不清空候选人已有的图数据
