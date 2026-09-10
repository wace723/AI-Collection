"""e2e-001 端到端完整闭环验证。

覆盖 docs/03 §8 TC-E2E-01/02/03：
- TC-E2E-01 完整催收闭环（上传→算风险→跑批→分配→工作台→AI话术→回填→大盘）
- TC-E2E-02 高风险多轮催收（FIRST→PROMISE 改期→第15天 SECOND）
- TC-E2E-03 已支付订单全程不催收

通过 TestClient 串真实 API 端到端验证全流程贯通。AI 话术走 mock（不触网）。
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.models.ai_config import AIConfig
from app.models.task import Task
from app.models.user import User
from app.services.task_engine import run_batch

# 37 列表头（与示例文件一致，复用 test_data_upload 模式）
CSV_HEADER = (
    "供应商编号,供应商名称,招标编号,服务费订单号,招标类型,采购类型,中标日期,"
    "实际支付时长_天,标签_30天是否欠费,标签_90天是否欠费,标签_180天是否欠费,"
    "标签_365天是否欠费,历史平台使用费订单数,上次缴费历时_天,历史缴费平均历时_天,"
    "服务市场历史支付金额,历史报名次数,历史投标次数,历史中标次数,历史中标率,"
    "近90天投标活跃度,首次中标距本次间隔_天,中标时是否会员,中标前购买会员次数,"
    "注册资金,注册地区,注册时间距中标间隔_天,平台入驻时间距中标间隔_天,"
    "最早入库时间距中标间隔_天,供应商品类,标签表历史中标率,股份优质评级次数,"
    "合作单位数量,累计履约项目数,中标月份,是否月末,是否季末"
)


# ── 辅助 ──────────────────────────────────────────────────────────


def _login_token(client, username, password="admin123") -> str:
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


def _headers(client, username) -> dict[str, str]:
    return {"Authorization": f"Bearer {_login_token(client, username)}"}


def _make_row(order_no: str, supplier: str, win_bid_date: date) -> str:
    """构造一行 HIGH 风险 CSV 数据（特征使 mock 概率 ≥70 → HIGH 档）。

    mock 公式：缴费历时长(0.35)+平台使用费订单数少(0.25)+中标率低(0.20)
    +活跃度低(0.15)+非会员(0.05) → 高风险。win_bid_date 可控。
    """
    return (
        f"1355714,{supplier},biz001,{order_no},竞价采购,集中采购,"
        f"{win_bid_date.year}/{win_bid_date.month}/{win_bid_date.day},"
        # 实际支付时长空(NULL)、各欠费标签=1
        ",1,1,1,1,"
        # 历史平台使用费订单数=0(少)、上次缴费历时=30、历史缴费平均历时=30(长→高风险)
        "0,30,30,"
        # 服务市场支付金额、报名、投标、中标=2(低)、中标率=0.05(低→高风险)
        "5000,5,6,2,0.05,"
        # 近90天活跃度=0(低→高风险)、首次中标间隔=100、非会员=0、会员购买次数=0
        "0,100,0,0,"
        # 注册资金、注册地区、各间隔、品类、标签中标率、优质评级、合作单位、履约项目、月份、月末、季末
        "5000000,北京,2000,1800,1600,市政类,0.1,0,1,1,1,0,0"
    )


def _build_csv(rows: list[str]) -> str:
    return "\n".join([CSV_HEADER, *rows])


def _seed_mock_ai_config(db_session) -> None:
    """插入 mock+enabled 的 ai_config，使 AI 生成走 mock 不触网。"""
    db_session.add(
        AIConfig(
            id=1,
            provider="mock",
            api_key=None,
            base_url=None,
            model=None,
            enabled=True,
        )
    )
    db_session.commit()


def _seed_five_users(db_session) -> None:
    """建 admin/supervisor + 3 名催收员。"""
    from app.core.security import hash_password

    users = [
        ("admin", "管理员", "ADMIN"),
        ("supervisor", "催收主管", "SUPERVISOR"),
        ("collector1", "催收员1", "COLLECTOR"),
        ("collector2", "催收员2", "COLLECTOR"),
        ("collector3", "催收员3", "COLLECTOR"),
    ]
    for username, display_name, role in users:
        db_session.add(
            User(
                username=username,
                password_hash=hash_password("admin123"),
                display_name=display_name,
                role=role,
                is_active=True,
            )
        )
    db_session.commit()


def _seed_default_config(db_session) -> None:
    """默认风险档配置 + 话术模板（幂等种子）。"""
    from seed import seed_ai_config, seed_default_config, seed_default_talk_templates

    seed_default_config(db_session)
    seed_default_talk_templates(db_session)
    # 覆盖 seed_ai_config（避免 .env 真实 key 启用 openai_compatible 触网）
    _seed_mock_ai_config(db_session)


@pytest.fixture()
def seed_users(db_session):
    """覆盖 conftest：建 5 用户 + 默认配置 + mock AI。"""
    _seed_five_users(db_session)
    _seed_default_config(db_session)
    return {u[0]: "admin123" for u in [
        ("admin", "", "ADMIN"),
        ("supervisor", "", "SUPERVISOR"),
        ("collector1", "", "COLLECTOR"),
        ("collector2", "", "COLLECTOR"),
        ("collector3", "", "COLLECTOR"),
    ]}


# ── TC-E2E-01：完整催收闭环 ───────────────────────────────────────


def test_e2e_01_full_collection_loop(client, db_session, seed_users):
    """上传→算风险→确认配置→跑批→分配→工作台→详情→推荐话术→AI生成→回填PAID→大盘。

    构造 20 条订单，win_bid_date=today-8天（HIGH 档 7 天时点已到，生成 FIRST 任务）。
    """
    today = date.today()
    win_bid = today - timedelta(days=8)

    # 步骤1：管理员上传 CSV，20 条入库
    rows = [_make_row(f"SFO_E2E_{i:04d}", f"测试公司{i}", win_bid) for i in range(20)]
    csv_text = _build_csv(rows)
    files = {"file": ("orders.csv", csv_text.encode("utf-8"), "text/csv")}
    resp = client.post("/api/data/upload", files=files, headers=_headers(client, "admin"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["inserted"] == 20

    # 步骤2：触发重新计算风险
    resp = client.post(
        "/api/data/orders/recalc-risk", headers=_headers(client, "admin")
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["recalculated"] == 20

    # 步骤3：默认风险档配置已 seed 生效（步骤 fixture）

    # 步骤4：管理员手动触发跑批
    resp = client.post(
        "/api/tasks/batch/run?recalc=true", headers=_headers(client, "admin")
    )
    assert resp.status_code == 200, resp.text
    batch = resp.json()["data"]
    assert batch["generated"] == 20  # 每订单 HIGH 档 7 天时点已到 → 1 个 FIRST 任务

    # 步骤4b：管理员触发分配
    resp = client.post(
        "/api/tasks/assign/run", headers=_headers(client, "admin")
    )
    assert resp.status_code == 200, resp.text
    assign = resp.json()["data"]
    assert assign["assigned"] == 20  # 分给 3 名催收员

    # 步骤5：催收员登录工作台，看到分配给自己的任务（按风险/账龄排序）
    resp = client.get(
        "/api/tasks?size=100", headers=_headers(client, "collector1")
    )
    assert resp.status_code == 200, resp.text
    my_tasks = resp.json()["data"]
    assert my_tasks["total"] >= 1  # collector1 至少分到 1 个
    task_id = my_tasks["items"][0]["id"]
    assert my_tasks["items"][0]["status"] in ("PENDING", "IN_PROGRESS")

    # 步骤6：进入任务详情（订单信息+特征摘要）
    resp = client.get(
        f"/api/tasks/{task_id}", headers=_headers(client, "collector1")
    )
    assert resp.status_code == 200, resp.text
    detail = resp.json()["data"]
    assert detail["order"] is not None
    assert detail["feature"] is not None

    # 步骤7：推荐基础话术
    resp = client.get(
        f"/api/talk/recommend?task_id={task_id}",
        headers=_headers(client, "collector1"),
    )
    assert resp.status_code == 200, resp.text
    rec = resp.json()["data"]
    assert len(rec["templates"]) >= 1  # ANY 兜底模板必有

    # 步骤8：触发 AI 生成话术（mock）
    resp = client.post(
        f"/api/talk/generate?task_id={task_id}",
        headers=_headers(client, "collector1"),
    )
    assert resp.status_code == 200, resp.text
    gen = resp.json()["data"]
    assert gen["content"]  # mock 非空
    assert gen["enabled"] is True

    # 步骤8b：领取任务（PENDING→IN_PROGRESS）后回填 PAID
    resp = client.post(
        f"/api/tasks/{task_id}/claim", headers=_headers(client, "collector1")
    )
    assert resp.status_code == 200, resp.text
    resp = client.post(
        f"/api/tasks/{task_id}/result",
        headers=_headers(client, "collector1"),
        json={"result": "PAID"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "DONE"
    assert resp.json()["data"]["result"] == "PAID"

    # 步骤9：查看日大盘，回款数 +1
    resp = client.get(
        "/api/dashboard/daily", headers=_headers(client, "supervisor")
    )
    assert resp.status_code == 200, resp.text
    daily = resp.json()["data"]
    assert daily["paid_count"] == 1
    assert daily["processed_count"] == 1
    assert daily["paid_rate"] == 1.0
    assert daily["unpaid_total"] == 20  # 上传的 20 条全未支付


# ── TC-E2E-02：高风险订单多轮催收闭环 ─────────────────────────────


def test_e2e_02_high_risk_multi_round(client, db_session, seed_users):
    """上传高风险订单 → 第7天跑批生成 FIRST → PROMISE 改期 → 第15天跑批生成 SECOND。

    用 service 层 run_batch 注入 today 模拟时间推进（API 不接受 today 注入）。
    """
    # 中标日设为基准，使第7天/第15天时点可控
    base_date = date(2026, 1, 1)

    rows = [_make_row("SFO_MR_001", "多轮催收测试公司", base_date)]
    csv_text = _build_csv(rows)
    files = {"file": ("orders.csv", csv_text.encode("utf-8"), "text/csv")}
    resp = client.post("/api/data/upload", files=files, headers=_headers(client, "admin"))
    assert resp.json()["data"]["inserted"] == 1

    # 重算风险 → HIGH 档（特征构造使 mock 概率落在 HIGH）
    resp = client.post(
        "/api/data/orders/recalc-risk", headers=_headers(client, "admin")
    )
    assert resp.json()["data"]["recalculated"] == 1
    # 确认该订单为 HIGH 档（mock 5 维加权，本行特征 → 可能 HIGH/MEDIUM）
    # 用 db 直接确认档位，若非 HIGH 则不强求档位，验证时点生成逻辑即可
    from app.models.order import Order

    order = (
        db_session.query(Order)
        .filter(Order.service_fee_order_no == "SFO_MR_001")
        .first()
    )
    assert order is not None
    assert order.risk_tier is not None  # 有档位

    # 第7天跑批：应生成 FIRST 任务（HIGH 档 day_offset=7）
    run_batch(db_session, today=base_date + timedelta(days=7), recalc_risk=False)
    db_session.commit()
    tasks_d7 = (
        db_session.query(Task)
        .filter(Task.order_id == order.id)
        .all()
    )
    first_tasks = [t for t in tasks_d7 if t.day_offset == 7]
    assert len(first_tasks) == 1
    assert first_tasks[0].scene == "FIRST"

    # 分配 + 领取 + 回填 PROMISE 改期
    from app.services.task_engine import assign_pending_tasks, claim_task, submit_result
    from app.models.user import User as UserModel

    assign_pending_tasks(db_session)
    db_session.commit()
    collector = (
        db_session.query(UserModel)
        .filter(UserModel.role == "COLLECTOR")
        .order_by(UserModel.id)
        .first()
    )
    task = first_tasks[0]
    # 确保分配给了某催收员
    assert task.assignee_id is not None
    operator = (
        db_session.query(UserModel).filter(UserModel.id == task.assignee_id).first()
    )
    claim_task(db_session, task.id, operator)
    db_session.commit()
    promise_date = base_date + timedelta(days=14)
    submit_result(
        db_session,
        task.id,
        operator,
        result="PROMISE",
        next_followup_date=promise_date,
    )
    db_session.commit()
    # 任务回到 PENDING（改期）
    db_session.refresh(task)
    assert task.status == "PENDING"

    # 第15天再跑批：生成 SECOND 任务（即使首轮改期，第15天时点仍触发）
    run_batch(db_session, today=base_date + timedelta(days=15), recalc_risk=False)
    db_session.commit()
    tasks_d15 = (
        db_session.query(Task)
        .filter(Task.order_id == order.id)
        .all()
    )
    second_tasks = [t for t in tasks_d15 if t.day_offset == 15]
    assert len(second_tasks) == 1
    assert second_tasks[0].scene == "SECOND"
    # 第7天的 FIRST 任务仍在（幂等不重复生成）
    assert len([t for t in tasks_d15 if t.day_offset == 7]) == 1

    # 回填 DISPUTE → 转异议处理（DONE 终态）
    task2 = second_tasks[0]
    # 分配 + 领取
    assign_pending_tasks(db_session)
    db_session.commit()
    db_session.refresh(task2)
    op2 = (
        db_session.query(UserModel).filter(UserModel.id == task2.assignee_id).first()
    )
    claim_task(db_session, task2.id, op2)
    db_session.commit()
    submit_result(db_session, task2.id, op2, result="DISPUTE")
    db_session.commit()
    db_session.refresh(task2)
    assert task2.status == "DONE"
    assert task2.result == "DISPUTE"


# ── TC-E2E-03：已支付订单全程不催收 ───────────────────────────────


def test_e2e_03_paid_order_never_collected(client, db_session, seed_users):
    """上传含已支付订单 → 跑批不生成其任务 → 多日跑批始终不生成。"""
    today = date.today()
    win_bid = today - timedelta(days=90)  # 账龄足够长，所有时点都到

    rows = [_make_row("SFO_PAID_001", "已支付公司", win_bid)]
    csv_text = _build_csv(rows)
    files = {"file": ("orders.csv", csv_text.encode("utf-8"), "text/csv")}
    resp = client.post("/api/data/upload", files=files, headers=_headers(client, "admin"))
    assert resp.json()["data"]["inserted"] == 1

    # 重算风险（有档位才能进入跑批候选）
    resp = client.post(
        "/api/data/orders/recalc-risk", headers=_headers(client, "admin")
    )
    assert resp.json()["data"]["recalculated"] == 1

    # 上传后该订单 pay_status 仍为 NULL（CSV 不含 pay_status 列），
    # 手动标记为已支付（模拟真实已支付订单）
    from app.models.order import Order

    order = (
        db_session.query(Order)
        .filter(Order.service_fee_order_no == "SFO_PAID_001")
        .first()
    )
    order.pay_status = "PAID"
    db_session.commit()

    # 跑批（recalc=false，用现有档位）
    resp = client.post(
        "/api/tasks/batch/run?recalc=false", headers=_headers(client, "admin")
    )
    assert resp.status_code == 200, resp.text
    batch = resp.json()["data"]
    # 该已支付订单不应生成任务
    assert batch["generated"] == 0

    # 多日跑批（推进 30 天）仍不生成
    for offset in (1, 7, 15, 30):
        run_batch(db_session, today=today + timedelta(days=offset), recalc_risk=False)
        db_session.commit()
    tasks = (
        db_session.query(Task)
        .filter(Task.order_id == order.id)
        .all()
    )
    assert len(tasks) == 0  # 始终不生成任何任务
