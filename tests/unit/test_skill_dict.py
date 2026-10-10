"""技能字典与别名归一测试。"""

from __future__ import annotations

from src.services.skill_dict import canonical_skill, canonical_skills


def test_alias_to_canonical():
    assert canonical_skill("J2EE") == "Java"
    assert canonical_skill("j2se") == "Java"
    assert canonical_skill("SpringBoot") == "Spring Boot"
    assert canonical_skill("spring 全家桶") == "Spring Boot"
    assert canonical_skill("k8s") == "Kubernetes"
    assert canonical_skill("MYSQL") == "MySQL"
    assert canonical_skill("js") == "JavaScript"


def test_canonical_case_variants():
    assert canonical_skill("SPRING BOOT") == "Spring Boot"
    assert canonical_skill("  spring-boot ") == "Spring Boot"
    assert canonical_skill("Docker容器") == "Docker"


def test_unknown_skill_kept_as_is():
    """未知技能不强行映射（保守原则，不做语义合并）。"""
    assert canonical_skill("Flink CDC") == "Flink CDC"
    assert canonical_skill("关系型数据库性能调优") == "关系型数据库性能调优"


def test_dedupe_and_drop_empty():
    out = canonical_skills(["Java", "J2EE", "  ", "Spring Boot", "springboot", ""])
    assert out == ["Java", "Spring Boot"]
