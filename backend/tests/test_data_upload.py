"""data-002 CSV 上传与解析测试（重写）。

适配新接口：
- POST /api/data/upload-pending：待支付导入（ADMIN），新订单入库+风险概率映射档位
- POST /api/data/upload-paid：已支付导入（ADMIN），按订单号回写 pay_status=PAID

风险概率经 tier_mapper 阈值映射档位（需 seed_default_config 提供 active 配置，
无配置时 tier_mapper 回退默认 70/30）。
"""

from __future__ import annotations

import io

from app.services.risk_engine import seed_default_config


# ── 测试夹具：构造最小合规 CSV（新表头） ────────────────────────────

# 待支付订单 CSV 表头（38 列，与 app/services/data_ingestion/columns.py 一致）
CSV_HEADER = (
    "供应商编号,供应商名称,招标编号,服务费订单号,标的名称,招标类型,采购类型,"
    "中标品类,合同类型,标的概算金额,中标日期,订单生成日期,历史平台使用费订单数,"
    "上次缴费历时_天,历史缴费平均历时_天,服务市场历史支付金额,历史报名次数,"
    "历史投标次数,历史中标次数,历史中标率,近90天投标活跃度,首次中标距本次间隔_天,"
    "中标时是否会员,中标前购买会员次数,注册资金,注册地区,注册省份,"
    "注册时间距中标间隔_天,平台入驻时间距中标间隔_天,最早入库时间距中标间隔_天,"
    "标签表历史中标率,股份优质评级次数,合作单位数量,累计履约项目数,"
    "中标月份,是否月末,是否季末,风险概率"
)

# 已支付订单 CSV 表头（39 列，与待支付差异：多「支付日期」「实际支付时长_天」，
# 无「订单生成日期」）
PAID_CSV_HEADER = (
    "供应商编号,供应商名称,招标编号,服务费订单号,标的名称,招标类型,采购类型,"
    "中标品类,合同类型,标的概算金额,中标日期,支付日期,实际支付时长_天,"
    "历史平台使用费订单数,上次缴费历时_天,历史缴费平均历时_天,"
    "服务市场历史支付金额,历史报名次数,历史投标次数,历史中标次数,历史中标率,"
    "近90天投标活跃度,首次中标距本次间隔_天,中标时是否会员,中标前购买会员次数,"
    "注册资金,注册地区,注册省份,注册时间距中标间隔_天,平台入驻时间距中标间隔_天,"
    "最早入库时间距中标间隔_天,标签表历史中标率,股份优质评级次数,合作单位数量,"
    "累计履约项目数,中标月份,是否月末,是否季末,风险概率"
)


def _pending_row(
    order_no: str = "SFO_TEST_0001",
    supplier: str = "北京恒锐建设工程有限公司",
    risk_prob: str = "75",
) -> str:
    """构造一行待支付 CSV 数据（38 列，风险概率默认 75→HIGH）。

    空值字段用历史缴费平均历时为空演示 NULL 入库。
    """
    return (
        f"1355714,{supplier},cscec2025061000001037188,{order_no},某标的项目,"
        f"竞价采购,集中采购,工程类,合同类型1,1000000,2025/9/8,2025/9/8,"
        f"1,9,9,12480,69,58,11,0.1897,3,1755,0,0,10000000,北京,北京,"
        f"2566,2217,1943,0.2308,0,3,7,9,0,0,{risk_prob}"
    )


def _pending_row_with_nulls(order_no: str = "SFO_NULL_001") -> str:
    """构造含空值的待支付行：历史缴费平均历时/风险概率为空。"""
    return (
        f"2000001,河南曼之达建设有限公司,biz002,{order_no},某标的2,"
        f"竞价采购,集中采购,工程类,合同类型1,1000000,2025/9/8,2025/9/8,"
        # 历史平台使用费订单数=2、上次缴费历时=15、历史缴费平均历时=空
        f"2,15,,0,70,60,8,0.13,5,100,1,2,5000000,北京,北京,"
        f"2000,1800,1600,0.1,1,5,3,9,0,0,"
        # 风险概率空 → risk_tier=None
        f""
    )


