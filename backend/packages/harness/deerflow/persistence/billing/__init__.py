"""VIP 计费 / 付费系统 ORM 模型。

四张表：
- subscription_plans  — 预定义的价格套餐
- user_quotas         — 每个用户的 Token 额度（每个用户一行）
- orders              — 支付订单记录
- quota_logs          — Token 变更审计日志

导入此模块即会将所有模型注册到 ``Base.metadata``，
因此 ``Base.metadata.create_all()`` 会在 Gateway
启动时自动建表（与现有持久化模型相同的模式）。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Index, String, Text, BigInteger, Integer
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


# ── subscription_plans（套餐表）─────────────────────────────────

class PlanRow(Base):
    """预定义的价格套餐，包含免费档和付费档。"""

    __tablename__ = "subscription_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)  # 套餐名称
    description: Mapped[str | None] = mapped_column(Text)  # 套餐描述
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)  # 价格（单位：分）
    input_token_quota: Mapped[int] = mapped_column(BigInteger, nullable=False)  # 输入 Token 总额
    output_token_quota: Mapped[int] = mapped_column(BigInteger, nullable=False)  # 输出 Token 总额
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # 是否为默认（免费）套餐
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # 是否启用
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 排序权重
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)

    __table_args__ = (
        Index("ix_plans_is_active", "is_active"),
        Index("ix_plans_sort_order", "sort_order"),
    )


# ── user_quotas（用户额度表）────────────────────────────────────

class UserQuotaRow(Base):
    """每个用户的 Token 额度，每个用户仅一行。"""

    __tablename__ = "user_quotas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)  # 用户 ID
    plan_id: Mapped[str | None] = mapped_column(String(36))  # 当前套餐 ID
    input_quota_total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)  # 累计输入 Token
    input_quota_used: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)  # 已用输入 Token
    input_quota_remaining: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)  # 剩余输入 Token
    output_quota_total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)  # 累计输出 Token
    output_quota_used: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)  # 已用输出 Token
    output_quota_remaining: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)  # 剩余输出 Token
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")  # active / exhausted
    first_activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)  # 首次激活时间
    last_recharged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 最后充值时间
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)

    __table_args__ = (
        Index("ix_quotas_user_id", "user_id", unique=True),
        Index("ix_quotas_status", "status"),
    )


# ── orders（订单表）──────────────────────────────────────────────

class OrderRow(Base):
    """支付订单记录。"""

    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)  # 订单号
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)  # 下单用户
    plan_id: Mapped[str] = mapped_column(String(36), nullable=False)  # 购买套餐
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)  # 支付金额（分）
    payment_method: Mapped[str | None] = mapped_column(String(32))  # 支付方式
    payment_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending / paid / failed / cancelled
    payment_id: Mapped[str | None] = mapped_column(String(128))  # 第三方支付流水号
    input_quota_granted: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)  # 输入 Token 数量
    output_quota_granted: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)  # 输出 Token 数量
    error_message: Mapped[str | None] = mapped_column(Text)  # 失败原因
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 支付完成时间
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)

    __table_args__ = (
        Index("ix_orders_order_no", "order_no", unique=True),
        Index("ix_orders_user_id", "user_id"),
        Index("ix_orders_payment_status", "payment_status"),
        Index("ix_orders_payment_id", "payment_id"),
    )


# ── quota_logs（额度变更日志表）──────────────────────────────────

class QuotaLogRow(Base):
    """Token 额度变更审计日志，记录每一次扣减、充值、赠送。"""

    __tablename__ = "quota_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)  # 用户 ID
    run_id: Mapped[str | None] = mapped_column(String(64))  # 关联的对话 ID（扣减时有值）
    change_type: Mapped[str] = mapped_column(String(20), nullable=False)  # deduct / grant / recharge
    input_change_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)  # 输入变更数量
    output_change_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)  # 输出变更数量
    input_balance_before: Mapped[int] = mapped_column(BigInteger, nullable=False)  # 变更前输入余额
    input_balance_after: Mapped[int] = mapped_column(BigInteger, nullable=False)  # 变更后输入余额
    output_balance_before: Mapped[int] = mapped_column(BigInteger, nullable=False)  # 变更前输出余额
    output_balance_after: Mapped[int] = mapped_column(BigInteger, nullable=False)  # 变更后输出余额
    remark: Mapped[str | None] = mapped_column(Text)  # 备注说明
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)

    __table_args__ = (
        Index("ix_quota_logs_user_id", "user_id"),
        Index("ix_quota_logs_run_id", "run_id"),
        Index("ix_quota_logs_change_type", "change_type"),
    )
