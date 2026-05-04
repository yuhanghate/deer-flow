"""计费 / Token 额度服务。

用户 Token 额度的检查、扣减、充值核心逻辑。
输入/输出 tokens 分别计费和扣减。
所有持久化操作均通过共享的异步 SQLAlchemy 会话工厂完成。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deerflow.persistence.billing import OrderRow, PlanRow, QuotaLogRow, UserQuotaRow

logger = logging.getLogger(__name__)


class BillingService:
    """基于共享数据库引擎的 Token 额度操作。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    # ── 额度查询 ───────────────────────────────────────────────

    async def get_quota(self, user_id: str) -> dict | None:
        """返回用户的额度行（普通字典），不存在则返回 ``None``。"""
        async with self._sf() as session:
            stmt = select(UserQuotaRow).where(UserQuotaRow.user_id == user_id).limit(1)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return {
                "user_id": row.user_id,
                "plan_id": row.plan_id,
                "input_quota_total": row.input_quota_total,
                "input_quota_used": row.input_quota_used,
                "input_quota_remaining": row.input_quota_remaining,
                "output_quota_total": row.output_quota_total,
                "output_quota_used": row.output_quota_used,
                "output_quota_remaining": row.output_quota_remaining,
                "status": row.status,
                "first_activated_at": row.first_activated_at.isoformat(),
                "last_recharged_at": row.last_recharged_at.isoformat() if row.last_recharged_at else None,
            }

    async def has_quota(self, user_id: str) -> bool:
        """快速检查：用户是否还有剩余 Token？"""
        async with self._sf() as session:
            stmt = select(UserQuotaRow).where(UserQuotaRow.user_id == user_id).limit(1)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                return True  # 还没有额度行 → 按免费套餐处理，放行
            return row.input_quota_remaining > 0 or row.output_quota_remaining > 0

    async def deduct_quota(self, user_id: str, run_id: str, input_tokens: int, output_tokens: int) -> None:
        """从用户额度中扣除 *input_tokens* 和 *output_tokens*，并写入审计日志。"""
        if input_tokens <= 0 and output_tokens <= 0:
            return
        async with self._sf() as session:
            stmt = select(UserQuotaRow).where(UserQuotaRow.user_id == user_id).limit(1)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                return

            input_before = row.input_quota_remaining
            output_before = row.output_quota_remaining

            row.input_quota_used += input_tokens
            row.input_quota_remaining = max(0, row.input_quota_remaining - input_tokens)
            row.output_quota_used += output_tokens
            row.output_quota_remaining = max(0, row.output_quota_remaining - output_tokens)
            row.status = "exhausted" if (row.input_quota_remaining <= 0 and row.output_quota_remaining <= 0) else "active"
            row.updated_at = datetime.now(UTC)

            session.add(
                QuotaLogRow(
                    id=str(uuid4()),
                    user_id=user_id,
                    run_id=run_id,
                    change_type="deduct",
                    input_change_amount=-input_tokens,
                    output_change_amount=-output_tokens,
                    input_balance_before=input_before,
                    input_balance_after=row.input_quota_remaining,
                    output_balance_before=output_before,
                    output_balance_after=row.output_quota_remaining,
                    remark=f"对话 {run_id} 消耗 输入 {input_tokens} tokens, 输出 {output_tokens} tokens",
                )
            )
            await session.commit()

    async def ensure_default_quota(self, user_id: str) -> bool:
        """为新用户创建免费额度行（如果尚不存在）。

        返回 ``True`` 表示新建了额度，``False`` 表示已存在。
        并发请求下第二个请求会捕获 IntegrityError 并视为已存在。
        """
        async with self._sf() as session:
            stmt = select(UserQuotaRow).where(UserQuotaRow.user_id == user_id).limit(1)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing is not None:
                return False

            # 查找默认的免费套餐
            stmt = select(PlanRow).where(PlanRow.is_default.is_(True)).limit(1)
            result = await session.execute(stmt)
            default_plan = result.scalar_one_or_none()
            if default_plan is None:
                logger.warning("subscription_plans 表中没有默认（免费）套餐；用户 %s 不会获得额度", user_id)
                return False

            session.add(
                UserQuotaRow(
                    id=str(uuid4()),
                    user_id=user_id,
                    plan_id=default_plan.id,
                    input_quota_total=default_plan.input_token_quota,
                    input_quota_used=0,
                    input_quota_remaining=default_plan.input_token_quota,
                    output_quota_total=default_plan.output_token_quota,
                    output_quota_used=0,
                    output_quota_remaining=default_plan.output_token_quota,
                    status="active",
                )
            )
            session.add(
                QuotaLogRow(
                    id=str(uuid4()),
                    user_id=user_id,
                    run_id=None,
                    change_type="grant",
                    input_change_amount=default_plan.input_token_quota,
                    output_change_amount=default_plan.output_token_quota,
                    input_balance_before=0,
                    input_balance_after=default_plan.input_token_quota,
                    output_balance_before=0,
                    output_balance_after=default_plan.output_token_quota,
                    remark=f"从免费套餐 {default_plan.name} 授予额度",
                )
            )
            try:
                await session.commit()
            except Exception as exc:
                # 并发请求可能导致唯一键冲突，视为已存在即可
                if "duplicate key" in str(exc) or "unique" in str(exc).lower():
                    await session.rollback()
                    return False
                raise
            logger.info(
                "向新用户 %s 授予免费额度: 输入 %d tokens, 输出 %d tokens",
                user_id, default_plan.input_token_quota, default_plan.output_token_quota,
            )
            return True

    # ── 订单操作 ───────────────────────────────────────────────

    async def create_order(self, user_id: str, plan_id: str) -> dict:
        """为指定套餐创建一条待支付订单。"""
        async with self._sf() as session:
            plan = await session.get(PlanRow, plan_id)
            if plan is None or not plan.is_active:
                raise ValueError(f"套餐 {plan_id} 不存在或未启用")

            order_no = datetime.now(UTC).strftime("DF%Y%m%d%H%M%S") + uuid4().hex[:8]

            order = OrderRow(
                id=str(uuid4()),
                order_no=order_no,
                user_id=user_id,
                plan_id=plan_id,
                amount_cents=plan.price_cents,
                payment_status="pending",
                input_quota_granted=plan.input_token_quota,
                output_quota_granted=plan.output_token_quota,
            )
            session.add(order)
            await session.commit()
            return {
                "order_id": order.id,
                "order_no": order.order_no,
                "amount_cents": order.amount_cents,
                "plan_name": plan.name,
                "input_token_quota": plan.input_token_quota,
                "output_token_quota": plan.output_token_quota,
            }

    async def fulfil_order(self, order_id: str) -> None:
        """将订单标记为已支付，并为用户充值 Token。"""
        async with self._sf() as session:
            order = await session.get(OrderRow, order_id)
            if order is None:
                raise ValueError(f"订单 {order_id} 不存在")
            if order.payment_status == "paid":
                return  # 幂等处理：已支付则直接返回
            if order.payment_status != "pending":
                raise ValueError(f"订单 {order_id} 当前状态为 {order.payment_status}")

            order.payment_status = "paid"
            order.paid_at = datetime.now(UTC)

            # 为用户充值额度（如果额度行不存在则新建）
            stmt = select(UserQuotaRow).where(UserQuotaRow.user_id == order.user_id).limit(1)
            result = await session.execute(stmt)
            quota = result.scalar_one_or_none()
            if quota is None:
                quota = UserQuotaRow(
                    id=str(uuid4()),
                    user_id=order.user_id,
                    plan_id=order.plan_id,
                    input_quota_total=0,
                    input_quota_used=0,
                    input_quota_remaining=0,
                    output_quota_total=0,
                    output_quota_used=0,
                    output_quota_remaining=0,
                    status="active",
                )
                session.add(quota)

            input_before = quota.input_quota_remaining
            output_before = quota.output_quota_remaining

            quota.input_quota_total += order.input_quota_granted
            quota.input_quota_remaining += order.input_quota_granted
            quota.output_quota_total += order.output_quota_granted
            quota.output_quota_remaining += order.output_quota_granted
            quota.plan_id = order.plan_id
            quota.last_recharged_at = datetime.now(UTC)
            quota.status = "active"

            session.add(
                QuotaLogRow(
                    id=str(uuid4()),
                    user_id=order.user_id,
                    run_id=None,
                    change_type="recharge",
                    input_change_amount=order.input_quota_granted,
                    output_change_amount=order.output_quota_granted,
                    input_balance_before=input_before,
                    input_balance_after=quota.input_quota_remaining,
                    output_balance_before=output_before,
                    output_balance_after=quota.output_quota_remaining,
                    remark=f"订单 {order.order_no} 充值 输入 {order.input_quota_granted} tokens, 输出 {order.output_quota_granted} tokens",
                )
            )
            await session.commit()
            logger.info(
                "订单 %s 已履约：向用户 %s 充值 输入 %d tokens, 输出 %d tokens",
                order.order_no, order.user_id, order.input_quota_granted, order.output_quota_granted,
            )

    # ── 套餐查询 ────────────────────────────────────────────────

    async def list_plans(self) -> list[dict]:
        """返回所有已启用的套餐，按 sort_order 排序。"""
        async with self._sf() as session:
            stmt = select(PlanRow).where(PlanRow.is_active.is_(True)).order_by(PlanRow.sort_order)
            result = await session.execute(stmt)
            plans = result.scalars().all()
            return [
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "price_cents": p.price_cents,
                    "input_token_quota": p.input_token_quota,
                    "output_token_quota": p.output_token_quota,
                    "is_default": p.is_default,
                    "is_active": p.is_active,
                    "sort_order": p.sort_order,
                }
                for p in plans
            ]

    async def list_orders(self, user_id: str) -> list[dict]:
        """返回指定用户的所有订单，按创建时间倒序。"""
        from sqlalchemy import desc

        async with self._sf() as session:
            stmt = select(OrderRow).where(OrderRow.user_id == user_id).order_by(desc(OrderRow.created_at))
            result = await session.execute(stmt)
            orders = result.scalars().all()
            return [
                {
                    "id": o.id,
                    "order_no": o.order_no,
                    "plan_id": o.plan_id,
                    "amount_cents": o.amount_cents,
                    "payment_status": o.payment_status,
                    "input_quota_granted": o.input_quota_granted,
                    "output_quota_granted": o.output_quota_granted,
                    "created_at": o.created_at.isoformat(),
                    "paid_at": o.paid_at.isoformat() if o.paid_at else None,
                }
                for o in orders
            ]