def _paid_row(
    order_no: str = "SFO_TEST_0001",
    pay_date: str = "2025/9/10",
    duration: str = "7",
) -> str:
    """构造一行已支付 CSV 数据（39 列，含支付日期+实际支付时长）。"""
    return (
        f"1355714,北京恒锐建设工程有限公司,cscec2025061000001037188,{order_no},"
        f"某标的项目,竞价采购,集中采购,工程类,合同类型1,1000000,2025/9/8,"
        f"{pay_date},{duration},"
        f"1,9,9,12480,69,58,11,0.1897,3,1755,0,0,10000000,北京,北京,"
        f"2566,2217,1943,0.2308,0,3,7,9,0,0,75"
    )


def _login_token(client, username="admin", password="admin123") -> str:
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


def _auth_headers(client, username="admin") -> dict[str, str]:
    return {"Authorization": f"Bearer {_login_token(client, username)}"}


def _build_csv(rows: list[str], header: str = CSV_HEADER, newline: str = "\n") -> str:
    return newline.join([header, *rows])


def _seed_risk_config(db_session) -> None:
    """插入默认风险档配置（70/30），使 tier_mapper 映射生效。"""
    seed_default_config(db_session)


# ── TC-DATA-01：UTF-8 待支付 CSV 上传成功 + 风险档映射 ──────────────


