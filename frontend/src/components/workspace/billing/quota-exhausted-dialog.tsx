"use client";

import { useEffect, useState } from "react";

import { UpgradeDialog } from "@/components/workspace/billing";

const QUOTA_EXHAUSTED_EVENT = "deerflow:quota-exhausted";

export function QuotaExhaustedDialog() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const handler = () => setOpen(true);
    window.addEventListener(QUOTA_EXHAUSTED_EVENT, handler);
    return () => window.removeEventListener(QUOTA_EXHAUSTED_EVENT, handler);
  }, []);

  return <UpgradeDialog open={open} onOpenChange={setOpen} />;
}
