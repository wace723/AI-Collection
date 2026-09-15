"""data-001 CSV 上传与解析测试。

对应 docs/03-测试用例.md TC-DATA-01~07。
"""

from __future__ import annotations

import io

from app.core.security import create_access_token


# ── 测试夹具：构造最小合规 CSV（37 列） ────────────────────────────

# 37 列表头（与示例文件一致）
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

# 一行合规数据
CSV_ROW = (
    "1355714,北京恒锐建设工程有限公司,cscec2025061000001037188,"
    "SFO2025090800002398299,竞价采购,集中采购,2025/9/8,"
    "7,0,0,0,0,1,9,9,12480,69,58,11,0.1897,3,1755,0,0,"
    "10000000,1115,2566,2217,1943,劳务分包类,0.2308,0,3,7,9,0,0"
)

# 欠费样本：实际支付时长为空（NULL），30天欠费标签=1
CSV_ROW_OVERDUE = (
    "2000001,河南曼之达建设有限公司,biz002,"
    "SFO_OVERDUE_001,竞价采购,集中采购,2025/9/8,"
    ",1,1,1,1,2,15,,0,70,60,8,0.13,5,100,1,2,"
    "5000000,北京,2000,1800,1600,市政类,0.1,1,5,3,9,0,0"
)


def _login_token(client, username="admin", password="admin123") -> str:
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


def _auth_headers(client) -> dict[str, str]:
    return {"Authorization": f"Bearer {_login_token(client)}"}


def _build_csv(rows: list[str], header: str = CSV_HEADER, newline: str = "\n") -> str:
    return newline.join([header, *rows])


# ── TC-DATA-01：UTF-8 CSV 上传成功 ────────────────────────────────


def test_upload_utf8_csv_success(client, seed_users):
    # 每行用不同的 service_fee_order_no，避免去重
    rows = []
    for i in range(20):
        row = CSV_ROW.replace(
            "SFO2025090800002398299", f"SFO_TEST_{i:04d}"
        ).replace("北京恒锐建设工程有限公司", f"测试公司{i}")
        rows.append(row)
    csv_text = _build_csv(rows)
    files = {
        "file": ("orders_utf8.csv", csv_text.encode("utf-8"), "text/csv"),
    }
    resp = client.post("/api/data/upload", files=files, headers=_auth_headers(client))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["inserted"] == 20
    assert body["data"]["skipped"] == 0

    # 列表可查到 20 条
    list_resp = client.get("/api/data/orders", headers=_auth_headers(client))
    assert list_resp.status_code == 200
    assert list_resp.json()["data"]["total"] == 20


# ── TC-DATA-02：GBK 编码 CSV 上传成功（编码自动识别） ──────────────


def test_upload_gbk_csv_success(client, seed_users):
    csv_text = _build_csv([CSV_ROW])
    files = {
        "file": ("orders_gbk.csv", csv_text.encode("gbk"), "text/csv"),
    }
    resp = client.post("/api/data/upload", files=files, headers=_auth_headers(client))

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["inserted"] == 1

    # 中文无乱码
    list_resp = client.get("/api/data/orders", headers=_auth_headers(client))
    supplier_name = list_resp.json()["data"]["items"][0]["supplier_name"]
    assert supplier_name == "北京恒锐建设工程有限公司"


# ── TC-DATA-03：列数不足返回 400 ──────────────────────────────────


def test_upload_missing_columns_returns_400(client, seed_users):
    # 10 列，但故意缺少必填列「服务费订单号」
    bad_header = (
        "供应商编号,供应商名称,招标编号,招标类型,采购类型,"
        "中标日期,实际支付时长_天,标签_30天是否欠费,标签_90天是否欠费,历史平台使用费订单数"
    )
    bad_row = "1,公司A,biz1,竞价,集中,2025/9/8,7,0,0,1"
    csv_text = "\n".join([bad_header, bad_row])
    files = {"file": ("bad.csv", csv_text.encode("utf-8"), "text/csv")}

    resp = client.post("/api/data/upload", files=files, headers=_auth_headers(client))

    assert resp.status_code == 400
    body = resp.json()
    # FastAPI HTTPException 返回 {"detail": "..."}；缺失列名提示在 detail 中
    detail = body.get("detail") or body.get("error") or ""
    assert "缺失" in detail or "missing" in detail.lower()


# ── TC-DATA-04：重复订单号去重 ────────────────────────────────────


