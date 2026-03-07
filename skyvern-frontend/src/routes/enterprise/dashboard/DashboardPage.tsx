/**
 * Enterprise Dashboard — operational metrics overview.
 * Shows 4 summary cards + 3 chart areas (trend, errors, business lines).
 */

import { useEffect, useState } from "react";
import ReactECharts from "echarts-for-react";
import { GlassCard } from "@/components/enterprise/GlassCard";
import { Icon } from "@/components/Icon";

type OverviewData = {
  total_tasks: number;
  success_rate_today: number;
  success_rate_7d: number;
  avg_duration_ms: number;
  pending_approvals: number;
  needs_human_count: number;
};

type TrendItem = {
  date: string;
  success: number;
  failed: number;
  total: number;
};

type ErrorDistribution = Record<string, number>;

type BLComparison = {
  business_line_id: string;
  total_tasks: number;
  success_rate: number;
};

// Demo data generators for when API is unavailable
function demoOverview(): OverviewData {
  return {
    total_tasks: 1247,
    success_rate_today: 94.2,
    success_rate_7d: 91.8,
    avg_duration_ms: 3200,
    pending_approvals: 5,
    needs_human_count: 2,
  };
}

function demoTrend(): TrendItem[] {
  const items: TrendItem[] = [];
  const now = new Date();
  for (let i = 6; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    const success = 30 + Math.floor(Math.random() * 20);
    const failed = Math.floor(Math.random() * 5);
    items.push({
      date: d.toISOString().slice(0, 10),
      success,
      failed,
      total: success + failed,
    });
  }
  return items;
}

function demoErrors(): ErrorDistribution {
  return {
    LLM_FAILURE: 12,
    TIMEOUT: 8,
    PAGE_ERROR: 5,
    APPROVAL_REJECTED: 3,
  };
}

function demoBL(): BLComparison[] {
  return [
    { business_line_id: "Corporate Lending", total_tasks: 320, success_rate: 95.3 },
    { business_line_id: "Retail Credit", total_tasks: 280, success_rate: 92.1 },
    { business_line_id: "Wealth Management", total_tasks: 190, success_rate: 88.5 },
    { business_line_id: "Intl Settlement", total_tasks: 145, success_rate: 96.2 },
  ];
}

