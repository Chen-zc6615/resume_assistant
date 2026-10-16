"""全链路集成测试：需求 -> 岗位 -> 上传 -> 解析 -> 归一化(mock LLM) -> 自动分配 -> 按岗初筛 -> 审核入库。

LLM 通过打桩 mock（不打真实 API），验证编排逻辑与状态机流转。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app_service.clients import parser_client
from app_service.services import llm
from fastapi.testclient import TestClient

from tests.conftest import golden

# 归一化 mock：不同简历返回不同候选人（按上传顺序即可，此 mock 恒定返回张三）
MOCK_EXTRACT = {
    "name": "张三",
    "gender": "男",
    "phone": "13800001111",
    "email": "zhangsan@email.com",
    "highest_education": "硕士",
    "graduation_institution": "北京大学",
    "total_work_months": 72,
    "skills": ["Java", "Spring Boot", "MySQL", "Redis"],
    "education_experiences": [
        {
            "school": "北京大学",
            "major": "计算机科学与技术",
            "education_level": "硕士",
            "start_date": "2014-09",
            "end_date": "2017-06",
            "is_current": False,
        }
    ],
    "work_experiences": [
        {
            "company": "字节跳动",
            "position": "高级工程师",
            "start_date": "2021-03",
            "end_date": None,
            "is_current": True,
            "description": "负责核心模块开发",
        }
    ],
    "project_experiences": [],
}


@pytest.fixture()
def mock_llm(monkeypatch):
    """打桩归一化 LLM 与解析 HTTP 客户端（测试不依赖真实模型/解析服务）。"""
    monkeypatch.setattr(
        llm, "chat_json", lambda sys, user: json.dumps(MOCK_EXTRACT, ensure_ascii=False)
    )
    # 解析已迁为独立服务：打桩 HTTP 客户端返回固定文本，验证编排与状态机
    monkeypatch.setattr(
        parser_client,
        "parse_resume_via_service",
        lambda pdf_path: parser_client.ParseResult(
            text="张三 简历 文本（测试打桩）",
            parse_method="stub",
            effective_chars=10,
        ),
    )


@pytest.fixture()
def client():
    from app_service.app import create_app
    from app_service.db.base import Base
    from app_service.db.session import engine
    from app_service.services import pipeline

    with TestClient(create_app()) as c:
        # 每个测试独立数据：清表 + 清内存批次
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        pipeline._batches.clear()
        yield c


def _mk_requirement(client, name="2026Q4 后端招聘", **overrides):
    body = {"requirement_name": name, "created_by": "hr_test"}
    body.update(overrides)
    r = client.post("/api/requirements", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _mk_job(client, requirement_id, **overrides):
    body = {
        "requirement_id": requirement_id,
        "job_name": "Java后端开发工程师",
        "job_jd": "负责后端服务开发",
        "job_min_degree": "本科",
        "job_min_exp_years": 3,
        "job_required_skills": ["Java", "Spring Boot", "MySQL"],
        "job_optional_skills": ["Redis"],
        "bonus_items": [],
        "job_status": 1,
        "job_created_by": "hr_test",
    }
    body.update(overrides)
    r = client.post("/api/jobs", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _upload(client, fn, requirement_id, **form):
    content = Path(golden(fn)).read_bytes()
    r = client.post(
        "/api/resumes/upload",
        files=[("files", (fn, content, "application/pdf"))],
        data={"requirement_id": str(requirement_id), **{k: str(v) for k, v in form.items()}},
    )
    assert r.status_code == 200
    return r.json()


def _wait_batch_done(client, batch_id):
    """轮询批次直至全部处理完。"""
    import time

    for _ in range(120):
        snapshot = client.get(f"/api/parse/{batch_id}/status")
        if snapshot.status_code != 200:
            break
        if snapshot.json()["finished"] >= snapshot.json()["total"]:
            return snapshot.json()
        time.sleep(0.05)
    snapshot = client.get(f"/api/parse/{batch_id}/status").json()
    assert snapshot["finished"] >= snapshot["total"], f"批次未完成: {snapshot}"
    return snapshot


def test_full_pipeline_with_requirement(client, mock_llm):
    """挂需求上传：解析 -> 归一化 -> 自动分配 -> 按岗初筛 -> 状态=待审核。"""
    # 1. 需求 -> 岗位（基准 JD：本科+3年+Java/Spring Boot/MySQL）
    req = _mk_requirement(client)
    job = _mk_job(client, req["requirement_id"])

    # 2. 上传 sample01（文本型），mock 张三技能全命中 -> 自动分配 -> 初筛通过
    resp = _upload(client, "sample01_完美匹配_高分正样本.pdf", req["requirement_id"], hr_id="hr_test")
    assert resp["items"][0]["accepted"] is True
    batch = _wait_batch_done(client, resp["batch_id"])
    assert batch["parse_success"] == 1
    assert batch["normalize_success"] == 1

    resume_id = resp["items"][0]["resume_id"]
    detail = client.get(f"/api/resumes/{resume_id}").json()
    assert detail["status_label"] == "待审核入库", detail["status_label"]
    assert detail["profile"]["name"] == "张三"
    # 需求池 + 岗位组（自动分配）都有留痕
    pool = client.get(f"/api/requirements/{req['requirement_id']}/resumes").json()
    assert [p["resume_id"] for p in pool] == [resume_id]
    group = client.get(f"/api/jobs/{job['job_id']}/resumes").json()
    assert [g["resume_id"] for g in group] == [resume_id]
    assert group[0]["added_by"] == "auto:assignment"
    assert "Java" in group[0]["match_detail"]["required_hits"]
    # failure_reason 为各岗初筛汇总
    assert detail["failure_reason"].startswith("岗位初筛汇总：")

    # 3. HR 审核入库
    ok = client.post(f"/api/resumes/{resume_id}/confirm")
    assert ok.json()["ok"] is True
    detail = client.get(f"/api/resumes/{resume_id}").json()
    assert detail["status_label"] == "已完成"


def test_upload_requires_existing_requirement(client, mock_llm):
    """上传必须挂真实需求：缺参 422 / 不存在 404。"""
    content = Path(golden("sample01_完美匹配_高分正样本.pdf")).read_bytes()
    files = [("files", ("s01.pdf", content, "application/pdf"))]

    missing = client.post("/api/resumes/upload", files=files)
    assert missing.status_code == 422

    not_found = client.post(
        "/api/resumes/upload", files=files, data={"requirement_id": "9999"}
    )
    assert not_found.status_code == 404


def test_duplicate_upload_dedup(client, mock_llm):
    """同一文件重复上传：按 SHA256 去重。"""
    req = _mk_requirement(client)
    first = _upload(client, "sample01_完美匹配_高分正样本.pdf", req["requirement_id"], hr_id="hr_test")
    _wait_batch_done(client, first["batch_id"])
    second = _upload(client, "sample01_完美匹配_高分正样本.pdf", req["requirement_id"], hr_id="hr_test")
    assert second["items"][0]["duplicated"] is True
    assert second["items"][0]["resume_id"] == first["items"][0]["resume_id"]
    # 去重后不应产生新记录
    stats = client.get("/api/resumes/stats").json()
    assert stats["total"] == 1


def test_mixed_upload_duplicated_still_visible_in_batch(client, mock_llm):
    """多份上传含重复：重复简历也出现在批次进度列表（不"少人"）。"""
    req = _mk_requirement(client)
    first = _upload(client, "sample01_完美匹配_高分正样本.pdf", req["requirement_id"], hr_id="hr_test")
    _wait_batch_done(client, first["batch_id"])
    s01_id = first["items"][0]["resume_id"]

    content01 = Path(golden("sample01_完美匹配_高分正样本.pdf")).read_bytes()
    content06 = Path(golden("sample06_复杂排版_双栏简历.pdf")).read_bytes()
    r = client.post(
        "/api/resumes/upload",
        files=[
            ("files", ("again01.pdf", content01, "application/pdf")),
            ("files", ("sample06.pdf", content06, "application/pdf")),
        ],
        data={"hr_id": "hr_test", "requirement_id": str(req["requirement_id"])},
    )
    up = r.json()
    assert up["items"][0]["duplicated"] is True
    batch = _wait_batch_done(client, up["batch_id"])

    # 展示全集：重复项 + 新项都在进度列表里
    assert batch["total"] == 2
    ids = {row["resume_id"] for row in batch["per_resume"]}
    assert ids == {s01_id, s01_id + 1}, ids
    # 重复项立即完成（stage=done），新项正常处理
    stages = {row["resume_id"]: row.get("stage") for row in batch["per_resume"]}
    assert stages[s01_id] == "done"
    # 数据库仍只有 2 条简历记录（去重生效）
    stats = client.get("/api/resumes/stats").json()
    assert stats["total"] == 2


def test_invalid_files_rejected_at_upload(client):
    """S09 加密 + 伪 PDF：上传即拒，返回友好原因。"""
    req = _mk_requirement(client)
    content09 = Path(golden("sample09_加密PDF_异常上传.pdf")).read_bytes()
    r = client.post(
        "/api/resumes/upload",
        files=[
            ("files", ("enc.pdf", content09, "application/pdf")),
            ("files", ("fake.pdf", b"not a pdf", "application/pdf")),
        ],
        data={"requirement_id": str(req["requirement_id"])},
    )
    items = r.json()["items"]
    assert items[0]["accepted"] is False and "加密" in items[0]["reason"]
    assert items[1]["accepted"] is False and "PDF" in items[1]["reason"]


def test_requirement_level_screening_any_job_pass_keeps_resume(client, mock_llm):
    """需求级初筛黄金用例：简历面对需求下所有岗位筛选，
    任一岗位通过即待审核入库，全部岗位都不满足才筛出去。"""
    req = _mk_requirement(client)
    # 岗位A：mock 张三全命中 -> PASS；岗位B（产品经理）：技能不命中 -> REJECT
    _mk_job(client, req["requirement_id"], job_name="Java后端")
    _mk_job(
        client, req["requirement_id"], job_name="产品经理",
        job_required_skills=["Axure", "数据分析"],
    )

    up = _upload(client, "sample01_完美匹配_高分正样本.pdf", req["requirement_id"], hr_id="hr_test")
    _wait_batch_done(client, up["batch_id"])
    resume_id = up["items"][0]["resume_id"]

    # 全量分配：两个岗位组都有这份简历（技能不命中也进组参与判定）
    for job_id in (1, 2):
        group = client.get(f"/api/jobs/{job_id}/resumes").json()
        assert [g["resume_id"] for g in group] == [resume_id]

    # 各岗独立 run：A=PASS / B=REJECT(缺技能)；归并取最优 -> 待审核入库
    runs = {r["job_id"]: r for r in client.get("/api/screening/runs").json()}
    assert runs[1]["passed"] == 1
    assert runs[2]["rejected"] == 1
    detail = client.get(f"/api/resumes/{resume_id}").json()
    assert detail["status_label"] == "待审核入库", "任一岗通过即留下，不因其他岗被筛出去"
    assert "产品经理=不通过" in detail["failure_reason"]
    assert "Java后端=通过" in detail["failure_reason"]


def test_reassign_after_new_job_added(client, mock_llm):
    """先上传后建岗：新岗位组为空，reassign 一键补分配并初筛。"""
    req = _mk_requirement(client)
    _mk_job(client, req["requirement_id"])  # Java 岗
    up = _upload(client, "sample01_完美匹配_高分正样本.pdf", req["requirement_id"], hr_id="hr_test")
    _wait_batch_done(client, up["batch_id"])
    resume_id = up["items"][0]["resume_id"]

    # 上传后新增产品经理岗：组为空，初筛 400
    pm = _mk_job(client, req["requirement_id"], job_name="产品经理", job_required_skills=["Axure"])
    empty = client.post(f"/api/jobs/{pm['job_id']}/screen")
    assert empty.status_code == 400

    # 重新分配并初筛：池内可筛简历进入新岗位组并跑 run
    r = client.post(f"/api/requirements/{req['requirement_id']}/reassign")
    assert r.status_code == 200, r.text
    assert r.json()["assigned_jobs"] >= 1

    group = client.get(f"/api/jobs/{pm['job_id']}/resumes").json()
    assert [g["resume_id"] for g in group] == [resume_id]
    # 产品岗初筛已跑（张三缺 Axure -> REJECT），但 Java 岗通过在先，简历不被筛出去
    detail = client.get(f"/api/resumes/{resume_id}").json()
    assert detail["status_label"] == "待审核入库"


def test_screening_run_crud(client, mock_llm):
    """显式筛选任务：模板 -> 执行（组内重筛）-> 三态结果 -> CSV 导出。

    不传 resume_ids 时筛模板关联岗位组内的简历（自动初筛后简历已流转
    到通过/不通过态，模板执行 = 组内按模板规则重筛并刷新归并结果）。
    """
    req = _mk_requirement(client)
    _mk_job(client, req["requirement_id"])  # S01 技能全命中 -> 自动分配进组并初筛通过
    up = _upload(client, "sample01_完美匹配_高分正样本.pdf", req["requirement_id"], hr_id="hr_test")
    _wait_batch_done(client, up["batch_id"])
    resume_id = up["items"][0]["resume_id"]
    assert client.get(f"/api/resumes/{resume_id}").json()["status_label"] == "待审核入库"

    tpl = client.post(
        "/api/screening/templates",
        json={
            "template_name": "Java基础模板",
            "job_id": 1,
            "rules": {"min_degree": "本科", "min_exp_years": 3, "required_skills": ["Java", "Spring Boot"]},
        },
    )
    assert tpl.status_code == 200, tpl.text
    run = client.post("/api/screening/runs", json={"template_id": tpl.json()["template_id"]})
    assert run.status_code == 200, run.text
    run_data = run.json()
    assert run_data["total"] == 1  # 组内 1 份，而不是全局 0 份
    assert run_data["passed"] >= 1  # mock 张三满足条件

    results = client.get(f"/api/screening/runs/{run_data['run_id']}/results").json()
    assert results[0]["result"] == "PASS"
    assert results[0]["name"] == "张三"

    csv_resp = client.get(f"/api/screening/runs/{run_data['run_id']}/export.csv")
    assert csv_resp.status_code == 200
    assert "张三" in csv_resp.text

    # 模板规则收紧（博士）后重筛：组内简历状态被刷新为不通过（同岗取最新 run）
    tpl2 = client.post(
        "/api/screening/templates",
        json={
            "template_name": "收紧模板",
            "job_id": 1,
            "rules": {"min_degree": "博士", "min_exp_years": 10, "required_skills": ["Rust"]},
        },
    )
    run2 = client.post("/api/screening/runs", json={"template_id": tpl2.json()["template_id"]})
    assert run2.json()["rejected"] == 1
    detail = client.get(f"/api/resumes/{resume_id}").json()
    assert detail["status_label"] == "初筛不通过"
    assert "博士" in detail["failure_reason"]


def test_review_edit_and_complete(client, mock_llm):
    """人工审核：编辑归一化字段后入库。"""
    req = _mk_requirement(client)
    up = _upload(client, "sample06_复杂排版_双栏简历.pdf", req["requirement_id"], hr_id="hr_test")
    _wait_batch_done(client, up["batch_id"])
    resume_id = up["items"][0]["resume_id"]
    patched = client.patch(
        f"/api/resumes/{resume_id}/profile",
        json={
            "name": "张三",
            "phone": "13900002222",
            "email": "zhangsan@new.com",
            "highest_education": "硕士",
            "graduation_institution": "北京大学",
            "total_work_months": 80,
            "skills": ["Java", "Redis"],
        },
    )
    assert patched.status_code == 200, patched.text
    client.post(f"/api/resumes/{resume_id}/confirm")
    detail = client.get(f"/api/resumes/{resume_id}").json()
    assert detail["status_label"] == "已完成"
    assert detail["profile"]["phone"] == "13900002222"


def test_manual_reject_requires_reason(client, mock_llm):
    """人工筛除：原因必填留痕。"""
    req = _mk_requirement(client)
    up = _upload(client, "sample06_复杂排版_双栏简历.pdf", req["requirement_id"], hr_id="hr_test")
    _wait_batch_done(client, up["batch_id"])
    resume_id = up["items"][0]["resume_id"]

    # 空原因 -> 422（NonEmptyText 拦截）
    bad = client.post(f"/api/resumes/{resume_id}/reject", json={"reason": "   "})
    assert bad.status_code == 422

    ok = client.post(f"/api/resumes/{resume_id}/reject", json={"reason": "工作经历与岗位方向不符"})
    assert ok.status_code == 200
    detail = client.get(f"/api/resumes/{resume_id}").json()
    assert detail["status_label"] == "初筛不通过"
    assert "人工筛除：工作经历与岗位方向不符" == detail["failure_reason"]


def test_multi_job_merge_best_result_wins(client, mock_llm):
    """业务流核心：全量分配 -> 多岗初筛 -> 结果归并（PASS 不被其他岗 REJECT 降级）。"""
    req = _mk_requirement(client)
    # 岗位A：S01 全命中 -> 初筛 PASS；岗位B：博士+Rust -> 初筛 REJECT
    job_a = _mk_job(client, req["requirement_id"], job_name="Java岗")
    job_b = _mk_job(
        client, req["requirement_id"], job_name="资深专家岗",
        job_min_degree="博士", job_min_exp_years=10, job_required_skills=["Rust"],
    )

    up = _upload(client, "sample01_完美匹配_高分正样本.pdf", req["requirement_id"], hr_id="hr_test")
    _wait_batch_done(client, up["batch_id"])
    s01_id = up["items"][0]["resume_id"]
    assert client.get(f"/api/resumes/{s01_id}").json()["status_label"] == "待审核入库"

    # 全量分配：A、B 两组都有 S01（B 技能不命中也参与判定 -> REJECT，但不降级 A 的 PASS）
    for job in (job_a, job_b):
        group = client.get(f"/api/jobs/{job['job_id']}/resumes").json()
        assert [g["resume_id"] for g in group] == [s01_id]

    detail = client.get(f"/api/resumes/{s01_id}").json()
    assert detail["status_label"] == "待审核入库", "多岗最优结果：B=REJECT 不得降级 A=PASS"
    assert detail["failure_reason"].startswith("岗位初筛汇总：")
    assert "不通过" in detail["failure_reason"] and "通过" in detail["failure_reason"]

    # 重复分入幂等跳过
    r2 = client.post(f"/api/jobs/{job_a['job_id']}/resumes", json={"resume_ids": [s01_id]})
    assert r2.json()["added"] == 0 and r2.json()["skipped_duplicated"] == 1

    # run 列表带需求/岗位名冗余展示字段
    runs = client.get("/api/screening/runs").json()
    named = {r["job_name"] for r in runs}
    assert {"Java岗", "资深专家岗"} <= named

    # 移出 B 组后重筛 A：B 的历史 REJECT 不再计入归并（只统计在组岗位）
    rm = client.delete(f"/api/jobs/{job_b['job_id']}/resumes/{s01_id}")
    assert rm.json()["ok"] is True
    re_run = client.post(f"/api/jobs/{job_a['job_id']}/screen")
    assert re_run.status_code == 200
    detail = client.get(f"/api/resumes/{s01_id}").json()
    assert detail["status_label"] == "待审核入库"
    assert "资深专家岗" not in detail["failure_reason"]


def test_empty_group_screen_rejected(client, mock_llm):
    """空组岗位执行初筛 -> 400 友好拒绝。"""
    req = _mk_requirement(client)
    job = _mk_job(client, req["requirement_id"], job_name="空岗", job_required_skills=["Go"])
    empty = client.post(f"/api/jobs/{job['job_id']}/screen")
    assert empty.status_code == 400


def test_delete_resume_cascades_groups_and_file(client, mock_llm):
    """删除简历：需求池/岗位组/初筛结果级联清理 + 磁盘文件移除（外键约束不炸）。

    回归：上传挂需求后简历必进 requirement_resume_groups，
    关联行不清理会触发 FOREIGN KEY 约束失败（500）。
    """
    import hashlib

    from app_service.core.config import get_settings

    req = _mk_requirement(client)
    _mk_job(client, req["requirement_id"])
    up = _upload(client, "sample01_完美匹配_高分正样本.pdf", req["requirement_id"], hr_id="hr_test")
    _wait_batch_done(client, up["batch_id"])
    resume_id = up["items"][0]["resume_id"]

    # 前置：已进需求池 + 岗位组（自动分配）+ 产生初筛结果
    assert len(client.get(f"/api/requirements/{req['requirement_id']}/resumes").json()) == 1
    assert len(client.get("/api/jobs/1/resumes").json()) == 1

    # 按本份文件的 sha256 精确断言（uploads 目录为全部测试共享，不能按总数断言）
    sha = hashlib.sha256(Path(golden("sample01_完美匹配_高分正样本.pdf")).read_bytes()).hexdigest()
    pdf_path = get_settings().upload_dir / f"{sha}.pdf"
    assert pdf_path.exists()

    # 删除成功（200 而非外键 500）
    r = client.delete(f"/api/resumes/{resume_id}")
    assert r.status_code == 200, r.text

    # 记录、池、组、文件全部清理
    assert client.get(f"/api/resumes/{resume_id}").status_code == 404
    assert client.get(f"/api/requirements/{req['requirement_id']}/resumes").json() == []
    assert client.get("/api/jobs/1/resumes").json() == []
    assert client.get("/api/resumes/stats").json()["total"] == 0
    assert not pdf_path.exists()

    # 已无简历：筛选 run 的结果也一并清掉（resume cascade），runs 列表仍可查询
    runs = client.get("/api/screening/runs").json()
    for run in runs:
        assert client.get(f"/api/screening/runs/{run['run_id']}/results").json() == []


def test_rejecting_job_first_does_not_eliminate_resume(client, mock_llm):
    """红线回归：批次内多岗依次初筛，第一岗 REJECT 的中间出局态
    不得剥夺后续岗位的判定机会——满足的第二岗必须把简历带回归并。"""
    req = _mk_requirement(client)
    # 先建专家岗（博士门槛 -> REJECT，先执行），再建 Java 岗（满足 -> PASS，后执行）
    _mk_job(
        client, req["requirement_id"], job_name="资深专家岗",
        job_min_degree="博士", job_required_skills=["Java"],
    )
    _mk_job(client, req["requirement_id"], job_name="Java岗")

    up = _upload(client, "sample01_完美匹配_高分正样本.pdf", req["requirement_id"], hr_id="hr_test")
    _wait_batch_done(client, up["batch_id"])
    resume_id = up["items"][0]["resume_id"]

    # 两个岗位的 run 都筛到了这份简历
    runs = {r["job_name"]: r for r in client.get("/api/screening/runs").json()}
    assert runs["资深专家岗"]["rejected"] == 1
    assert runs["Java岗"]["passed"] == 1, "第一岗 REJECT 后简历不得被排除出第二岗筛选"

    # 归并：任一岗通过 -> 待审核入库（不因专家岗被筛出去）
    detail = client.get(f"/api/resumes/{resume_id}").json()
    assert detail["status_label"] == "待审核入库"
    assert "资深专家岗=不通过" in detail["failure_reason"]
    assert "Java岗=通过" in detail["failure_reason"]


def test_rejected_resume_excluded_from_subsequent_runs(client, mock_llm):
    """初筛不通过的简历不再进入任何后续筛选（模板执行 / 按组重筛均排除）。

    回归：出局（status=3）与已入库（status=4）不参与筛选，
    组内全部出局时按组重筛友好拒绝（400）。
    """
    req = _mk_requirement(client)
    # 博士门槛：S01（硕士）学历一票否决 -> 自动初筛 REJECT
    job = _mk_job(
        client, req["requirement_id"], job_min_degree="博士",
        job_required_skills=["Java", "Spring Boot", "MySQL"],
    )
    up = _upload(client, "sample01_完美匹配_高分正样本.pdf", req["requirement_id"], hr_id="hr_test")
    _wait_batch_done(client, up["batch_id"])
    resume_id = up["items"][0]["resume_id"]
    assert client.get(f"/api/resumes/{resume_id}").json()["status_label"] == "初筛不通过"

    # 组内仅这份出局简历：模板执行（同岗位）不捞它 -> total=0
    tpl = client.post(
        "/api/screening/templates",
        json={
            "template_name": "放宽模板",
            "job_id": job["job_id"],
            "rules": {"min_degree": "本科", "min_exp_years": 3, "required_skills": ["Java"]},
        },
    )
    run = client.post("/api/screening/runs", json={"template_id": tpl.json()["template_id"]})
    assert run.status_code == 200
    assert run.json()["total"] == 0, "出局简历不应再进入模板筛选"

    # 按组重筛：组内全部出局 -> 400 友好拒绝
    r = client.post(f"/api/jobs/{job['job_id']}/screen")
    assert r.status_code == 400
    assert "出局" in r.json()["detail"]


def test_restore_rejected_resume(client, mock_llm):
    """恢复待筛：初筛不通过 -> 待初筛，规则修正后重新筛选可翻案；终态不可恢复。"""
    req = _mk_requirement(client)
    job = _mk_job(
        client, req["requirement_id"], job_min_degree="博士",
        job_required_skills=["Java", "Spring Boot", "MySQL"],
    )
    up = _upload(client, "sample01_完美匹配_高分正样本.pdf", req["requirement_id"], hr_id="hr_test")
    _wait_batch_done(client, up["batch_id"])
    resume_id = up["items"][0]["resume_id"]
    assert client.get(f"/api/resumes/{resume_id}").json()["status_label"] == "初筛不通过"

    # 恢复 -> 待初筛
    r = client.post(f"/api/resumes/{resume_id}/restore")
    assert r.status_code == 200
    detail = client.get(f"/api/resumes/{resume_id}").json()
    assert detail["status_label"] == "待初筛"
    assert detail["failure_reason"] is None

    # 岗位门槛修正为本科后重筛（组保留，重筛即刷新）
    client.put(
        f"/api/jobs/{job['job_id']}",
        json={
            "requirement_id": req["requirement_id"],
            "job_name": job["job_name"], "job_jd": "jd", "job_min_degree": "本科",
            "job_min_exp_years": 3, "job_required_skills": ["Java", "Spring Boot", "MySQL"],
            "job_optional_skills": [], "job_status": 1,
        },
    )
    run = client.post(f"/api/jobs/{job['job_id']}/screen")
    assert run.status_code == 200
    assert run.json()["passed"] == 1
    assert client.get(f"/api/resumes/{resume_id}").json()["status_label"] == "待审核入库"

    # 入库后为终态：不可恢复
    client.post(f"/api/resumes/{resume_id}/confirm")
    bad = client.post(f"/api/resumes/{resume_id}/restore")
    assert bad.status_code == 400


def test_confirm_marks_passed_job_names(client, mock_llm):
    """确认入库标记通过岗位：已完成简历可见"已入库（岗位：Java岗）"。"""
    req = _mk_requirement(client)
    _mk_job(
        client, req["requirement_id"], job_name="资深专家岗",
        job_min_degree="博士", job_required_skills=["Java"],
    )
    _mk_job(client, req["requirement_id"], job_name="Java岗")
    up = _upload(client, "sample01_完美匹配_高分正样本.pdf", req["requirement_id"], hr_id="hr_test")
    _wait_batch_done(client, up["batch_id"])
    resume_id = up["items"][0]["resume_id"]
    assert client.get(f"/api/resumes/{resume_id}").json()["status_label"] == "待审核入库"

    client.post(f"/api/resumes/{resume_id}/confirm")
    detail = client.get(f"/api/resumes/{resume_id}").json()
    assert detail["status_label"] == "已完成"
    assert detail["failure_reason"] == "已入库（岗位：Java岗）"


def test_delete_template_keeps_runs(client, mock_llm):
    """删除筛选模板：历史 run 与结果保留（template_id 置空，快照仍可审计）。"""
    req = _mk_requirement(client)
    _mk_job(client, req["requirement_id"], job_name="Java岗", job_required_skills=["Java"])
    up = _upload(client, "sample01_完美匹配_高分正样本.pdf", req["requirement_id"], hr_id="hr_test")
    _wait_batch_done(client, up["batch_id"])

    tpl = client.post(
        "/api/screening/templates",
        json={"template_name": "T1", "job_id": 1, "rules": {"min_degree": "本科", "required_skills": ["Java"]}},
    ).json()
    run = client.post("/api/screening/runs", json={"template_id": tpl["template_id"]}).json()
    assert run["total"] >= 1

    ok = client.delete(f"/api/screening/templates/{tpl['template_id']}")
    assert ok.status_code == 200
    assert client.get("/api/screening/templates").json() == []

    # run 保留且可查（template_id 已置空，结果与快照完整）
    runs = client.get("/api/screening/runs").json()
    kept = next(r for r in runs if r["run_id"] == run["run_id"])
    assert kept["template_id"] is None
    results = client.get(f"/api/screening/runs/{run['run_id']}/results").json()
    assert results

    # 再删一次 -> 404
    assert client.delete(f"/api/screening/templates/{tpl['template_id']}").status_code == 404


def test_list_runs_limit(client, mock_llm):
    """任务列表默认最近 10 条（limit 参数可调）。"""
    req = _mk_requirement(client)
    _mk_job(client, req["requirement_id"], job_name="Go岗", job_required_skills=["Go"])
    up = _upload(client, "sample01_完美匹配_高分正样本.pdf", req["requirement_id"], hr_id="hr_test")
    _wait_batch_done(client, up["batch_id"])

    for _ in range(3):
        tpl = client.post(
            "/api/screening/templates",
            json={"template_name": "T", "job_id": 1, "rules": {"min_degree": "本科", "required_skills": ["Java"]}},
        ).json()
        client.post("/api/screening/runs", json={"template_id": tpl["template_id"]})

    assert len(client.get("/api/screening/runs?limit=2").json()) == 2
    assert len(client.get("/api/screening/runs").json()) <= 10


def test_delete_requirement_cascades(client, mock_llm):
    """删除需求：岗位/模板/筛选任务/结果/分组/需求池级联清理（外键不炸）。"""
    req = _mk_requirement(client)
    _mk_job(client, req["requirement_id"], job_name="资深专家岗", job_min_degree="博士")
    _mk_job(client, req["requirement_id"], job_name="Java岗")
    up = _upload(client, "sample01_完美匹配_高分正样本.pdf", req["requirement_id"], hr_id="hr_test")
    _wait_batch_done(client, up["batch_id"])
    resume_id = up["items"][0]["resume_id"]
    # 前置：池/组/run 均有数据
    assert len(client.get(f"/api/requirements/{req['requirement_id']}/resumes").json()) == 1
    runs_before = len(client.get("/api/screening/runs").json())
    assert runs_before >= 2

    ok = client.delete(f"/api/requirements/{req['requirement_id']}")
    assert ok.status_code == 200, ok.text

    assert client.get("/api/requirements").json() == []
    assert client.get("/api/jobs").json() == []
    assert client.get("/api/screening/runs").json() == []
    # 简历记录本身保留（仅脱离需求），状态不再有该需求的初筛汇总
    detail = client.get(f"/api/resumes/{resume_id}").json()
    assert detail["resume_id"] == resume_id
    pool = client.get(f"/api/requirements/{req['requirement_id']}/resumes")
    assert pool.status_code == 404


def test_talent_flow_interview_and_pool(client, mock_llm):
    """人才域：标记面试状态 -> 发起邀约（自动置已邀请）-> 沉淀入候选库（幂等 409）-> 移出。"""
    req = _mk_requirement(client, dept="电商事业部", deadline="2026-12-31")
    job = _mk_job(client, req["requirement_id"], job_code="A岗", headcount=2, major="计算机")
    up = _upload(client, "sample01_完美匹配_高分正样本.pdf", req["requirement_id"], hr_id="hr_test")
    _wait_batch_done(client, up["batch_id"])
    rid = up["items"][0]["resume_id"]
    assert client.get(f"/api/resumes/{rid}").json()["status_label"] == "待审核入库"

    # 面试状态标记（brief 透出）
    ok = client.post(f"/api/resumes/{rid}/interview-status", json={"status": 0})
    assert ok.json()["interview_status"] == 0
    assert client.get(f"/api/resumes/{rid}").json()["interview_status"] == 0

    # 发起邀约 -> 自动置「已邀请面试」，列表可按简历查
    inv = client.post(
        "/api/talent/interviews",
        json={
            "resume_id": rid, "job_id": job["job_id"],
            "interview_time": "2026-10-12 14:30", "way": "线上技术面",
            "interviewer": "李婷、赵工", "note": "准备项目介绍",
        },
    )
    assert inv.status_code == 200, inv.text
    assert inv.json()["job_name"] == "Java后端开发工程师"
    assert client.get(f"/api/resumes/{rid}").json()["interview_status"] == 1
    listed = client.get(f"/api/talent/interviews?resume_id={rid}").json()
    assert len(listed) == 1 and listed[0]["interviewer"] == "李婷、赵工"

    # 沉淀入候选库（带来源），重复入库 409
    pool = client.post(
        f"/api/talent/pool?resume_id={rid}",
        json={"source_requirement_id": req["requirement_id"], "source_job_id": job["job_id"], "note": "暂不匹配，储备"},
    )
    assert pool.status_code == 200, pool.text
    assert pool.json()["source_requirement_name"] == req["requirement_name"]
    assert pool.json()["resume"]["resume_id"] == rid
    dup = client.post(f"/api/talent/pool?resume_id={rid}", json={})
    assert dup.status_code == 409

    entries = client.get("/api/talent/pool").json()
    assert len(entries) == 1

    # 移出沉淀库
    rm = client.delete(f"/api/talent/pool/{entries[0]['pool_id']}")
    assert rm.json()["ok"] is True
    assert client.get("/api/talent/pool").json() == []


def test_auto_screening_creates_run_with_rules_snapshot(client, mock_llm):
    """自动初筛落 filter_runs 留痕，规则快照固化（岗位事后修改不影响历史）。"""
    req = _mk_requirement(client)
    job = _mk_job(client, req["requirement_id"])
    up = _upload(client, "sample01_完美匹配_高分正样本.pdf", req["requirement_id"], hr_id="hr_test")
    _wait_batch_done(client, up["batch_id"])

    runs = client.get("/api/screening/runs").json()
    assert runs, "自动初筛应产生 filter_run 记录"
    run = runs[0]
    assert run["passed"] >= 1
    # 岗位事后被改，不影响快照
    client.put(
        f"/api/jobs/{job['job_id']}",
        json={
            "requirement_id": req["requirement_id"],
            "job_name": "改了", "job_jd": "jd", "job_min_degree": "博士",
            "job_min_exp_years": 10, "job_required_skills": ["Rust"], "job_status": 1,
        },
    )
    results = client.get(f"/api/screening/runs/{run['run_id']}/results").json()
    assert results[0]["result"] == "PASS"  # 快照规则判定不变
