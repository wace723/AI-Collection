"""订单与特征模型。

orders 存标识与状态字段，order_features 1:1 存 37 列特征中的非标识字段。
列名沿用 CSV 表头（中文），Python 属性用英文。
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    DECIMAL,
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Order(Base, TimestampMixin):
    """平台使用费订单（标识 + 状态 + 风险）。"""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    supplier_no: Mapped[str] = mapped_column(String(64))
    supplier_name: Mapped[str] = mapped_column(String(255))
    biz_no: Mapped[str] = mapped_column(String(64), index=True)
    service_fee_order_no: Mapped[str] = mapped_column(
        String(64), unique=True, index=True
    )
    tender_type_desc: Mapped[str | None] = mapped_column(String(64))
    purchase_type_desc: Mapped[str | None] = mapped_column(String(64))
    win_bid_date: Mapped[date | None] = mapped_column(Date, index=True)
    register_area: Mapped[str | None] = mapped_column(String(64))
    # WAIT_PAY / PAID / NULL（未支付为 NULL 时由 pay_status 与 pay_time 共同表达）
    pay_status: Mapped[str | None] = mapped_column(String(16))
    pay_time: Mapped[datetime | None] = mapped_column(DateTime)
    risk_prob: Mapped[float | None] = mapped_column(DECIMAL(5, 2))
    risk_tier: Mapped[str | None] = mapped_column(String(8))
    risk_calc_time: Mapped[datetime | None] = mapped_column(DateTime)


class OrderFeature(Base):
    """订单特征（1:1 关联 orders），37 列中的非标识字段。"""

    __tablename__ = "order_features"

    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True
    )

    # A 类 · 缴费历史（截至中标时刻）
    history_fee_order_count: Mapped[int | None] = mapped_column(
        Integer, name="历史平台使用费订单数"
    )
    last_pay_duration_days: Mapped[int | None] = mapped_column(
        Integer, name="上次缴费历时_天"
    )
    avg_pay_duration_days: Mapped[float | None] = mapped_column(
        DECIMAL(10, 4), name="历史缴费平均历时_天"
    )

    # B 类 · 活跃度与支付
    fwsc_history_pay_amount: Mapped[float | None] = mapped_column(
        DECIMAL(16, 2), name="服务市场历史支付金额"
    )
    signup_count: Mapped[int | None] = mapped_column(Integer, name="历史报名次数")
    bidding_count: Mapped[int | None] = mapped_column(Integer, name="历史投标次数")
    win_count: Mapped[int | None] = mapped_column(Integer, name="历史中标次数")
    win_rate: Mapped[float | None] = mapped_column(DECIMAL(6, 4), name="历史中标率")
    active_90d: Mapped[int | None] = mapped_column(Integer, name="近90天投标活跃度")
    first_win_interval_days: Mapped[int | None] = mapped_column(
        Integer, name="首次中标距本次间隔_天"
    )
    is_member_at_win: Mapped[bool | None] = mapped_column(
        Boolean, name="中标时是否会员"
    )
    member_purchase_count_before_win: Mapped[int | None] = mapped_column(
        Integer, name="中标前购买会员次数"
    )

    # C 类 · 资质与标签表（注意：无时间维度，上线真实算法需时间切割）
    register_fund: Mapped[int | None] = mapped_column(BigInteger, name="注册资金")
    register_interval_days: Mapped[int | None] = mapped_column(
        Integer, name="注册时间距中标间隔_天"
    )
    in_date_interval_days: Mapped[int | None] = mapped_column(
        Integer, name="平台入驻时间距中标间隔_天"
    )
    entry_interval_days: Mapped[int | None] = mapped_column(
        Integer, name="最早入库时间距中标间隔_天"
    )
    supplier_categories: Mapped[str | None] = mapped_column(
        String(255), name="供应商品类"
    )
    ads_win_rate: Mapped[float | None] = mapped_column(
        DECIMAL(6, 4), name="标签表历史中标率"
    )
    high_quality_cnt: Mapped[int | None] = mapped_column(
        Integer, name="股份优质评级次数"
    )
    cooperate_org_num: Mapped[int | None] = mapped_column(
        Integer, name="合作单位数量"
    )
    total_perform_project_num: Mapped[int | None] = mapped_column(
        Integer, name="累计履约项目数"
    )

    # 标签
    actual_pay_duration_days: Mapped[int | None] = mapped_column(
        Integer, name="实际支付时长_天"
    )
    label_30: Mapped[int | None] = mapped_column(SmallInteger, name="标签_30天是否欠费")
    label_90: Mapped[int | None] = mapped_column(SmallInteger, name="标签_90天是否欠费")
    label_180: Mapped[int | None] = mapped_column(
        SmallInteger, name="标签_180天是否欠费"
    )
    label_365: Mapped[int | None] = mapped_column(
        SmallInteger, name="标签_365天是否欠费"
    )

    # 预留扩展特征（跨库 JSON：SQLite 用 JSON，PG 用 JSONB）
    extra_features: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True, name="extra_features"
    )
