"use client";

import { CoinsIcon } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { getQuota, calculateRemainingAmount, formatYuan } from "@/core/billing";
import type { UserQuota } from "@/core/billing/types";
import { useI18n } from "@/core/i18n/hooks";

import { PricingSheet } from "./pricing-sheet";

interface QuotaBarProps {
  refreshTrigger?: number;
}

export function QuotaBar({ refreshTrigger }: QuotaBarProps) {
  const { t } = useI18n();
  const [quota, setQuota] = useState<UserQuota | null>(null);
  const [open, setOpen] = useState(false);

  const fetchQuota = useCallback(async () => {
    try {
      const data = await getQuota();
      setQuota(data);
    } catch {
      // Silently ignore — quota is an enhancement, not critical
    }
  }, []);

  useEffect(() => {
    void fetchQuota();
  }, [fetchQuota, refreshTrigger]);

  if (!quota || quota.input_quota_total === 0) return null;

  const totalRemaining = calculateRemainingAmount(quota.input_quota_remaining, quota.output_quota_remaining);

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <button
          type="button"
          className="text-foreground/70 hover:bg-secondary hover:text-foreground flex h-8 items-center gap-1.5 whitespace-nowrap rounded-full border px-3 text-xs transition-colors"
        >
          <CoinsIcon size={14} />
          <span className="whitespace-nowrap">
            {t.billing.remaining} {formatYuan(totalRemaining)}
          </span>
        </button>
      </SheetTrigger>
      <SheetContent side="right" className="w-[420px] sm:w-[540px]">
        <div className="flex flex-col h-full px-6">
          <SheetHeader className="mb-8 pt-2">
            <SheetTitle className="flex items-center gap-2 text-base">
              <CoinsIcon size={18} />
              {t.billing.quotaTitle}
            </SheetTitle>
            <SheetDescription className="text-sm">{t.billing.description}</SheetDescription>
          </SheetHeader>
          <div className="flex-1 space-y-8 overflow-y-auto">
            <div className="bg-muted/30 rounded-xl border p-6">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground text-sm">{t.billing.remaining}</span>
                <span className="font-mono text-lg font-semibold">{formatYuan(totalRemaining)}</span>
              </div>
            </div>

            {/* Upgrade CTA */}
            <PricingSheet onPurchaseComplete={fetchQuota} />
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
