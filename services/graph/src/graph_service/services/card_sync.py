from dataclasses import dataclass

from graph_service.clients.llm_client import chat_json
from graph_service.services.triple_extractor import extract_triples
from graph_service.services.triple_verifier import verify_triples
from graph_service.services.triple_writer import write_resume


@dataclass(frozen=True)
class SyncReport:
    extracted: int      #模型一共抽取多少条
    rejected: int       #核对时丢掉几条
    written: int        #最后写进图中有几条


def sync_card_to_graph(settings, store, resume_id, card_text, chat=chat_json) -> SyncReport:
    extracted = extract_triples(settings, card_text, chat)
    passed, rejected = verify_triples(card_text, extracted)
    written = write_resume(store, resume_id, passed)
    return SyncReport(len(extracted), len(rejected), written)
