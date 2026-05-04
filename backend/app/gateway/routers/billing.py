"""计费 API — 套餐列表、额度查询、订单管理、支付回调。

除 ``GET /api/billing/plans`` 外，其余端点均需要用户认证。

路由列表：
    GET  /api/billing/plans                 — 获取所有可用套餐（无需登录）
    GET  /api/billing/quota                 — 当前用户的 Token 余额
    GET  /api/billing/orders                — 当前用户的订单历史
    POST /api/billing/orders                — 创建新购买订单
    POST /api/billing/webhook/{provider}    — 支付平台回调入口
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Path, Request
from pydantic import BaseModel, Field

from app.gateway.billing.service import BillingService
from app.gateway.deps import get_billing_service, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])


# ---------------------------------------------------------------------------
# 请求 / 响应模型
# ---------------------------------------------------------------------------


class CreateOrderRequest(BaseModel):
    plan_id: str = Field(..., description="要购买的套餐 ID")
    payment_method: str = Field(default="stripe", description="支付方式：alipay / wechat_pay / stripe")


class OrderResponse(BaseModel):
    order_id: str
    order_no: str
    amount_cents: int
    plan_name: str
    input_token_quota: int
    output_token_quota: int


class QuotaResponse(BaseModel):
    user_id: str
    plan_id: str | None = None
    input_quota_total: int = 0
    input_quota_used: int = 0
    input_quota_remaining: int = 0
    output_quota_total: int = 0
    output_quota_used: int = 0
    output_quota_remaining: int = 0
    status: str
    first_activated_at: str | None = None
    last_recharged_at: str | None = None


class PlanResponse(BaseModel):
    id: str
    name: str
    description: str | None
    price_cents: int
    input_token_quota: int
    output_token_quota: int
    is_default: bool
    is_active: bool
    sort_order: int


class OrderHistoryItem(BaseModel):
    id: str
    order_no: str
    plan_id: str
    amount_cents: int
    payment_status: str
    input_quota_granted: int
    output_quota_granted: int
    created_at: str
    paid_at: str | None


# ---------------------------------------------------------------------------
# 接口端点
# ---------------------------------------------------------------------------


@router.get("/plans", response_model=list[PlanResponse])
async def list_plans(request: Request) -> list[PlanResponse]:
    """列出所有可用套餐（无需认证）。"""
    svc: BillingService = get_billing_service(request)
    plans = await svc.list_plans()
    return [PlanResponse(**p) for p in plans]


@router.get("/quota", response_model=QuotaResponse)
async def get_quota(request: Request) -> QuotaResponse:
    """获取当前用户的 Token 额度。"""
    user_id = await get_current_user(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="未登录")

    svc: BillingService = get_billing_service(request)

    # 确保用户拥有默认免费额度
    await svc.ensure_default_quota(user_id)

    quota = await svc.get_quota(user_id)
    if quota is None:
        raise HTTPException(status_code=500, detail="额度记录不存在")

    return QuotaResponse(**quota)


@router.get("/orders", response_model=list[OrderHistoryItem])
async def list_orders(request: Request) -> list[OrderHistoryItem]:
    """获取当前用户的订单历史。"""
    user_id = await get_current_user(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="未登录")

    svc: BillingService = get_billing_service(request)
    orders = await svc.list_orders(user_id)
    return [OrderHistoryItem(**o) for o in orders]


@router.post("/orders", response_model=OrderResponse)
async def create_order(body: CreateOrderRequest, request: Request) -> OrderResponse:
    """为指定套餐创建购买订单。"""
    user_id = await get_current_user(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="未登录")

    svc: BillingService = get_billing_service(request)
    try:
        result = await svc.create_order(user_id, body.plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return OrderResponse(**result)


@router.post("/webhook/{provider}")
async def payment_webhook(
    provider: str = Path(..., description="支付平台名称"),
    request: Request = None,
) -> dict:
    """支付平台回调入口（占位实现）。

    需要在此实现各支付平台的签名验证逻辑（如 Stripe 签名校验、
    支付宝通知验证等），确认支付成功后调用
    ``BillingService.fulfil_order`` 完成充值。
    """
    logger.info("收到支付平台回调: %s", provider)
    # TODO: 实现各支付平台的签名验证
    # 验证通过后调用 svc.fulfil_order(order_id) 完成订单
    return {"status": "ok", "provider": provider}
