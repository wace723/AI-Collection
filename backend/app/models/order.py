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
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

# SQLite 下 BIGINT 主键不会自增（只有 INTEGER PRIMARY KEY 是 rowid 别名），
# 用 variant 让 SQLite 退化为 INTEGER 自增，PostgreSQL 保持 BIGINT。
_PK_BIGINT = BigInteger().with_variant(Integer, "sqlite")
_FK_BIGINT = BigInteger().with_variant(Integer, "sqlite")


class Order(Base, TimestampMixin):
    """平台使用费订单（标识 + 状态 + 风险 + 支付）。"""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(_PK_BIGINT, primary_key=True, autoincrement=True)
    supplier_no: Mapped[str] = mapped_column(String(64))
    supplier_name: Mapped[str] = mapped_column(String(255))
    biz_no: Mapped[str] = mapped_column(String(64), index=True)
    service_fee_order_no: Mapped[str] = mapped_column(
        String(64), unique=True, index=True
    )
    # 新 CSV 字段（标的/品类/合同/省份/订单生成日期）
    subject_name: Mapped[str | None] = mapped_column(String(255))
    tender_type_desc: Mapped[str | None] = mapped_column(String(64))
    purchase_type_desc: Mapped[str | None] = mapped_column(String(64))
    bid_category: Mapped[str | None] = mapped_column(String(128))
    contract_type: Mapped[str | None] = mapped_column(String(64))
    subject_estimate_amount: Mapped[float | None] = mapped_column(DECIMAL(16, 2))
    win_bid_date: Mapped[date | None] = mapped_column(Date, index=True)
    order_generated_date: Mapped[date | None] = mapped_column(Date)
    register_area: Mapped[str | None] = mapped_column(String(64))
    register_province: Mapped[str | None] = mapped_column(String(64))
    # 支付状态（已支付导入回写）
    pay_status: Mapped[str | None] = mapped_column(String(16))
    pay_time: Mapped[datetime | None] = mapped_column(DateTime)
    actual_pay_duration_days: Mapped[int | None] = mapped_column(Integer)
    # 风险（CSV 导入，不再系统预测）
    risk_prob: Mapped[float | None] = mapped_column(DECIMAL(5, 2))
    risk_tier: Mapped[str | None] = mapped_column(String(8))
    risk_import_time: Mapped[datetime | None] = mapped_column(DateTime)
    # 催收状态机（data-003）：NO_NEED/PENDING_COLLECTION/COLLECTED/FINALIZED
    # 详见 app/services/task_engine/states.py
    collection_state: Mapped[str] = mapped_column(
        String(24), default="NO_NEED", nullable=False, index=True
    )


class OrderFeature(Base):
    """订单特征（1:1 关联 orders），37 列中的非标识字段。"""

    __tablename__ = "order_features"

    order_id: Mapped[int] = mapped_column(
        _FK_BIGINT, ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True
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

    # 预留扩展特征（跨库 JSON：SQLite 用 JSON，PG 用 JSONB）
    extra_features: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True, name="extra_features"
    )
