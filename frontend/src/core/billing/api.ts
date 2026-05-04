import { fetch } from "@/core/api/fetcher";

import type { BillingPlan, UserQuota, BillingOrder, CreateOrderResponse } from "./types";

const BILLING_PREFIX = "/api/billing";

export async function listPlans(): Promise<BillingPlan[]> {
  const res = await fetch(`${BILLING_PREFIX}/plans`);
  if (!res.ok) throw new Error("Failed to fetch billing plans");
  return res.json();
}

export async function getQuota(): Promise<UserQuota | null> {
  const res = await fetch(`${BILLING_PREFIX}/quota`);
  if (res.status === 401) return null;
  if (!res.ok) throw new Error("Failed to fetch quota");
  return res.json();
}

export async function listOrders(): Promise<BillingOrder[]> {
  const res = await fetch(`${BILLING_PREFIX}/orders`);
  if (!res.ok) throw new Error("Failed to fetch orders");
  return res.json();
}

export async function createOrder(planId: string): Promise<CreateOrderResponse> {
  const res = await fetch(`${BILLING_PREFIX}/orders`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ plan_id: planId }),
  });
  if (!res.ok) throw new Error("Failed to create order");
  return res.json();
}

export function formatPrice(cents: number): string {
  return `¥${(cents / 100).toFixed(1)}`;
}

/**
 * Calculate spent amount (in yuan) based on used tokens.
 * Pricing: input ¥0.012/1K, output ¥0.048/1K
 */
export function calculateSpentAmount(inputUsed: number, outputUsed: number): number {
  const inputCost = (inputUsed / 1000) * 0.012;
  const outputCost = (outputUsed / 1000) * 0.048;
  return inputCost + outputCost;
}

/** Calculate remaining amount (in yuan) based on remaining tokens. */
export function calculateRemainingAmount(inputRemaining: number, outputRemaining: number): number {
  const inputCost = (inputRemaining / 1000) * 0.012;
  const outputCost = (outputRemaining / 1000) * 0.048;
  return inputCost + outputCost;
}

/** Format a yuan amount, showing 2 decimal places */
export function formatYuan(amount: number): string {
  return `¥${amount.toFixed(2)}`;
}

export function formatTokenCount(tokens: number): string {
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(tokens % 1_000_000 === 0 ? 0 : 1)}M`;
  if (tokens >= 1_000) return `${(tokens / 1_000).toFixed(tokens % 1_000 === 0 ? 0 : 1)}K`;
  return tokens.toLocaleString();
}
