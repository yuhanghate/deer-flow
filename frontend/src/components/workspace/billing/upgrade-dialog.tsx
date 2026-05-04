"use client";

import { CoinsIcon, Loader2Icon, SparklesIcon } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { createOrder, formatPrice, listPlans } from "@/core/billing";
import type { BillingPlan } from "@/core/billing/types";
import { useI18n } from "@/core/i18n/hooks";

interface UpgradeDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onPurchaseComplete?: () => void;
}

export function UpgradeDialog({ open, onOpenChange, onPurchaseComplete }: UpgradeDialogProps) {
  const { t } = useI18n();
  const [plans, setPlans] = useState<BillingPlan[]>([]);
  const [purchasingId, setPurchasingId] = useState<string | null>(null);

  const fetchPlans = useCallback(async () => {
    try {
      const data = await listPlans();
      setPlans(data.filter((p) => p.is_active && !p.is_default));
    } catch {
      // Silently ignore
    }
  }, []);

  useEffect(() => {
    if (open) void fetchPlans();
  }, [open, fetchPlans]);

  const handlePurchase = async (plan: BillingPlan) => {
    setPurchasingId(plan.id);
    try {
      const order = await createOrder(plan.id);
      if (order.checkout_url) {
        window.location.href = order.checkout_url;
        return;
      }
      if (onPurchaseComplete) onPurchaseComplete();
      onOpenChange(false);
    } catch {
      // In production, show a toast notification
    } finally {
      setPurchasingId(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <CoinsIcon className="text-destructive" size={20} />
            {t.billing.quotaExhausted}
          </DialogTitle>
          <DialogDescription>{t.billing.quotaExhaustedMessage}</DialogDescription>
        </DialogHeader>

        <div className="space-y-3 pt-2">
          {plans.map((plan) => {
            const isPurchasing = purchasingId === plan.id;
            return (
              <button
                key={plan.id}
                type="button"
                onClick={() => handlePurchase(plan)}
                disabled={isPurchasing}
                className="flex w-full items-center justify-between rounded-lg border p-4 text-left transition-colors hover:bg-accent disabled:opacity-50"
              >
                <div className="font-medium">{plan.name}</div>
                <div className="flex items-center gap-3">
                  <span className="font-medium">{formatPrice(plan.price_cents)}</span>
                  {isPurchasing ? (
                    <Loader2Icon className="size-4 animate-spin" />
                  ) : (
                    <SparklesIcon className="size-4 text-primary" />
                  )}
                </div>
              </button>
            );
          })}
        </div>
      </DialogContent>
    </Dialog>
  );
}
