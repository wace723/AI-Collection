"""演示数据一键生成脚本。

功能：
1. 清库（删 orders/order_features/tasks/task_results，保留 users/risk_configs/talk_templates/ai_config）
2. 调用 seed.seed() 确保用户+配置+话术就绪（幂等）
3. 生成 3 个 CSV 到 ../演示数据/（待支付 T 时 300 / 待支付 T+1 新增 30 / 已支付 T+1 30）
4. 预置 14 天历史数据（直接插库：30 条 PAID 订单 + 30 个 DONE Task + 30 条 REACHED TaskResult）
5. 打印操作指引 + 写 演示操作手册.md

用法：在 backend/ 目录下运行 `python demo_setup.py`。幂等可重跑。

时间基准：
- T = 2026-10-08（演示 T 时：系统时间调到 10-08）
- T+1 = 2026-10-09（演示 T+1：系统时间调到 10-09）
- 历史 14 天窗口对齐 10-09 为「今天」，覆盖两次演示

关键约束：
- 历史订单必须 pay_status=PAID（跑批跳过 PAID 订单，保住其 Task+TaskResult 不被删）
- 历史 Task 必须 status=DONE（终态）
- 历史 TaskResult.created_at 显式回填到过去 14 天（驱动大盘趋势）
- CSV 风险概率是档位唯一来源（导入用 recalc_risk=False，演示时禁止手动跑批）
"""

from __future__ import annotations

import csv
import random
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import text

from app.core.database import SessionLocal
from app.models.order import Order, OrderFeature
from app.models.task import Task, TaskResult
from app.services.data_ingestion.columns import (
    PAID_ORDER_COLUMNS,
    PENDING_ORDER_COLUMNS,
)
from app.services.task_engine.states import (
    DONE,
    FINALIZED,
    NO_NEED,
    REACHED,
)

# ── 时间基准 ──────────────────────────────────────────────────────
T_DATE = date(2026, 10, 8)          # T 时
T1_DATE = date(2026, 10, 9)         # T+1
TODAY_FOR_HISTORY = T1_DATE         # 历史窗口对齐 10-09（覆盖两次演示）

# ── 催收员 ID（DB 实测：3=collector1, 4=collector2, 5=collector3） ──
COLLECTOR_IDS = [3, 4, 5]

# ── 输出目录（backend/ 上一级） ────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent
DEMO_DIR = BACKEND_DIR.parent / "演示数据"

# ── 随机种子（可复现） ────────────────────────────────────────────
RNG_SEED = 20261008

# ── 字段取值池（贴近真实样本） ────────────────────────────────────
SUPPLIER_PREFIXES = [
    "北京", "上海", "广州", "深圳", "杭州", "成都", "重庆", "武汉",
    "南京", "苏州", "西安", "长沙", "青岛", "大连", "郑州", "合肥",
    "福州", "厦门", "昆明", "贵阳", "南昌", "济南", "沈阳", "哈尔滨",
    "石家庄", "太原", "兰州", "银川", "南宁", "海口",
]
SUPPLIER_CORES = [
    "恒锐", "中盛建", "宏源", "鼎诚", "华远", "瑞通", "泰昌", "金毅成",
    "盛润合", "迈诺", "启正", "木图", "晨越", "巴华", "雄安东", "迈达",
    "建工", "市政", "机电", "装饰", "科技", "建材", "工程", "实业",
]
SUPPLIER_SUFFIXES = ["有限公司", "股份有限公司", "集团有限公司", "建设有限公司"]
TENDER_TYPES = ["公开招标", "竞价采购", "邀请招标", "询比采购"]
PURCHASE_TYPES = ["招标采购", "区域联采", "分散采购", "集中采购"]
BID_CATEGORIES = ["设备", "专业分包", "劳务分包", "物资", "专业服务", "租赁"]
CONTRACT_TYPES = ["框架协议", "招标采购合同"]
ENGINEERING_BUREAUS = [
    "中国建筑第一工程局有限公司",
    "中国建筑第二工程局有限公司",
    "中国建筑第三工程局有限公司",
    "中国建筑第四工程局有限公司",
    "中国建筑第五工程局有限公司",
    "中国建筑第六工程局有限公司",
    "中国建筑第七工程局有限公司",
    "中国建筑第八工程局有限公司",
]
SUBSIDIARY_TEMPLATES = [
    "中建{N}局第一建设有限公司",
    "中建{N}局第二建设有限公司",
    "中建{N}局第{M}分公司",
    "中建{N}局总承包公司",
    "中建{N}局安装工程有限公司",
]
PROJECT_NAMES = [
    "市政道路及配套管网工程",
    "综合体机电安装工程",
    "学校新校区建设项目",
    "医院综合楼施工总承包",
    "产业园基础设施采购",
    "高速公路服务区改造工程",
    "水厂扩建及管网敷设工程",
    "体育馆幕墙供应工程",
    "数据中心弱电系统工程",
    "保障房主体施工专业分包",
    "轨道交通车站装饰装修工程",
    "污水处理厂设备采购",
    "桥梁加固及附属设施工程",
    "片区综合开发基础设施项目",
    "智慧园区智能化系统工程",
]
REGION_TO_PROVINCES = {
    "华东地区": ["江苏省", "浙江省", "安徽省", "福建省", "山东省"],
    "华南地区": ["广东省", "广西壮族自治区", "海南省"],
    "西南地区": ["重庆市", "四川省", "贵州省", "云南省"],
    "华北地区": ["北京市", "天津市", "河北省", "山西省", "内蒙古自治区"],
    "东北地区": ["辽宁省", "吉林省", "黑龙江省"],
    "西北地区": ["陕西省", "甘肃省", "青海省", "宁夏回族自治区", "新疆维吾尔自治区"],
    "华中地区": ["河南省", "湖北省", "湖南省"],
}


