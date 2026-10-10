"""技能字典与别名归一。

初筛匹配的漏筛风险主要来自同一技能的不同写法（J2EE / SpringBoot / k8s…）。
归一化阶段入库前统一到 canonical 名；初筛匹配时双方再各归一一次，双保险。

原则（保守，宁可不做也不误并）：
- 只合并明确同义/同一事物的写法变体（大小写、空格、连字符、缩写）；
- 不做语义合并（"关系型数据库" ≠ "MySQL"），语义召回属已裁剪的 C 域。
"""

from __future__ import annotations

import re
import unicodedata

# canonical 名 -> 已知别名/写法变体（匹配一律在 lower+去分隔符形态上进行）
_ALIAS_GROUPS: list[tuple[str, list[str]]] = [
    ("Java", ["java", "j2ee", "j2se", "javase", "javaee", "core java", "java开发"]),
    ("Spring Boot", ["spring boot", "springboot", "spring-boot", "springboot2", "spring全家桶", "spring"]),
    ("Spring Cloud", ["spring cloud", "springcloud", "spring-cloud"]),
    ("MySQL", ["mysql", "my sql", "mysql数据库", "关系型数据库mysql"]),
    ("Redis", ["redis"]),
    ("Kafka", ["kafka", "apachekafka", "apache kafka"]),
    ("RabbitMQ", ["rabbitmq", "rabbit mq"]),
    ("Docker", ["docker", "docker容器"]),
    ("Kubernetes", ["kubernetes", "k8s"]),
    ("JavaScript", ["javascript", "js", "ecmascript", "es6"]),
    ("TypeScript", ["typescript", "ts"]),
    ("Vue", ["vue", "vuejs", "vue.js", "vue2", "vue3"]),
    ("React", ["react", "reactjs", "react.js"]),
    ("Python", ["python", "python3"]),
    ("Linux", ["linux", "linux shell", "shell"]),
    ("Git", ["git", "github", "gitlab"]),
]

def _key(text: str) -> str:
    """归一匹配键：NFKC -> 小写 -> 去除空白/点/连字符/下划线。"""
    t = unicodedata.normalize("NFKC", text or "").lower()
    return re.sub(r"[\s.\-_·]+", "", t)


_ALIAS_MAP: dict[str, str] = {}
for _canonical, _aliases in _ALIAS_GROUPS:
    for _alias in _aliases:
        _ALIAS_MAP[_alias] = _canonical
    # canonical 自身也注册（处理 "SPRING BOOT" 等大小写变体）
    _ALIAS_MAP[_key(_canonical)] = _canonical


def canonical_skill(raw: str) -> str:
    """单个技能 -> canonical 名；未知技能原样保留（strip 后非空才保留）。"""
    text = (raw or "").strip()
    if not text:
        return ""
    key = _key(text)
    return _ALIAS_MAP.get(key, text)


def canonical_skills(raw: list[str]) -> list[str]:
    """技能列表归一 + 去重（保持首次出现顺序）。"""
    seen: set[str] = set()
    out: list[str] = []
    for s in raw:
        c = canonical_skill(s)
        if c and c.lower() not in seen:
            seen.add(c.lower())
            out.append(c)
    return out
