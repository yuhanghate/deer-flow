"use client";

import { CheckIcon, Loader2Icon } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { createOrder, formatPrice, listPlans } from "@/core/billing";
import type { BillingPlan } from "@/core/billing/types";
import { useI18n } from "@/core/i18n/hooks";

interface PricingSheetProps {
  onPurchaseComplete?: () => void;
}

export function PricingSheet({ onPurchaseComplete }: PricingSheetProps) {
  const { t } = useI18n();
  const [plans, setPlans] = useState<BillingPlan[]>([]);
  const [purchasingId, setPurchasingId] = useState<string | null>(null);

  const fetchPlans = useCallback(async () => {
    try {
      const data = await listPlans();
      setPlans(data.filter((p) => p.is_active));
    } catch {
      // Silently ignore
    }
  }, []);

  useEffect(() => {
    void fetchPlans();
  }, [fetchPlans]);

  const handlePurchase = async (plan: BillingPlan) => {
    setPurchasingId(plan.id);
    try {
      const order = await createOrder(plan.id);
      // If the payment provider returns a checkout URL, redirect to it
      if (order.checkout_url) {
        window.location.href = order.checkout_url;
        return;
      }
      // Otherwise simulate instant fulfillment (for demo / no-provider mode)
      if (onPurchaseComplete) {
        onPurchaseComplete();
      }
    } catch {
      // In production, show a toast notification
    } finally {
      setPurchasingId(null);
    }
  };

  if (plans.length === 0) return null;

  return (
    <div className="space-y-6">
      <h3 className="text-sm font-medium px-1">{t.billing.plans.title}</h3>
      <div className="space-y-4">
        {plans.filter((p) => !p.is_default).map((plan) => {
          const isPurchasing = purchasingId === plan.id;

          return (
            <div
              key={plan.id}
              className="group flex items-center justify-between rounded-xl border bg-card p-6 shadow-sm transition-all hover:border-primary/30 hover:shadow-md"
            >
              <div>
                <span className="text-base font-semibold">{plan.name}</span>
              </div>
              <div className="flex items-center gap-4">
                <span className="text-lg font-bold">{formatPrice(plan.price_cents)}</span>
                <Button
                  size="sm"
                  variant="default"
                  disabled={isPurchasing}
                  onClick={() => handlePurchase(plan)}
                  className="shrink-0"
                >
                  {isPurchasing ? (
                    <Loader2Icon className="size-4 animate-spin" />
                  ) : (
                    <CheckIcon className="size-4" />
                  )}
                  {t.billing.buyNow}
                </Button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