def _gen_supplier_no(rng: random.Random, idx: int) -> str:
    """6-8 位供应商编号。"""
    return f"{1000000 + idx * 37 + rng.randint(1, 9999)}"


def _gen_supplier_name(rng: random.Random) -> str:
    pre = rng.choice(SUPPLIER_PREFIXES)
    core = rng.choice(SUPPLIER_CORES)
    suf = rng.choice(SUPPLIER_SUFFIXES)
    mid = rng.choice(["", "科技", "建设"])
    return f"{pre}{core}{mid}{suf}"


def _gen_biz_no(rng: random.Random, d: date) -> str:
    return f"cscec{d.strftime('%Y%m%d')}0000{rng.randint(100000, 999999)}"


def _gen_service_fee_order_no(prefix_date: date, tag: str, idx: int) -> str:
    """全局唯一服务费订单号。tag 区分命名空间（D=T时 / N=T+1新增 / HIST=历史）。"""
    return f"SFO{prefix_date.strftime('%Y%m%d')}{tag}{idx:04d}"


def _gen_subject_name(rng: random.Random) -> str:
    bureau = rng.choice(ENGINEERING_BUREAUS)
    proj = rng.choice(PROJECT_NAMES)
    return f"{bureau}{proj}"


def _gen_bureau_subsidiary(rng: random.Random) -> tuple[str, str]:
    n = rng.randint(1, 8)
    bureau = f"中国建筑第{_cn_num(n)}工程局有限公司"
    tpl = rng.choice(SUBSIDIARY_TEMPLATES)
    sub = tpl.format(N=_cn_num(n), M=rng.randint(1, 5))
    return bureau, sub


_CN_NUMS = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]


def _cn_num(n: int) -> str:
    return _CN_NUMS[n] if 0 <= n < len(_CN_NUMS) else str(n)


def _gen_region_province(rng: random.Random) -> tuple[str, str]:
    region = rng.choice(list(REGION_TO_PROVINCES.keys()))
    province = rng.choice(REGION_TO_PROVINCES[region])
    return region, province


# ── T 时 300 条中标日期分配（决定生成哪一轮任务 + T+1 演进） ──────
# (risk_tier, count, win_bid_date_fn_key)
# T=2026-10-08，age_days = T - win_bid_date
# HIGH day_offset=[7,15,30], MEDIUM=[30], LOW=[90]


def _t_date_alloc() -> list[tuple[str, date]]:
    """返回 T 时 300 条的 (risk_tier, win_bid_date) 列表。"""
    rng = random.Random(RNG_SEED)
    alloc: list[tuple[str, date]] = []

    def add(tier: str, win_bid: date, n: int) -> None:
        for _ in range(n):
            alloc.append((tier, win_bid))

    # HIGH 30 条
    add("HIGH", T_DATE - timedelta(days=rng.randint(7, 14)), 12)   # ROUND_1
    add("HIGH", T_DATE - timedelta(days=rng.randint(15, 29)), 9)   # ROUND_2
    add("HIGH", T_DATE - timedelta(days=rng.randint(30, 60)), 9)   # ROUND_3
    # MEDIUM 90 条
    add("MEDIUM", T_DATE - timedelta(days=rng.randint(30, 60)), 54)  # ROUND_1
    add("MEDIUM", T_DATE - timedelta(days=29), 18)                  # T时NO_NEED→T+1到期(age 29→30)
    add("MEDIUM", T_DATE - timedelta(days=rng.randint(0, 28)), 18)  # 仍NO_NEED
    # LOW 180 条
    add("LOW", T_DATE - timedelta(days=rng.randint(90, 120)), 75)    # ROUND_1
    add("LOW", T_DATE - timedelta(days=89), 27)                     # T时NO_NEED→T+1到期(age 89→90)
    add("LOW", T_DATE - timedelta(days=rng.randint(0, 88)), 78)      # 仍NO_NEED

    rng.shuffle(alloc)
    return alloc