def test_upload_duplicate_updates_payment_status(client, seed_users):
    """重复上传同订单号：更新支付状态（非跳过）。

    第一次：actual_pay_duration_days 为空 → 未支付（pay_status=None）
    第二次：actual_pay_duration_days 有值 → 已支付（pay_status=PAID），updated=1
    """
    # 构造未支付行（实际支付时长_天 为空）
    row_unpaid = CSV_ROW_OVERDUE.replace("SFO_OVERDUE_001", "SFO_DUP_001")
    # 构造已支付行（同订单号，实际支付时长_天=7）
    row_paid = CSV_ROW.replace("SFO2025090800002398299", "SFO_DUP_001")

    # 第一次上传（未支付）
    files1 = {"file": ("orders.csv", _build_csv([row_unpaid]).encode("utf-8"), "text/csv")}
    resp1 = client.post("/api/data/upload", files=files1, headers=_auth_headers(client))
    assert resp1.status_code == 200
    assert resp1.json()["data"]["inserted"] == 1
    # 查订单：pay_status 应为 None（未支付）
    list1 = client.get("/api/data/orders", headers=_auth_headers(client))
    order1 = list1.json()["data"]["items"][0]
    assert order1["pay_status"] is None

    # 第二次上传（同订单号，已支付）
    files2 = {"file": ("orders.csv", _build_csv([row_paid]).encode("utf-8"), "text/csv")}
    resp2 = client.post("/api/data/upload", files=files2, headers=_auth_headers(client))
    assert resp2.status_code == 200
    data2 = resp2.json()["data"]
    assert data2["inserted"] == 0
    assert data2["updated"] == 1  # 重复订单更新支付状态（非 skipped）

    # 查订单：pay_status 应为 PAID
    list2 = client.get("/api/data/orders", headers=_auth_headers(client))
    assert list2.json()["data"]["total"] == 1  # 仍为 1 条
    order2 = list2.json()["data"]["items"][0]
    assert order2["pay_status"] == "PAID"


# ── TC-DATA-05：含空值字段存 NULL ─────────────────────────────────


def test_upload_null_values_stored_as_null(client, seed_users):
    csv_text = _build_csv([CSV_ROW_OVERDUE])
    files = {"file": ("orders.csv", csv_text.encode("utf-8"), "text/csv")}
    resp = client.post("/api/data/upload", files=files, headers=_auth_headers(client))

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["inserted"] == 1

    # 验证空值字段为 NULL：查特征详情
    list_resp = client.get("/api/data/orders", headers=_auth_headers(client))
    order_id = list_resp.json()["data"]["items"][0]["id"]
    detail_resp = client.get(
        f"/api/data/orders/{order_id}", headers=_auth_headers(client)
    )
    assert detail_resp.status_code == 200
    feature = detail_resp.json()["data"]["feature"]
    # 实际支付时长为空 → NULL
    assert feature["actual_pay_duration_days"] is None
    # 历史缴费平均历时为空 → NULL
    assert feature["avg_pay_duration_days"] is None
    # 非空字段正常
    assert feature["history_fee_order_count"] == 2
    assert feature["label_30"] == 1
    # 供应商名称无乱码
    assert detail_resp.json()["data"]["order"]["supplier_name"] == "河南曼之达建设有限公司"


# ── TC-DATA-06：空文件返回 400 ────────────────────────────────────


def test_upload_empty_file_returns_400(client, seed_users):
    files = {"file": ("empty.csv", b"", "text/csv")}
    resp = client.post("/api/data/upload", files=files, headers=_auth_headers(client))

    assert resp.status_code == 400
    assert resp.json()["detail"]


# ── TC-DATA-07：非 CSV 文件返回 400 ───────────────────────────────


def test_upload_non_csv_returns_400(client, seed_users):
    files = {"file": ("data.txt", "hello world".encode("utf-8"), "text/plain")}
    resp = client.post("/api/data/upload", files=files, headers=_auth_headers(client))

    assert resp.status_code == 400
    assert resp.json()["detail"]


# ── 权限：非 ADMIN 不能上传 ────────────────────────────────────────


def test_upload_requires_admin(client, seed_users):
    # 用 collector 登录
    resp = client.post(
        "/api/auth/login", json={"username": "collector1", "password": "admin123"}
    )
    collector_token = resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {collector_token}"}

    csv_text = _build_csv([CSV_ROW])
    files = {"file": ("orders.csv", csv_text.encode("utf-8"), "text/csv")}
    resp = client.post("/api/data/upload", files=files, headers=headers)

    assert resp.status_code == 403


# ── 未登录不能上传 ────────────────────────────────────────────────


def test_upload_requires_auth(client, seed_users):
    csv_text = _build_csv([CSV_ROW])
    files = {"file": ("orders.csv", csv_text.encode("utf-8"), "text/csv")}
    resp = client.post("/api/data/upload", files=files)
    assert resp.status_code == 401