def test_upload_utf8_csv_success(client, seed_users, db_session):
    _seed_risk_config(db_session)
    # 每行用不同 order_no，风险概率=75 → HIGH 档
    rows = [_pending_row(f"SFO_TEST_{i:04d}", f"测试公司{i}") for i in range(20)]
    csv_text = _build_csv(rows)
    files = {
        "file": ("orders_utf8.csv", csv_text.encode("utf-8"), "text/csv"),
    }
    resp = client.post(
        "/api/data/upload-pending", files=files, headers=_auth_headers(client)
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["inserted"] == 20
    assert body["data"]["skipped"] == 0

    # 列表可查到 20 条
    list_resp = client.get("/api/data/orders", headers=_auth_headers(client))
    assert list_resp.status_code == 200
    assert list_resp.json()["data"]["total"] == 20

    # 风险档映射：风险概率 75 ≥ 70 → HIGH
    items = list_resp.json()["data"]["items"]
    assert all(item["risk_tier"] == "HIGH" for item in items)
    # 待支付导入：pay_status 应为 None
    assert all(item["pay_status"] is None for item in items)
    # risk_import_time 已写入
    assert all(item["risk_import_time"] is not None for item in items)


# ── TC-DATA-02：GBK 编码 CSV 上传成功（编码自动识别） ──────────────


def test_upload_gbk_csv_success(client, seed_users, db_session):
    _seed_risk_config(db_session)
    csv_text = _build_csv([_pending_row()])
    files = {
        "file": ("orders_gbk.csv", csv_text.encode("gbk"), "text/csv"),
    }
    resp = client.post(
        "/api/data/upload-pending", files=files, headers=_auth_headers(client)
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["inserted"] == 1

    # 中文无乱码
    list_resp = client.get("/api/data/orders", headers=_auth_headers(client))
    supplier_name = list_resp.json()["data"]["items"][0]["supplier_name"]
    assert supplier_name == "北京恒锐建设工程有限公司"


# ── TC-DATA-03：缺失必填列返回 400 ──────────────────────────────────


def test_upload_missing_columns_returns_400(client, seed_users, db_session):
    _seed_risk_config(db_session)
    # 故意缺少必填列「服务费订单号」
    bad_header = (
        "供应商编号,供应商名称,招标编号,标的名称,招标类型,采购类型,"
        "中标品类,合同类型,标的概算金额,中标日期,订单生成日期,风险概率"
    )
    bad_row = "1,公司A,biz1,某标的,竞价,集中,工程类,合同1,1000000,2025/9/8,2025/9/8,75"
    csv_text = "\n".join([bad_header, bad_row])
    files = {"file": ("bad.csv", csv_text.encode("utf-8"), "text/csv")}

    resp = client.post(
        "/api/data/upload-pending", files=files, headers=_auth_headers(client)
    )

    assert resp.status_code == 400
    body = resp.json()
    detail = body.get("detail") or body.get("error") or ""
    assert "缺失" in detail or "missing" in detail.lower()


# ── TC-DATA-04：重复上传更新风险概率/特征 ────────────────────────────


def test_duplicate_updates_risk_prob(client, seed_users, db_session):
    """重复上传同订单号：更新风险概率与特征（updated=1，非 inserted）。

    第一次：风险概率=75 → HIGH
    第二次：风险概率=15 → LOW（特征同步更新）
    """
    _seed_risk_config(db_session)
    # 第一次上传（HIGH）
    files1 = {
        "file": (
            "orders.csv",
            _build_csv([_pending_row("SFO_DUP_001", risk_prob="75")]).encode("utf-8"),
            "text/csv",
        )
    }
    resp1 = client.post(
        "/api/data/upload-pending", files=files1, headers=_auth_headers(client)
    )
    assert resp1.status_code == 200
    assert resp1.json()["data"]["inserted"] == 1

    list1 = client.get("/api/data/orders", headers=_auth_headers(client))
    order1 = list1.json()["data"]["items"][0]
    assert order1["pay_status"] is None
    assert order1["risk_tier"] == "HIGH"
    assert order1["risk_prob"] == 75.0

    # 第二次上传（同订单号，风险概率=15 → LOW）
    files2 = {
        "file": (
            "orders.csv",
            _build_csv([_pending_row("SFO_DUP_001", risk_prob="15")]).encode("utf-8"),
            "text/csv",
        )
    }
    resp2 = client.post(
        "/api/data/upload-pending", files=files2, headers=_auth_headers(client)
    )
    assert resp2.status_code == 200
    data2 = resp2.json()["data"]
    assert data2["inserted"] == 0
    assert data2["updated"] == 1  # 重复订单更新风险概率（非 skipped）

    # 查订单：仍为 1 条，风险档已更新为 LOW
    list2 = client.get("/api/data/orders", headers=_auth_headers(client))
    assert list2.json()["data"]["total"] == 1
    order2 = list2.json()["data"]["items"][0]
    assert order2["risk_tier"] == "LOW"
    assert order2["risk_prob"] == 15.0


# ── TC-DATA-05：含空值字段存 NULL ─────────────────────────────────


def test_upload_null_values_stored_as_null(client, seed_users, db_session):
    _seed_risk_config(db_session)
    csv_text = _build_csv([_pending_row_with_nulls()])
    files = {"file": ("orders.csv", csv_text.encode("utf-8"), "text/csv")}
    resp = client.post(
        "/api/data/upload-pending", files=files, headers=_auth_headers(client)
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["inserted"] == 1

    # 验证空值字段为 NULL：查详情
    list_resp = client.get("/api/data/orders", headers=_auth_headers(client))
    order_id = list_resp.json()["data"]["items"][0]["id"]
    detail_resp = client.get(
        f"/api/data/orders/{order_id}", headers=_auth_headers(client)
    )
    assert detail_resp.status_code == 200
    feature = detail_resp.json()["data"]["feature"]
    # 历史缴费平均历时为空 → NULL
    assert feature["avg_pay_duration_days"] is None
    # 非空字段正常
    assert feature["history_fee_order_count"] == 2
    # 风险概率为空 → risk_tier None
    order = detail_resp.json()["data"]["order"]
    assert order["risk_prob"] is None
    assert order["risk_tier"] is None
    # 供应商名称无乱码
    assert order["supplier_name"] == "河南曼之达建设有限公司"


# ── TC-DATA-06：空文件返回 400 ────────────────────────────────────


def test_upload_empty_file_returns_400(client, seed_users, db_session):
    _seed_risk_config(db_session)
    files = {"file": ("empty.csv", b"", "text/csv")}
    resp = client.post(
        "/api/data/upload-pending", files=files, headers=_auth_headers(client)
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]


# ── TC-DATA-07：非 CSV 文件返回 400 ───────────────────────────────


def test_upload_non_csv_returns_400(client, seed_users, db_session):
    _seed_risk_config(db_session)
    files = {"file": ("data.txt", "hello world".encode("utf-8"), "text/plain")}
    resp = client.post(
        "/api/data/upload-pending", files=files, headers=_auth_headers(client)
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]


# ── 权限：非 ADMIN 不能上传 ────────────────────────────────────────


def test_upload_requires_admin(client, seed_users, db_session):
    _seed_risk_config(db_session)
    csv_text = _build_csv([_pending_row()])
    files = {"file": ("orders.csv", csv_text.encode("utf-8"), "text/csv")}
    resp = client.post(
        "/api/data/upload-pending",
        files=files,
        headers=_auth_headers(client, username="collector1"),
    )
    assert resp.status_code == 403


# ── 未登录不能上传 ────────────────────────────────────────────────


def test_upload_requires_auth(client, seed_users, db_session):
    _seed_risk_config(db_session)
    csv_text = _build_csv([_pending_row()])
    files = {"file": ("orders.csv", csv_text.encode("utf-8"), "text/csv")}
    resp = client.post("/api/data/upload-pending", files=files)
    assert resp.status_code == 401


# ── 已支付 CSV 导入：回写 pay_status=PAID ────────────────────────────


def test_upload_paid_csv(client, seed_users, db_session):
    """先导入待支付 → 再导入已支付 CSV → 匹配订单 pay_status=PAID。"""
    _seed_risk_config(db_session)
    # 步骤1：导入待支付订单（pay_status=None）
    pending_csv = _build_csv([_pending_row("SFO_PAID_001")])
    resp1 = client.post(
        "/api/data/upload-pending",
        files={"file": ("pending.csv", pending_csv.encode("utf-8"), "text/csv")},
        headers=_auth_headers(client),
    )
    assert resp1.status_code == 200
    assert resp1.json()["data"]["inserted"] == 1

    list1 = client.get("/api/data/orders", headers=_auth_headers(client))
    assert list1.json()["data"]["items"][0]["pay_status"] is None

    # 步骤2：导入已支付 CSV（同订单号，含支付日期+实际支付时长）
    paid_csv = "\n".join([PAID_CSV_HEADER, _paid_row("SFO_PAID_001", "2025/9/10", "7")])
    resp2 = client.post(
        "/api/data/upload-paid",
        files={"file": ("paid.csv", paid_csv.encode("utf-8"), "text/csv")},
        headers=_auth_headers(client),
    )
    assert resp2.status_code == 200, resp2.text
    data2 = resp2.json()["data"]
    assert data2["inserted"] == 0  # 已支付导入不新建订单
    assert data2["updated"] == 1  # 匹配 1 条回写
    assert data2["skipped"] == 0

    # 查订单：pay_status=PAID + pay_time + actual_pay_duration_days
    list2 = client.get("/api/data/orders", headers=_auth_headers(client))
    order = list2.json()["data"]["items"][0]
    assert order["pay_status"] == "PAID"
    assert order["actual_pay_duration_days"] == 7
    assert order["pay_time"] is not None


# ── 已支付 CSV 导入：无匹配订单 skipped ───────────────────────────


def test_upload_paid_no_match_skipped(client, seed_users, db_session):
    """已支付导入：订单号不存在 → skipped+1，不新建订单。"""
    _seed_risk_config(db_session)
    paid_csv = "\n".join(
        [PAID_CSV_HEADER, _paid_row("SFO_NOT_EXIST", "2025/9/10", "5")]
    )
    resp = client.post(
        "/api/data/upload-paid",
        files={"file": ("paid.csv", paid_csv.encode("utf-8"), "text/csv")},
        headers=_auth_headers(client),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["inserted"] == 0
    assert data["updated"] == 0
    assert data["skipped"] == 1
    assert len(data["errors"]) >= 1  # 记录"订单不存在"错误

    # 确认未新建订单
    list_resp = client.get("/api/data/orders", headers=_auth_headers(client))
    assert list_resp.json()["data"]["total"] == 0
