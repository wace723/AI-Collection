"""e2e-001 端到端完整闭环验证（data-004 改造适配）。

覆盖 docs/03 §8 TC-E2E-01/02/03：
- TC-E2E-01 完整催收闭环（上传待支付→自动跑批推进→分配→工作台→详情→推荐话术→AI生成→
  回填REACHED→Order转COLLECTED→大盘）
- TC-E2E-02 高风险多轮催收（首轮REACHED→COLLECTED→第15天跑批推进PENDING_COLLECTION→生成SECOND）
- TC-E2E-03 已支付订单标记 PAID 后跑批不生成新任务

data-004 改造点（影响 e2e）：
- POST /api/data/upload-pending 导入成功后自动调用 run_batch(today=date.today(), recalc_risk=False)，
  响应 UploadSummary.batch_result（含 generated/finalized/by_tier）。不再需要手动 POST /batch/run。
- CSV 由 38 列变 40 列：新增「工程局单位」「下属单位」（在「标的概算金额」后、「中标日期」前）。
- PENDING_COLLECTION 现在在 ADVANCEABLE_STATES，跑批会推进 PENDING_COLLECTION 状态的订单
  （为其生成当轮无 Task 的任务）。

通过 TestClient 串真实 API 端到端验证全流程贯通。AI 话术走 mock（不触网）。
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.models.ai_config import AIConfig
from app.models.order import Order
from app.models.task import Task
from app.models.user import User
from app.services.task_engine import run_batch
from app.services.task_engine.states import (
    COLLECTED,
    FINALIZED,
    PENDING_COLLECTION,
    REACHED,
)

# 待支付订单 CSV 表头（40 列，与 columns.py 一致）
# data-004：新增「工程局单位」「下属单位」（在「标的概算金额」后、「中标日期」前）
CSV_HEADER = (
    "供应商编号,供应商名称,招标编号,服务费订单号,标的名称,招标类型,采购类型,"
    "中标品类,合同类型,标的概算金额,工程局单位,下属单位,中标日期,订单生成日期,"
    "历史平台使用费订单数,"
    "上次缴费历时_天,历史缴费平均历时_天,服务市场历史支付金额,历史报名次数,"
    "历史投标次数,历史中标次数,历史中标率,近90天投标活跃度,首次中标距本次间隔_天,"
    "中标时是否会员,中标前购买会员次数,注册资金,注册地区,注册省份,"
    "注册时间距中标间隔_天,平台入驻时间距中标间隔_天,最早入库时间距中标间隔_天,"
    "标签表历史中标率,股份优质评级次数,合作单位数量,累计履约项目数,"
    "中标月份,是否月末,是否季末,风险概率"
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
    """构造一行待支付 CSV 数据（40 列，风险概率=75 → HIGH 档）。

    data-004：在「标的概算金额」后插入「工程局单位,下属单位」两列。
    """
    return (
        f"1355714,{supplier},biz001,{order_no},某标的项目,"
        f"竞价采购,集中采购,工程类,合同类型1,1000000,"
        f"某工程局,某下属单位,"
        f"{win_bid_date.year}/{win_bid_date.month}/{win_bid_date.day},"
        f"{win_bid_date.year}/{win_bid_date.month}/{win_bid_date.day},"
        f"0,30,30,"
        f"5000,5,6,2,0.05,"
        f"0,100,0,0,"
        f"5000000,北京,北京,2000,1800,1600,0.1,0,1,1,1,0,0,"
        f"75"
    )


def _build_csv(rows: list[str]) -> str:
    return "\n".join([CSV_HEADER, *rows])


def _seed_mock_ai_config(db_session) -> None:
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
    from seed import seed_ai_config, seed_default_config, seed_default_talk_templates

    seed_default_config(db_session)
    seed_default_talk_templates(db_session)
    _seed_mock_ai_config(db_session)


@pytest.fixture()
def seed_users(db_session):
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
    """上传待支付→自动跑批推进→分配→工作台→详情→推荐话术→AI生成→回填REACHED→COLLECTED→大盘。

    构造 20 条 HIGH 风险订单（风险概率=75），win_bid_date=today-8天
    （HIGH 档 7 天时点已到，导入即预设 PENDING_COLLECTION，并触发自动跑批生成 FIRST 任务）。

    data-004 改造点：
    - POST /api/data/upload-pending 导入后自动调用 run_batch(today=date.today())，
      响应 UploadSummary.batch_result（含 generated/finalized/by_tier）。
    - 不再需要手动 POST /api/tasks/batch/run 推进首轮。
    """
    today = date.today()
    win_bid = today - timedelta(days=8)

    # 步骤1：管理员上传待支付 CSV，20 条入库（风险概率=75 → HIGH，导入预设 collection_state）
    # data-004：导入成功后自动触发跑批（推进状态机 + 生成任务）
    rows = [_make_row(f"SFO_E2E_{i:04d}", f"测试公司{i}", win_bid) for i in range(20)]
    csv_text = _build_csv(rows)
    files = {"file": ("orders.csv", csv_text.encode("utf-8"), "text/csv")}
    resp = client.post(
        "/api/data/upload-pending", files=files, headers=_headers(client, "admin")
    )
    assert resp.status_code == 200, resp.text
    upload_data = resp.json()["data"]
    assert upload_data["inserted"] == 20

    # 自动跑批已触发：batch_result 不为 None（证明 upload-pending 已自动跑批）
    assert upload_data["batch_result"] is not None
    batch_result = upload_data["batch_result"]
    # HIGH 档首轮 day_offset=7，win_bid=today-8 → 首轮时点已到，生成 20 条 FIRST 任务
    # （不强制断言 generated 具体值，因 today 真实日期与 win_bid 关系决定；
    #  这里 win_bid=today-8 确保首轮 7 天时点已到，generated 应为 20）
    assert batch_result["generated"] == 20

    # 导入预设：win_bid+7天<=today → PENDING_COLLECTION
    order0 = (
        db_session.query(Order)
        .filter(Order.service_fee_order_no == "SFO_E2E_0000")
        .first()
    )
    assert order0.collection_state == PENDING_COLLECTION

    # 步骤2：风险档已由导入写入
    # 步骤3：默认风险档配置已 seed 生效（fixture）
    # 步骤4：已由 upload-pending 自动跑批生成首轮任务，无需手动 POST /batch/run

    # 步骤4b：管理员触发分配
    resp = client.post(
        "/api/tasks/assign/run", headers=_headers(client, "admin")
    )
    assert resp.status_code == 200, resp.text
    assign = resp.json()["data"]
    assert assign["assigned"] == 20

    # 步骤5：催收员登录工作台
    resp = client.get(
        "/api/tasks?size=100", headers=_headers(client, "collector1")
    )
    assert resp.status_code == 200, resp.text
    my_tasks = resp.json()["data"]
    assert my_tasks["total"] >= 1
    task_id = my_tasks["items"][0]["id"]
    assert my_tasks["items"][0]["status"] == "IN_PROGRESS"
    assert my_tasks["items"][0]["collection_state"] == PENDING_COLLECTION

    # 步骤6：任务详情
    resp = client.get(
        f"/api/tasks/{task_id}", headers=_headers(client, "collector1")
    )
    assert resp.status_code == 200, resp.text
    detail = resp.json()["data"]
    assert detail["order"] is not None
    assert detail["feature"] is not None

    # 步骤7：推荐话术
    resp = client.get(
        f"/api/talk/recommend?task_id={task_id}",
        headers=_headers(client, "collector1"),
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["data"]["templates"]) >= 1

    # 步骤8：AI 生成话术（mock）
    resp = client.post(
        f"/api/talk/generate?task_id={task_id}",
        headers=_headers(client, "collector1"),
    )
    assert resp.status_code == 200, resp.text
    gen = resp.json()["data"]
    assert gen["content"]
    assert gen["enabled"] is True

    # 步骤8b：回填 REACHED → Task DONE + Order COLLECTED
    resp = client.post(
        f"/api/tasks/{task_id}/result",
        headers=_headers(client, "collector1"),
        json={"result": REACHED, "note": "客户确认付款"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "DONE"
    assert resp.json()["data"]["result"] == REACHED

    # Order 推进为已催收
    db_session.refresh(order0)
    # order0 可能不是回填的那个，查回填的 task 对应 order
    task = db_session.get(Task, task_id)
    filled_order = db_session.get(Order, task.order_id)
    assert filled_order.collection_state == COLLECTED

    # 步骤9：大盘（回款=REACHED 明细，data-003 口径）
    resp = client.get(
        "/api/dashboard/daily", headers=_headers(client, "supervisor")
    )
    assert resp.status_code == 200, resp.text
    daily = resp.json()["data"]
    assert daily["paid_count"] == 1
    assert daily["processed_count"] == 1
    assert daily["paid_rate"] == 1.0
    assert daily["unpaid_total"] == 20


# ── TC-E2E-02：高风险订单多轮催收闭环 ─────────────────────────────


def test_e2e_02_high_risk_multi_round(client, db_session, seed_users):
    """首轮 REACHED→COLLECTED→第15天跑批推进 PENDING_COLLECTION→生成 SECOND→回填 REACHED。

    用 service 层 run_batch 注入 today 模拟时间推进（API 不接受 today 注入）。

    data-004 改造点：
    - upload-pending 导入后自动跑批（today=date.today()）。base_date=2026-01-01，
      today=真实今天（远晚于 base_date+30），自动跑批会生成首轮 FIRST(day_offset=7) 任务。
    - 为用注入 today 的 run_batch 验证多轮时间推进，导入后清理自动跑批产生的任务，
      重置 collection_state=NO_NEED，得到干净起点。
    """
    from app.services.task_engine import assign_pending_tasks, submit_result
    from app.models.user import User as UserModel

    base_date = date(2026, 1, 1)

    rows = [_make_row("SFO_MR_001", "多轮催收测试公司", base_date)]
    csv_text = _build_csv(rows)
    files = {"file": ("orders.csv", csv_text.encode("utf-8"), "text/csv")}
    resp = client.post(
        "/api/data/upload-pending", files=files, headers=_headers(client, "admin")
    )
    assert resp.json()["data"]["inserted"] == 1
    # data-004：导入后自动跑批已触发，batch_result 不为 None
    assert resp.json()["data"]["batch_result"] is not None

    order = (
        db_session.query(Order)
        .filter(Order.service_fee_order_no == "SFO_MR_001")
        .first()
    )
    assert order.risk_tier == "HIGH"

    # 清理导入时自动跑批产生的任务 + 重置状态为 NO_NEED，得到干净的多轮推进起点
    db_session.query(Task).filter(Task.order_id == order.id).delete(
        synchronize_session=False
    )
    order.collection_state = "NO_NEED"
    db_session.commit()

    # 第7天跑批：NO_NEED→PENDING_COLLECTION + 生成 FIRST
    run_batch(db_session, today=base_date + timedelta(days=7), recalc_risk=False)
    db_session.commit()
    tasks_d7 = (
        db_session.query(Task).filter(Task.order_id == order.id).all()
    )
    first_tasks = [t for t in tasks_d7 if t.day_offset == 7]
    assert len(first_tasks) == 1
    assert first_tasks[0].scene == "FIRST"
    assert order.collection_state == PENDING_COLLECTION

    # 分配 + 回填 REACHED → Task DONE + Order COLLECTED
    assign_pending_tasks(db_session)
    db_session.commit()
    task = first_tasks[0]
    operator = (
        db_session.query(UserModel).filter(UserModel.id == task.assignee_id).first()
    )
    submit_result(db_session, task.id, operator, result=REACHED, note="首轮接通")
    db_session.commit()
    db_session.refresh(task)
    assert task.status == "DONE"
    assert order.collection_state == COLLECTED

    # 第15天跑批：COLLECTED→PENDING_COLLECTION + 生成 SECOND（该轮无 Task）
    run_batch(db_session, today=base_date + timedelta(days=15), recalc_risk=False)
    db_session.commit()
    tasks_d15 = (
        db_session.query(Task).filter(Task.order_id == order.id).all()
    )
    second_tasks = [t for t in tasks_d15 if t.day_offset == 15]
    assert len(second_tasks) == 1
    assert second_tasks[0].scene == "SECOND"
    # 首轮 FIRST 任务仍在
    assert len([t for t in tasks_d15 if t.day_offset == 7]) == 1
    assert order.collection_state == PENDING_COLLECTION

    # 回填 SECOND → DONE + COLLECTED
    assign_pending_tasks(db_session)
    db_session.commit()
    task2 = second_tasks[0]
    db_session.refresh(task2)
    op2 = (
        db_session.query(UserModel).filter(UserModel.id == task2.assignee_id).first()
    )
    submit_result(db_session, task2.id, op2, result=REACHED, note="二轮接通")
    db_session.commit()
    db_session.refresh(task2)
    assert task2.status == "DONE"
    assert order.collection_state == COLLECTED


# ── TC-E2E-03：已支付订单全程不催收 ───────────────────────────────


def test_e2e_03_paid_order_never_collected(client, db_session, seed_users):
    """已支付订单标记 PAID 后跑批不生成新任务。

    data-004 改造点：
    - upload-pending 导入后自动跑批：win_bid=today-90，HIGH 首轮 day_offset=7 已到，
      导入时自动生成 FIRST 任务（导入时订单仍待支付，属正常催收）。
    - 标记 PAID 后再跑批（API + service 层多日推进）：已支付订单被 pay_status 门控跳过，
      不推进、不生成新任务。本测试断言「标记 PAID 后的跑批不生成新任务」
      （而非「全程不生成任何任务」，因导入时已自动跑批生成过）。
    """
    today = date.today()
    win_bid = today - timedelta(days=90)

    rows = [_make_row("SFO_PAID_001", "已支付公司", win_bid)]
    csv_text = _build_csv(rows)
    files = {"file": ("orders.csv", csv_text.encode("utf-8"), "text/csv")}
    resp = client.post(
        "/api/data/upload-pending", files=files, headers=_headers(client, "admin")
    )
    assert resp.json()["data"]["inserted"] == 1
    # data-004：导入后自动跑批已触发
    assert resp.json()["data"]["batch_result"] is not None

    order = (
        db_session.query(Order)
        .filter(Order.service_fee_order_no == "SFO_PAID_001")
        .first()
    )
    assert order.risk_tier == "HIGH"

    # 导入时自动跑批生成首轮任务（订单当时待支付，win_bid+7<=today）
    tasks_before_paid = (
        db_session.query(Task).filter(Task.order_id == order.id).all()
    )
    assert len(tasks_before_paid) == 1  # 导入自动跑批生成的 FIRST

    # 手动标记为已支付（不取消已存在任务，仅阻止后续跑批生成新任务）
    order.pay_status = "PAID"
    db_session.commit()

    # 标记 PAID 后跑批（recalc=false）：已支付订单被 pay_status 门控跳过，不推进不生成新任务
    resp = client.post(
        "/api/tasks/batch/run?recalc=false", headers=_headers(client, "admin")
    )
    assert resp.status_code == 200, resp.text
    batch = resp.json()["data"]
    assert batch["generated"] == 0

    # 多日跑批仍不生成新任务（任务数仍等于导入时的数量）
    for offset in (1, 7, 15, 30):
        run_batch(db_session, today=today + timedelta(days=offset), recalc_risk=False)
        db_session.commit()
    tasks_after_paid = (
        db_session.query(Task).filter(Task.order_id == order.id).all()
    )
    assert len(tasks_after_paid) == len(tasks_before_paid)
