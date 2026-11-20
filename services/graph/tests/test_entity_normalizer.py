from graph_service.services.entity_normalizer import (
    _clean,
    _lookup_alias,
    _match_key,
    _strip_brackets,
    _strip_company_suffix,
    _strip_english_suffix,
    canonicalize,
)


def test_clean_strips_spaces():
    assert _clean(" SpaceX ") == "SpaceX"


def test_clean_fullwidth_to_halfwidth():
    assert _clean("腾讯科技（深圳）") == "腾讯科技(深圳)"


def test_clean_collapses_spaces():
    assert _clean("Tsinghua   University") == "Tsinghua University"


def test_strip_brackets():
    assert _strip_brackets("腾讯科技(深圳)有限公司") == "腾讯科技有限公司"


def test_strip_company_suffix():
    assert _strip_company_suffix("腾讯科技有限公司") == "腾讯科技"


def test_strip_company_suffix_long_first():
    assert _strip_company_suffix("腾讯科技股份有限公司") == "腾讯科技"


def test_strip_company_suffix_no_suffix():
    assert _strip_company_suffix("腾讯科技") == "腾讯科技"


def test_strip_company_suffix_all_suffix():
    assert _strip_company_suffix("股份有限公司") == "股份有限公司"


def test_strip_english_suffix():
    assert _strip_english_suffix("Acme Ltd") == "Acme"
    assert _strip_english_suffix("Acme LTD") == "Acme"
    assert _strip_english_suffix("Acme Inc.") == "Acme"
    assert _strip_english_suffix("Acme Co., Ltd.") == "Acme"
    assert _strip_english_suffix("Acme, Ltd.") == "Acme"


def test_strip_english_suffix_keeps_case_and_word_boundary():
    assert _strip_english_suffix("OpenAI Inc") == "OpenAI"
    assert _strip_english_suffix("Zinc") == "Zinc"
    assert _strip_english_suffix("Ltd") == "Ltd"


def test_match_key_company_chinese():
    assert _match_key("Company", "腾讯科技(深圳)有限公司") == "腾讯科技"


def test_match_key_company_english():
    assert _match_key("Company", "Acme Co., Ltd.") == "acme"


def test_match_key_school():
    assert _match_key("School", "Tsinghua University") == "tsinghuauniversity"


def test_match_key_skill():
    assert _match_key("Skill", "Machine Learning") == "machinelearning"


def test_lookup_alias_hit():
    assert _lookup_alias("School", "tsinghuauniversity") == "清华大学"
    assert _lookup_alias("School", "清华") == "清华大学"


def test_lookup_alias_miss():
    assert _lookup_alias("School", "不存在") is None


def test_lookup_alias_unknown_type():
    assert _lookup_alias("Foo", "tencent") is None


def test_lookup_alias_empty_key():
    assert _lookup_alias("Company", "") is None


def test_lookup_alias_type_isolated():
    # 同一把钥匙在别的类型下不应命中
    assert _lookup_alias("Skill", "tencent") is None


def test_canonicalize_hit():
    assert canonicalize("School", "Tsinghua  University") == "清华大学"


def test_canonicalize_miss_keeps_cleaned_name():
    assert canonicalize("Skill", "Rust") == "Rust"


def test_canonicalize_empty_key_not_used_as_name():
    assert canonicalize("Company", "(北京)") == "(北京)"


def test_canonicalize_does_not_merge_similar():
    assert canonicalize("School", "北京大学医学部") != canonicalize("School", "北京大学")