function OverviewCards({ data }: { data: OverviewData }) {
  const cards = [
    {
      title: "Total Tasks",
      value: data.total_tasks.toLocaleString(),
      icon: "task" as const,
      color: "var(--finrpa-blue)",
    },
    {
      title: "Success Rate (Today)",
      value: `${data.success_rate_today}%`,
      icon: "check-circle" as const,
      color: "var(--status-completed)",
    },
    {
      title: "Pending Approvals",
      value: data.pending_approvals.toString(),
      icon: "clock" as const,
      color: "var(--finrpa-gold)",
    },
    {
      title: "Needs Human",
      value: data.needs_human_count.toString(),
      icon: "user-check" as const,
      color: "var(--status-needs-human)",
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4">
      {cards.map((card) => (
        <GlassCard key={card.title} padding="md">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-medium uppercase tracking-wider" style={{ color: "var(--finrpa-text-muted)" }}>
                {card.title}
              </p>
              <p className="mt-1 text-2xl font-bold" style={{ color: "var(--finrpa-text-primary)" }}>
                {card.value}
              </p>
            </div>
            <div
              className="flex h-12 w-12 items-center justify-center rounded-xl"
              style={{ background: `${card.color}10` }}
            >
              <Icon name={card.icon} size={24} color={card.color} />
            </div>
          </div>
        </GlassCard>
      ))}
    </div>
  );
}

function TrendChart({ data }: { data: TrendItem[] }) {
  const option = {
    tooltip: { trigger: "axis" as const },
    legend: { data: ["Success", "Failed"], bottom: 0 },
    grid: { left: 40, right: 20, top: 20, bottom: 40 },
    xAxis: {
      type: "category" as const,
      data: data.map((d) => d.date.slice(5)),
      axisLine: { lineStyle: { color: "var(--chart-axis)" } },
      axisLabel: { color: "var(--finrpa-text-secondary)" },
    },
    yAxis: {
      type: "value" as const,
      axisLine: { show: false },
      splitLine: { lineStyle: { color: "var(--chart-grid)" } },
      axisLabel: { color: "var(--finrpa-text-secondary)" },
    },
    series: [
      {
        name: "Success",
        type: "line",
        smooth: true,
        data: data.map((d) => d.success),
        lineStyle: { color: "var(--chart-blue)", width: 2 },
        itemStyle: { color: "var(--chart-blue)" },
        areaStyle: { color: "rgba(26,58,92,0.08)" },
      },
      {
        name: "Failed",
        type: "line",
        smooth: true,
        data: data.map((d) => d.failed),
        lineStyle: { color: "var(--chart-red)", width: 2 },
        itemStyle: { color: "var(--chart-red)" },
      },
    ],
  };

  return <ReactECharts option={option} style={{ height: 280 }} />;
}

function ErrorPieChart({ data }: { data: ErrorDistribution }) {
  const entries = Object.entries(data);
  const colors = ["var(--chart-red)", "var(--chart-gold)", "var(--chart-purple)", "var(--chart-cyan)"];
  const option = {
    tooltip: { trigger: "item" as const },
    series: [
      {
        type: "pie",
        radius: ["40%", "70%"],
        data: entries.map(([name, value], i) => ({
          name,
          value,
          itemStyle: { color: colors[i % colors.length] },
        })),
        label: {
          color: "var(--finrpa-text-secondary)",
          fontSize: 12,
        },
      },
    ],
  };

  return <ReactECharts option={option} style={{ height: 280 }} />;
}

function BLBarChart({ data }: { data: BLComparison[] }) {
  const option = {
    tooltip: { trigger: "axis" as const },
    grid: { left: 120, right: 30, top: 20, bottom: 20 },
    xAxis: {
      type: "value" as const,
      max: 100,
      axisLabel: { formatter: "{value}%", color: "var(--finrpa-text-secondary)" },
      splitLine: { lineStyle: { color: "var(--chart-grid)" } },
    },
    yAxis: {
      type: "category" as const,
      data: data.map((d) => d.business_line_id),
      axisLabel: { color: "var(--finrpa-text-secondary)", fontSize: 12 },
      axisLine: { lineStyle: { color: "var(--chart-axis)" } },
    },
    series: [
      {
        type: "bar",
        data: data.map((d) => d.success_rate),
        barWidth: 20,
        itemStyle: {
          color: "var(--chart-blue)",
          borderRadius: [0, 4, 4, 0],
        },
      },
    ],
  };

  return <ReactECharts option={option} style={{ height: 280 }} />;
}

export function DashboardPage() {
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [trend, setTrend] = useState<TrendItem[]>([]);
  const [errors, setErrors] = useState<ErrorDistribution>({});
  const [blData, setBLData] = useState<BLComparison[]>([]);

  useEffect(() => {
    // Attempt to fetch from API, fall back to demo data
    async function load() {
      try {
        const [ov, tr, er, bl] = await Promise.all([
          fetch("/api/v1/enterprise/dashboard/overview").then((r) => r.ok ? r.json() : null),
          fetch("/api/v1/enterprise/dashboard/trend?days=7").then((r) => r.ok ? r.json() : null),
          fetch("/api/v1/enterprise/dashboard/errors").then((r) => r.ok ? r.json() : null),
          fetch("/api/v1/enterprise/dashboard/business-lines").then((r) => r.ok ? r.json() : null),
        ]);
        setOverview(ov ?? demoOverview());
        setTrend(tr ?? demoTrend());
        setErrors(er ?? demoErrors());
        setBLData(bl ?? demoBL());
      } catch {
        setOverview(demoOverview());
        setTrend(demoTrend());
        setErrors(demoErrors());
        setBLData(demoBL());
      }
    }
    load();
  }, []);

  if (!overview) return null;

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Icon name="dashboard" size={24} color="var(--finrpa-blue)" />
          <h1 className="text-xl font-bold" style={{ color: "var(--finrpa-blue)" }}>
            Operations Dashboard
          </h1>
        </div>
        <button className="glass-btn-secondary flex items-center gap-2 text-sm">
          <Icon name="download" size={16} />
          Export CSV
        </button>
      </div>

      <OverviewCards data={overview} />

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <GlassCard hoverable={false} padding="md">
          <h3 className="mb-4 text-sm font-semibold" style={{ color: "var(--finrpa-text-primary)" }}>
            Task Trend (7 Days)
          </h3>
          <TrendChart data={trend} />
        </GlassCard>

        <GlassCard hoverable={false} padding="md">
          <h3 className="mb-4 text-sm font-semibold" style={{ color: "var(--finrpa-text-primary)" }}>
            Error Distribution
          </h3>
          <ErrorPieChart data={errors} />
        </GlassCard>
      </div>

      <GlassCard hoverable={false} padding="md">
        <h3 className="mb-4 text-sm font-semibold" style={{ color: "var(--finrpa-text-primary)" }}>
          Business Line Comparison — Success Rate
        </h3>
        <BLBarChart data={blData} />
      </GlassCard>
    </div>
  );
}