def _build_pending_row(
    rng: random.Random,
    *,
    supplier_no: str,
    supplier_name: str,
    biz_no: str,
    order_no: str,
    win_bid: date,
    risk_prob: float,
) -> dict[str, str]:
    """构造一行待支付 CSV（40 列）。"""
    bureau, sub = _gen_bureau_subsidiary(rng)
    region, province = _gen_region_province(rng)
    subject = _gen_subject_name(rng)
    estimate = rng.randint(600000, 32000000)

    # 缴费历史（0 居多，贴近真实样本）
    fee_orders = rng.choices([0, 1, 2, 3, 5], weights=[60, 15, 10, 10, 5])[0]
    if fee_orders > 0:
        last_dur = rng.randint(1, 180)
        avg_dur = round(rng.uniform(1, last_dur), 4)
        hist_pay_amt = round(rng.uniform(1000, 50000), 2)
    else:
        last_dur = None
        avg_dur = None
        hist_pay_amt = 0.0

    signup = rng.randint(1, 30)
    bidding = rng.randint(1, 50)
    win_cnt = rng.randint(0, min(10, bidding))
    win_rate = round(win_cnt / bidding, 4) if bidding else 0.0
    active_90d = rng.randint(0, 15)
    first_win_interval = rng.choice([None, rng.randint(1, 4000)])
    is_member = 1 if rng.random() < 0.1 else 0
    member_buy = rng.randint(1, 3) if is_member else 0
    register_fund = rng.randint(1000000, 300000000)
    reg_interval = rng.randint(10, 5000)
    in_interval = rng.randint(10, 5000)
    entry_interval = rng.randint(10, 5000)
    ads_win_rate = round(rng.uniform(0, 1), 4)
    hq_cnt = rng.randint(0, 3)
    coop_org = rng.randint(1, 5)
    total_proj = rng.randint(1, 10)

    month = win_bid.month
    is_month_end = 1 if win_bid.day >= 25 else 0
    is_quarter_end = 1 if (is_month_end and month in (3, 6, 9, 12)) else 0

    def fmt(v) -> str:
        if v is None:
            return ""
        return str(v)

    return {
        "供应商编号": supplier_no,
        "供应商名称": supplier_name,
        "招标编号": biz_no,
        "服务费订单号": order_no,
        "标的名称": subject,
        "招标类型": rng.choice(TENDER_TYPES),
        "采购类型": rng.choice(PURCHASE_TYPES),
        "中标品类": rng.choice(BID_CATEGORIES),
        "合同类型": rng.choice(CONTRACT_TYPES),
        "标的概算金额": fmt(estimate),
        "工程局单位": bureau,
        "下属单位": sub,
        "中标日期": win_bid.strftime("%Y-%m-%d"),
        "订单生成日期": win_bid.strftime("%Y-%m-%d"),
        "历史平台使用费订单数": fmt(fee_orders),
        "上次缴费历时_天": fmt(last_dur),
        "历史缴费平均历时_天": fmt(avg_dur),
        "服务市场历史支付金额": fmt(hist_pay_amt),
        "历史报名次数": fmt(signup),
        "历史投标次数": fmt(bidding),
        "历史中标次数": fmt(win_cnt),
        "历史中标率": fmt(win_rate),
        "近90天投标活跃度": fmt(active_90d),
        "首次中标距本次间隔_天": fmt(first_win_interval),
        "中标时是否会员": fmt(is_member),
        "中标前购买会员次数": fmt(member_buy),
        "注册资金": fmt(register_fund),
        "注册地区": region,
        "注册省份": province,
        "注册时间距中标间隔_天": fmt(reg_interval),
        "平台入驻时间距中标间隔_天": fmt(in_interval),
        "最早入库时间距中标间隔_天": fmt(entry_interval),
        "标签表历史中标率": fmt(ads_win_rate),
        "股份优质评级次数": fmt(hq_cnt),
        "合作单位数量": fmt(coop_org),
        "累计履约项目数": fmt(total_proj),
        "中标月份": fmt(month),
        "是否月末": fmt(is_month_end),
        "是否季末": fmt(is_quarter_end),
        "风险概率": fmt(risk_prob),
    }


def _risk_prob_for_tier(tier: str, rng: random.Random) -> float:
    """按风险档生成风险概率（确保映射到目标档位）。阈值 70/30。"""
    if tier == "HIGH":
        return float(rng.randint(70, 95))
    if tier == "MEDIUM":
        return float(rng.randint(30, 69))
    return float(rng.randint(0, 29))


