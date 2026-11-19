import logging

from neo4j import Driver, GraphDatabase
from neo4j.exceptions import DriverError, Neo4jError

from graph_service.core.config import Settings

logger = logging.getLogger(__name__)

# (约束名, Label, 唯一键)：对应 README 图模型里的"唯一键"一列
UNIQUE_CONSTRAINTS: tuple[tuple[str, str, str], ...] = (
    ("document_doc_id", "Document", "doc_id"),
    ("candidate_id", "Candidate", "candidate_id"),
    ("job_id", "Job", "job_id"),
    ("skill_name", "Skill", "name"),
    ("company_name", "Company", "name"),
    ("school_name", "School", "name"),
)


class GraphStore:
    def __init__(self, settings: Settings) -> None:
        self._database = settings.neo4j_database
        self._driver: Driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
            connection_timeout=settings.neo4j_connection_timeout_seconds,
        )

    def close(self) -> None:
        self._driver.close()

    def ping(self) -> bool:
        try:
            self._driver.verify_connectivity()
            return True
        except (DriverError, Neo4jError) as e:
            logger.warning("Neo4j 不可达： %s", e)
            return False

    def init_schema(self) -> bool:
        """创建唯一约束（幂等）。失败只记日志、不抛出，避免 Neo4j 未就绪时服务起不来。"""
        try:
            for name, label, prop in UNIQUE_CONSTRAINTS:
                self._driver.execute_query(
                    f"CREATE CONSTRAINT {name} IF NOT EXISTS "
                    f"FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE",
                    database_=self._database,
                )
        except (DriverError, Neo4jError) as e:
            logger.warning("初始化图约束失败: %s", e)
            return False
        logger.info("图约束就绪：%d 条", len(UNIQUE_CONSTRAINTS))
        return True
