"use client";

import { useEffect, useState } from "react";
import { Activity, CheckCircle2, AlertTriangle } from "lucide-react";
import { useLocaleStore } from "@/stores/localeStore";
import { getDetailedHealth } from "@/lib/api";

interface HealthData {
  status: string;
  graph?: { healthy: boolean; total_issues: number; total_concepts: number; total_relationships: number };
  pipeline?: { all_apis_healthy: boolean; apis: { name: string; available: boolean }[] };
  cost?: { cost: { estimated_monthly_rate_usd: number } };
}

export default function SystemHealth() {
  const { t } = useLocaleStore();
  const [health, setHealth] = useState<HealthData | null>(null);

  useEffect(() => {
    getDetailedHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  if (!health) return null;

  const isHealthy = health.status === "healthy";
  const apisUp = health.pipeline?.apis?.filter((a) => a.available).length ?? 0;
  const apisTotal = health.pipeline?.apis?.length ?? 0;
  const monthlyCost = health.cost?.cost?.estimated_monthly_rate_usd ?? 0;

  return (
    <div className="space-y-2">
      {/* Overall status */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isHealthy ? (
            <CheckCircle2 size={12} className="text-accent-green" />
          ) : (
            <AlertTriangle size={12} className="text-accent-amber" />
          )}
          <span className="text-xs text-text-secondary">
            {isHealthy ? t.healthy : t.degraded}
          </span>
        </div>
        <Activity size={12} className="text-text-tertiary" />
      </div>

      {/* Metrics row */}
      <div className="grid grid-cols-3 gap-2">
        <div className="bg-surface-sunken rounded-lg px-2 py-1.5 text-center">
          <span className="block text-[10px] text-text-tertiary">{t.graphHealth}</span>
          <span className={`text-xs font-medium ${health.graph?.healthy ? "text-accent-green" : "text-accent-amber"}`}>
            {health.graph?.total_issues ?? "?"} issues
          </span>
        </div>
        <div className="bg-surface-sunken rounded-lg px-2 py-1.5 text-center">
          <span className="block text-[10px] text-text-tertiary">{t.apisHealth}</span>
          <span className={`text-xs font-medium ${apisUp === apisTotal ? "text-accent-green" : "text-accent-amber"}`}>
            {apisUp}/{apisTotal}
          </span>
        </div>
        <div className="bg-surface-sunken rounded-lg px-2 py-1.5 text-center">
          <span className="block text-[10px] text-text-tertiary">{t.costEstimate}</span>
          <span className="text-xs font-medium text-text-secondary">
            ${monthlyCost.toFixed(0)}/mo
          </span>
        </div>
      </div>
    </div>
  );
}