def gen_pending_t_csv() -> list[dict[str, str]]:
    """生成 T 时 300 条待支付订单行。返回行列表（含全局唯一订单号）。"""
    rng = random.Random(RNG_SEED)
    alloc = _t_date_alloc()  # 300 条
    rows: list[dict[str, str]] = []
    for idx, (tier, win_bid) in enumerate(alloc, start=1):
        order_no = _gen_service_fee_order_no(T_DATE, "D", idx)
        supplier_no = _gen_supplier_no(rng, idx)
        supplier_name = _gen_supplier_name(rng)
        biz_no = _gen_biz_no(rng, win_bid)
        risk_prob = _risk_prob_for_tier(tier, rng)
        rows.append(
            _build_pending_row(
                rng,
                supplier_no=supplier_no,
                supplier_name=supplier_name,
                biz_no=biz_no,
                order_no=order_no,
                win_bid=win_bid,
                risk_prob=risk_prob,
            )
        )
    return rows


def gen_pending_t1_csv(t_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """生成 T+1 新增 30 条待支付订单行（中标日=T+1，全部 NO_NEED）。"""
    rng = random.Random(RNG_SEED + 1)
    rows: list[dict[str, str]] = []
    # T+1 风险档随机分布
    tiers = ["HIGH"] * 3 + ["MEDIUM"] * 9 + ["LOW"] * 18
    rng.shuffle(tiers)
    for idx, tier in enumerate(tiers, start=1):
        order_no = _gen_service_fee_order_no(T1_DATE, "N", idx)
        supplier_no = _gen_supplier_no(rng, idx + 10000)
        supplier_name = _gen_supplier_name(rng)
        win_bid = T1_DATE
        biz_no = _gen_biz_no(rng, win_bid)
        risk_prob = _risk_prob_for_tier(tier, rng)
        rows.append(
            _build_pending_row(
                rng,
                supplier_no=supplier_no,
                supplier_name=supplier_name,
                biz_no=biz_no,
                order_no=order_no,
                win_bid=win_bid,
                risk_prob=risk_prob,
            )
        )
    return rows


def gen_paid_t1_csv(t_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """生成 T+1 已支付 30 条：从 T 时挑 30 条已生成任务的订单号回写支付。

    已支付 CSV（40 列）：多支付日期/实际支付时长，无订单生成日期/风险概率。
    """
    rng = random.Random(RNG_SEED + 2)
    # 从 T 时挑 30 条已生成任务的订单（HIGH 9 + MEDIUM 9 + LOW 12）
    # T 时已生成任务的：HIGH 全 30 条（age≥7），MEDIUM age≥30 的 54 条，LOW age≥90 的 75 条
    def parse_winbid(row: dict[str, str]) -> date:
        return datetime.strptime(row["中标日期"], "%Y-%m-%d").date()

    t_high = [r for r in t_rows if float(r["风险概率"]) >= 70]
    t_med = [r for r in t_rows if 30 <= float(r["风险概率"]) < 70
             and (T_DATE - parse_winbid(r)).days >= 30]
    t_low = [r for r in t_rows if float(r["风险概率"]) < 30
             and (T_DATE - parse_winbid(r)).days >= 90]
    rng.shuffle(t_high)
    rng.shuffle(t_med)
    rng.shuffle(t_low)
    picked = t_high[:9] + t_med[:9] + t_low[:12]
    assert len(picked) == 30, f"挑选数量不足: {len(picked)}"

    rows: list[dict[str, str]] = []
    for i, src in enumerate(picked):
        win_bid = parse_winbid(src)
        pay_dt = datetime(2026, 10, 9, 10 + (i % 7), (i * 7) % 60, 0)
        actual_dur = (T1_DATE - win_bid).days
        rows.append({
            "供应商编号": src["供应商编号"],
            "供应商名称": src["供应商名称"],
            "招标编号": src["招标编号"],
            "服务费订单号": src["服务费订单号"],
            "标的名称": src["标的名称"],
            "招标类型": src["招标类型"],
            "采购类型": src["采购类型"],
            "中标品类": src["中标品类"],
            "合同类型": src["合同类型"],
            "标的概算金额": src["标的概算金额"],
            "工程局单位": src["工程局单位"],
            "下属单位": src["下属单位"],
            "中标日期": src["中标日期"],
            "支付日期": pay_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "实际支付时长_天": str(actual_dur),
            "历史平台使用费订单数": src["历史平台使用费订单数"],
            "上次缴费历时_天": src["上次缴费历时_天"],
            "历史缴费平均历时_天": src["历史缴费平均历时_天"],
            "服务市场历史支付金额": src["服务市场历史支付金额"],
            "历史报名次数": src["历史报名次数"],
            "历史投标次数": src["历史投标次数"],
            "历史中标次数": src["历史中标次数"],
            "历史中标率": src["历史中标率"],
            "近90天投标活跃度": src["近90天投标活跃度"],
            "首次中标距本次间隔_天": src["首次中标距本次间隔_天"],
            "中标时是否会员": src["中标时是否会员"],
            "中标前购买会员次数": src["中标前购买会员次数"],
            "注册资金": src["注册资金"],
            "注册地区": src["注册地区"],
            "注册省份": src["注册省份"],
            "注册时间距中标间隔_天": src["注册时间距中标间隔_天"],
            "平台入驻时间距中标间隔_天": src["平台入驻时间距中标间隔_天"],
            "最早入库时间距中标间隔_天": src["最早入库时间距中标间隔_天"],
            "标签表历史中标率": src["标签表历史中标率"],
            "股份优质评级次数": src["股份优质评级次数"],
            "合作单位数量": src["合作单位数量"],
            "累计履约项目数": src["累计履约项目数"],
            "中标月份": src["中标月份"],
            "是否月末": src["是否月末"],
            "是否季末": src["是否季末"],
        })
    return rows


def _write_csv(path: Path, header: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    """写 CSV（utf-8-sig，Excel 友好，表头严格按 header）。"""
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(header))
        writer.writeheader()
        for r in rows:
            # 只写 header 列，忽略多余 key
            writer.writerow({k: r.get(k, "") for k in header})


# ── 14 天历史数据预置（直接插库） ─────────────────────────────────


def _history_distribution() -> list[tuple[date, int, int, int]]:
    """返回 [(date, c1_count, c2_count, c3_count), ...]，共 30 条按 14 天分布。

    以 TODAY_FOR_HISTORY(10-09) 为今天，周窗口 10-03~10-09，月窗口 10-01~10-09。
    合计 c1=13, c2=10, c3=7。
    """
    # (日期, c1, c2, c3) —— c1=collector1(id3), c2=collector2(id4), c3=collector3(id5)
    return [
        (date(2026, 9, 26), 0, 1, 0),
        (date(2026, 9, 27), 1, 0, 0),
        (date(2026, 9, 28), 1, 0, 1),
        (date(2026, 9, 29), 1, 1, 0),
        (date(2026, 9, 30), 0, 1, 1),
        (date(2026, 10, 1), 2, 1, 0),
        (date(2026, 10, 2), 1, 1, 1),
        (date(2026, 10, 3), 1, 0, 1),
        (date(2026, 10, 4), 0, 1, 1),
        (date(2026, 10, 5), 2, 1, 0),
        (date(2026, 10, 6), 1, 1, 1),
        (date(2026, 10, 7), 1, 0, 1),
        (date(2026, 10, 8), 1, 1, 0),
        (date(2026, 10, 9), 1, 1, 0),
    ]


def seed_history(db) -> dict:
    """预置 14 天历史数据：30 条 PAID 订单 + 30 个 DONE Task + 30 条 REACHED TaskResult。

    历史订单全部 PAID+FINALIZED（跑批跳过 PAID，保住 Task+TaskResult）。
    TaskResult.created_at 显式回填到过去 14 天驱动大盘趋势。
    """
    rng = random.Random(RNG_SEED + 3)
    dist = _history_distribution()

    # 展开成 [(date, collector_id), ...] 共 30 条
    schedule: list[tuple[date, int]] = []
    for d, c1, c2, c3 in dist:
        schedule.extend([(d, COLLECTOR_IDS[0])] * c1)
        schedule.extend([(d, COLLECTOR_IDS[1])] * c2)
        schedule.extend([(d, COLLECTOR_IDS[2])] * c3)
    assert len(schedule) == 30

    # 历史 30 条订单三档各 10
    tiers = ["HIGH"] * 10 + ["MEDIUM"] * 10 + ["LOW"] * 10
    rng.shuffle(tiers)

    for i, (d, collector_id) in enumerate(schedule):
        tier = tiers[i]
        win_bid: date
        if tier == "HIGH":
            win_bid = date(2026, 6, 1) + timedelta(days=rng.randint(0, 60))
            scene = "ROUND_3"
            day_offset = 30
        elif tier == "MEDIUM":
            win_bid = date(2026, 6, 1) + timedelta(days=rng.randint(0, 60))
            scene = "ROUND_1"
            day_offset = 30
        else:  # LOW
            win_bid = date(2026, 6, 1) + timedelta(days=rng.randint(0, 29))
            scene = "ROUND_1"
            day_offset = 90

        order_no = _gen_service_fee_order_no(date(2026, 6, 1), "HIST", i + 1)
        supplier_name = _gen_supplier_name(rng)
        subject = _gen_subject_name(rng)
        bureau, sub = _gen_bureau_subsidiary(rng)
        region, province = _gen_region_province(rng)
        risk_prob = _risk_prob_for_tier(tier, rng)

        # 历史 TaskResult.created_at（驱动大盘趋势）
        result_dt = datetime(d.year, d.month, d.day, 14, (i * 7) % 60, 0)
        # 历史 Task.created_at（早于 result，设回填日 09:00）
        task_created = datetime(d.year, d.month, d.day, 9, 0, 0)

        order = Order(
            supplier_no=_gen_supplier_no(rng, i + 20000),
            supplier_name=supplier_name,
            biz_no=_gen_biz_no(rng, win_bid),
            service_fee_order_no=order_no,
            subject_name=subject,
            tender_type_desc=rng.choice(TENDER_TYPES),
            purchase_type_desc=rng.choice(PURCHASE_TYPES),
            bid_category=rng.choice(BID_CATEGORIES),
            contract_type=rng.choice(CONTRACT_TYPES),
            subject_estimate_amount=rng.randint(600000, 32000000),
            engineering_bureau=bureau,
            subsidiary=sub,
            win_bid_date=win_bid,
            register_area=region,
            register_province=province,
            pay_status="PAID",
            pay_time=result_dt,
            actual_pay_duration_days=(result_dt.date() - win_bid).days,
            risk_prob=risk_prob,
            risk_tier=tier,
            risk_import_time=datetime(2026, 6, 1),
            collection_state=FINALIZED,
        )
        db.add(order)
        db.flush()

        # OrderFeature（历史订单也填特征，便于详情展示）
        feature = OrderFeature(
            order_id=order.id,
            history_fee_order_count=rng.randint(0, 3),
            signup_count=rng.randint(1, 30),
            bidding_count=rng.randint(1, 50),
            win_count=rng.randint(0, 10),
            win_rate=round(rng.uniform(0, 0.5), 4),
            active_90d=rng.randint(0, 15),
            is_member_at_win=rng.random() < 0.1,
            register_fund=rng.randint(1000000, 300000000),
            cooperate_org_num=rng.randint(1, 5),
            total_perform_project_num=rng.randint(1, 10),
        )
        db.add(feature)

        task = Task(
            order_id=order.id,
            service_fee_order_no=order_no,
            risk_tier=tier,
            scene=scene,
            day_offset=day_offset,
            due_date=win_bid + timedelta(days=day_offset),
            status=DONE,
            assignee_id=collector_id,
            assigned_at=task_created,
            result=REACHED,
            batch_id=f"hist-{d.isoformat()}",
            created_at=task_created,
        )
        db.add(task)
        db.flush()

        task_result = TaskResult(
            task_id=task.id,
            collector_id=collector_id,
            result=REACHED,
            note="客户确认缴费，已催回",
            created_at=result_dt,
        )
        db.add(task_result)

    db.commit()
    return {"history_orders": 30, "history_tasks": 30, "history_results": 30}


# ── 清库 ─────────────────────────────────────────────────────────


def clean_db(db) -> None:
    """清库：删业务数据，保留配置（users/risk_configs/talk_templates/ai_config）。"""
    db.execute(text("DELETE FROM task_results"))
    db.execute(text("DELETE FROM tasks"))
    db.execute(text("DELETE FROM order_features"))
    db.execute(text("DELETE FROM orders"))
    db.execute(text("DELETE FROM ai_conversations"))
    db.commit()


# ── 操作手册 ────────────────────────────────────────────────────


def write_demo_guide(pending_t_count: int, pending_t1_count: int,
                     paid_count: int) -> None:
    """写演示操作手册.md 到 演示数据/ 目录。"""
    guide = f"""# 平台使用费 AI 辅助催收系统 — 演示操作手册

## 演示前准备

```bash
# 1. 生成演示数据（清库 + 生成 CSV + 预置 14 天历史）
cd backend
python demo_setup.py

# 2. 启动后端（系统时间调到 2026-10-08）
cd backend
uvicorn app.main:app --reload --port 8123

# 3. 启动前端
cd frontend
npm run dev
```

## 账号

| 角色 | 账号 | 密码 |
|---|---|---|
| 管理员 | admin | admin123 |
| 催收主管 | supervisor | admin123 |
| 催收员1 | collector1 | admin123 |
| 催收员2 | collector2 | admin123 |
| 催收员3 | collector3 | admin123 |

## 演示数据概览

| 文件 | 条数 | 说明 |
|---|---|---|
| 01_待支付_T时_300条.csv | {pending_t_count} | T 时存量待支付，导入后生成 159 条任务 |
| 02_待支付_T+1新增_30条.csv | {pending_t1_count} | T+1 新订单，全部 NO_NEED |
| 03_已支付_T+1_30条.csv | {paid_count} | 从 T 时挑 30 条回写支付 |

历史 14 天数据已预置：30 条已支付订单 + 30 个已完成任务 + 30 条回填记录（驱动大盘趋势）。

## ⚠️ 演示注意事项

1. **演示时禁止点击「手动跑批」按钮**（该接口默认 recalc=true，会误触已废弃的 Mock 重算路径，覆盖 CSV 导入的风险档，打乱 1:3:6 比例）。系统的风险概率已由 CSV「风险概率」列导入，跑批默认 recalc_risk=False 不重算，正常流程不受影响
2. **系统时间调整**：演示 T 时调到 2026-10-08，演示 T+1 调到 2026-10-09
3. 跑批靠系统启动自动触发 + 调系统时间后重启触发，不依赖手动跑批

## 第一阶段：T 时演示（系统时间 = 2026-10-08）

### Step 1: 登录系统
- 打开前端 http://localhost:5173
- 用 admin/admin123 登录

### Step 2: 导入 T 时待支付订单
- 进入「配置后台」→「数据导入」Tab
- 在「待支付订单导入」区域，上传 `01_待支付_T时_300条.csv`
- 预期弹窗：新增入库 300，跑批生成任务 159，风险档分布 HIGH:30/MEDIUM:54:LOW:75
- 导入后系统自动跑批生成 159 条任务（PENDING_ASSIGN，待分配）

### Step 2b: 触发任务分配
- 导入只自动跑批生成任务，不自动分配。需触发分配（任选其一）：
  - **方式1**：重启后端（启动跑批+分配，历史 PAID 不受影响）
  - **方式2**：用 supervisor 登录，进入「任务统计」Tab → 点「自动分配」按钮
  - **方式3**（管理员）：访问 Swagger `/docs`，POST `/api/tasks/assign/run`
- 分配后 159 条任务分给 collector1/2/3 各 53 条，状态变 IN_PROGRESS

### Step 3: 查看数据大盘
- 用 supervisor 登录，进入「数据大盘」
- **日大盘**：当日新增任务 161（159 + 历史 2），回款数 2（历史），未支付 300，风险分布 HIGH30/MEDIUM90/LOW180
- **周大盘**：7 天趋势图有起伏（每天 2-3 回款），催收员排名 collector1(7) > collector2(5) = collector3(5)
- **月大盘**：月度回款 20，各档催收效果 HIGH/MEDIUM/LOW 有数据

### Step 4: 查看任务分配
- 用 admin 登录，进入「任务管理」
- 159 条任务 status=IN_PROGRESS，按风险档 HIGH 优先排序
- 分配给 collector1/2/3 各约 53 条

### Step 5: 演示催收员工作台
- 用 collector1/admin123 登录，进入工作台
- 待办列表仅显示分配给自己的约 53 条任务，按 HIGH>MEDIUM>LOW + 账龄排序
- 点开一条任务看：订单信息 + 用户特征画像 + 推荐话术（二维匹配）+ AI 话术生成

### Step 6: 演示话术配置
- 用 admin 登录，进入「配置后台」→「话术配置」Tab
- 覆盖度矩阵（风险档×轮次），缺口高亮，点击格子编辑固定话术 / AI 提示词
- 44 个占位符变量可插入

### Step 7: 演示风险档配置
- 进入「风险档配置」Tab
- 当前配置：阈值 70/30，催收时点 HIGH(7/15/30)/MEDIUM(30)/LOW(90)
- 历史版本回滚演示；改阈值触发话术覆盖度联动提示

## 第二阶段：T+1 演示（系统时间调到 2026-10-09，重启后端）

### Step 8: 导入 T+1 新增订单
- 用 admin 登录，「配置后台」→「数据导入」
- 上传 `02_待支付_T+1新增_30条.csv`
- 预期：新增入库 30，跑批生成 0（全部 NO_NEED，未到首轮）
- 订单总数 330，未支付 330

### Step 9: 查看 T+1 自动到期演进
- 重启后端后（系统时间 10-09），启动跑批自动推进
- **18 条 MEDIUM**（中标日 09-10，age 29→30）跨过首轮 → 生成 18 条 ROUND_1 任务
- **27 条 LOW**（中标日 07-11，age 89→90）跨过首轮 → 生成 27 条 ROUND_1 任务
- 共 45 条新任务自动生成，展示「待支付订单到期自动催收」演进
- 启动同时自动分配这 45 条新任务给 3 名催收员

### Step 10: 导入 T+1 已支付订单
- 上传 `03_已支付_T+1_30条.csv`
- 预期：回写支付状态 30，这 30 条订单 FINALIZED，活跃任务被删
- 未支付订单从 330 降至 300

### Step 11: 查看 T+1 变化
- 数据大盘日大盘：未支付 300，新增任务 45（自动到期），FINALIZED 升至 60
- 任务管理：新增 45 条 IN_PROGRESS 任务（如未自动分配，见 Step 2b 方式触发分配）

## 验证 SQL（可选）

```sql
-- 历史数据（脚本运行后）
SELECT pay_status, collection_state, COUNT(*) FROM orders GROUP BY pay_status, collection_state;
-- 预期：PAID/FINALIZED = 30

-- T 时导入后
SELECT risk_tier, COUNT(*) FROM orders WHERE pay_status IS NULL OR pay_status!='PAID' GROUP BY risk_tier;
-- 预期：HIGH=30, MEDIUM=90, LOW=180

SELECT status, COUNT(*) FROM tasks GROUP BY status;
-- 预期：IN_PROGRESS=159, DONE=30

-- 催收员历史回款分布
SELECT collector_id, COUNT(*) FROM task_results WHERE result='REACHED' GROUP BY collector_id;
-- 预期：3=13, 4=10, 5=7
```
"""
    path = DEMO_DIR / "演示操作手册.md"
    path.write_text(guide, encoding="utf-8")


# ── 主流程 ──────────────────────────────────────────────────────


def main() -> None:
    DEMO_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("平台使用费 AI 辅助催收系统 — 演示数据生成")
    print("=" * 60)

    # 1. 生成 CSV（先在内存生成，清库后插历史，最后写文件）
    print("\n[1/5] 生成 T 时待支付 CSV 行...")
    pending_t_rows = gen_pending_t_csv()
    print(f"      T 时待支付: {len(pending_t_rows)} 条")

    print("[2/5] 生成 T+1 新增待支付 CSV 行...")
    pending_t1_rows = gen_pending_t1_csv(pending_t_rows)
    print(f"      T+1 新增: {len(pending_t1_rows)} 条")

    print("[3/5] 生成 T+1 已支付 CSV 行...")
    paid_t1_rows = gen_paid_t1_csv(pending_t_rows)
    print(f"      T+1 已支付: {len(paid_t1_rows)} 条")

    # 写 CSV 文件
    print("\n[4/5] 写 CSV 文件到 演示数据/ 目录...")
    _write_csv(DEMO_DIR / "01_待支付_T时_300条.csv", PENDING_ORDER_COLUMNS, pending_t_rows)
    _write_csv(DEMO_DIR / "02_待支付_T+1新增_30条.csv", PENDING_ORDER_COLUMNS, pending_t1_rows)
    _write_csv(DEMO_DIR / "03_已支付_T+1_30条.csv", PAID_ORDER_COLUMNS, paid_t1_rows)
    print(f"      写入 3 个 CSV 到 {DEMO_DIR}")

    # 2. 清库 + 预置历史
    print("\n[5/5] 清库 + 预置 14 天历史数据...")
    db = SessionLocal()
    try:
        clean_db(db)
        print("      业务数据已清空（保留用户/配置/话术）")

        # 调用 seed 确保配置就绪（幂等）
        from seed import seed
        seed()

        hist = seed_history(db)
        print(f"      历史订单: {hist['history_orders']} 条")
        print(f"      历史任务: {hist['history_tasks']} 个 (DONE)")
        print(f"      历史回填: {hist['history_results']} 条 (REACHED, 分布 14 天)")
    finally:
        db.close()

    # 3. 写操作手册
    write_demo_guide(len(pending_t_rows), len(pending_t1_rows), len(paid_t1_rows))

    print("\n" + "=" * 60)
    print("✅ 演示数据生成完成！")
    print("=" * 60)
    print(f"\n📁 CSV 文件: {DEMO_DIR}")
    print("   - 01_待支付_T时_300条.csv")
    print("   - 02_待支付_T+1新增_30条.csv")
    print("   - 03_已支付_T+1_30条.csv")
    print(f"   - 演示操作手册.md")
    print("\n📅 历史 14 天数据已预置（30 条已支付订单 + 30 个已完成任务）")
    print("\n🚀 演示步骤:")
    print("   1. 调系统时间到 2026-10-08，启动后端：uvicorn app.main:app --reload --port 8123")
    print("   2. 启动前端：cd frontend && npm run dev")
    print("   3. admin/admin123 登录，导入 01_待支付_T时_300条.csv")
    print("   4. 查看任务/大盘/工作台/话术配置")
    print("   5. 调系统时间到 2026-10-09，重启后端，导入 02/03 CSV")
    print("\n⚠️ 演示时禁止点「手动跑批」按钮（默认 recalc=true 会误触废弃的 Mock 重算路径覆盖档位）")
    print(f"\n📖 详细操作见: {DEMO_DIR / '演示操作手册.md'}")


if __name__ == "__main__":
    main()
