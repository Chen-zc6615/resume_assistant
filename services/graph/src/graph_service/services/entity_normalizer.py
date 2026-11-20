import re
import unicodedata


def _clean(raw: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", raw).split())


def _strip_brackets(name: str) -> str:
    return re.sub(r"\([^)]*\)", "", name)


def _strip_company_suffix(name: str) -> str:
    suffixes = ["股份有限公司", "有限公司"]
    for suffix in suffixes:
        if name.endswith(suffix):
            result = name[: -len(suffix)]
            if result:
                return result
            break
    return name


# 英文后缀，已按长度从长到短排好：长的必须在前，否则 "co., ltd." 会先被 "ltd." 抢走
_ENGLISH_SUFFIXES = [
    "co., ltd.",
    "co.,ltd.",
    "co., ltd",
    "co.,ltd",
    "ltd.",
    "ltd",
    "inc.",
    "inc",
    "llc",
    "corp.",
    "corp",
]


def _strip_english_suffix(name: str) -> str:
    lowered = name.lower()  # 只用小写做比较，返回时仍切原字符串，保留原有大小写
    for suffix in _ENGLISH_SUFFIXES:
        # 前面加一个空格：要求后缀是"独立的一个词"，避免 "Zinc" 被剥成 "Z"
        if lowered.endswith(" " + suffix):
            # 多切掉 1 个空格；rstrip 清掉 "Acme," 这类残留的逗号和空格
            result = name[: -(len(suffix) + 1)].rstrip(" ,")
            if result:
                return result
            break
    return name


def _match_key(tail_type: str, cleaned: str) -> str:
    key = cleaned
    if tail_type == "Company":
        key = _strip_brackets(key)
        key = _strip_company_suffix(key)
        key = _strip_english_suffix(key)
    return "".join(key.lower().split())


# 别名字典：key 是匹配键（即 _match_key 的输出），value 是标准名。
# 同一个标准名可以有多条 key。新增条目时，先用 _match_key 算出 key，不要凭感觉写。
_ALIASES: dict[str, dict[str, str]] = {
    "Company": {
        "tencent": "腾讯",
        "腾讯科技": "腾讯",
    },
    "School": {
        "清华": "清华大学",
        "tsinghuauniversity": "清华大学",
        "北大": "北京大学",
        "pku": "北京大学",
        "pekinguniversity": "北京大学",
    },
    "Skill": {
        "js": "JavaScript",
        "javascript": "JavaScript",
        "k8s": "Kubernetes",
        "kubernetes": "Kubernetes",
    },
}


def _lookup_alias(tail_type: str, key: str) -> str | None:
    # 两层都用 get：类型不存在、key 不存在，都只返回 None，不报错
    return _ALIASES.get(tail_type, {}).get(key)


def canonicalize(tail_type: str, raw_name: str) -> str:
    cleaned = _clean(raw_name)
    key = _match_key(tail_type, cleaned)
    alias = _lookup_alias(tail_type, key)
    if alias is not None:
        return alias
    return cleaned
