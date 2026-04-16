import { useEffect, useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";

import { GlassCard } from "@/components/enterprise/GlassCard";
import { StatusBadge } from "@/components/enterprise/StatusBadge";
import { authFetch } from "@/util/authFetch";

type EvalMetrics = {
  accuracy: number;
  weighted_f1: number;
  miss_rate: number;
  conservative_rate: number;
  plan_validity: number;
  avg_step_count: number;
  goal_coverage: number;
  llm_judge_score: number;
  avg_latency_ms: number;
  total_cases: number;
  passed_cases: number;
};

type EvalCaseResult = {
  case_id: string;
  passed: boolean;
  latency_ms: number;
  actual_output: Record<string, unknown>;
  expected_output: Record<string, unknown>;
  notes?: string | null;
  score: number;
};

type EvalReport = {
  eval_id: string;
  module: string;
  prompt_version: string;
  generated_at: string;
  metrics: EvalMetrics;
  results: EvalCaseResult[];
};

type TraceStats = {
  total_traces: number;
  success_rate: number;
  avg_latency_ms: number;
  estimated_cost_usd: number;
  by_module?: Record<string, { calls: number; avg_latency_ms: number; estimated_cost_usd: number; success_rate: number }>;
};

const demoReports: EvalReport[] = [
  {
    eval_id: "eval_demo_a",
    module: "risk_detector",
    prompt_version: "v1",
    generated_at: "2026-04-10T10:00:00Z",
    metrics: {
      accuracy: 0.78,
      weighted_f1: 0.74,
      miss_rate: 0.08,
      conservative_rate: 0.12,
      plan_validity: 0,
      avg_step_count: 0,
      goal_coverage: 0,
      llm_judge_score: 0.76,
      avg_latency_ms: 842,
      total_cases: 12,
      passed_cases: 9,
    },
    results: [
      {
        case_id: "risk_001",
        passed: true,
        latency_ms: 801,
        actual_output: { risk_level: "critical" },
        expected_output: { risk_level: "critical" },
        score: 0.91,
      },
      {
        case_id: "risk_002",
        passed: false,
        latency_ms: 933,
        actual_output: { risk_level: "medium" },
        expected_output: { risk_level: "low" },
        notes: "Query case over-escalated",
        score: 0.58,
      },
    ],
  },
  {
    eval_id: "eval_demo_b",
    module: "risk_detector",
    prompt_version: "v2-rag",
    generated_at: "2026-04-10T14:00:00Z",
    metrics: {
      accuracy: 0.91,
      weighted_f1: 0.88,
      miss_rate: 0.0,
      conservative_rate: 0.17,
      plan_validity: 0,
      avg_step_count: 0,
      goal_coverage: 0,
      llm_judge_score: 0.89,
      avg_latency_ms: 956,
      total_cases: 12,
      passed_cases: 11,
    },
    results: [
      {
        case_id: "risk_001",
        passed: true,
        latency_ms: 981,
        actual_output: { risk_level: "critical" },
        expected_output: { risk_level: "critical" },
        score: 0.97,
      },
      {
        case_id: "risk_002",
        passed: true,
        latency_ms: 905,
        actual_output: { risk_level: "low" },
        expected_output: { risk_level: "low" },
        score: 0.87,
      },
    ],
  },
];

const demoTraceStats: TraceStats = {
  total_traces: 168,
  success_rate: 0.964,
  avg_latency_ms: 914,
  estimated_cost_usd: 2.84,
  by_module: {
    risk_detector: { calls: 92, avg_latency_ms: 881, estimated_cost_usd: 1.41, success_rate: 0.978 },
    planner: { calls: 76, avg_latency_ms: 955, estimated_cost_usd: 1.43, success_rate: 0.947 },
  },
};

function formatPct(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function SectionTitle({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-4">
      <h2 className="text-xl font-semibold text-slate-900">{title}</h2>
      {subtitle ? <p className="mt-1 text-sm text-slate-500">{subtitle}</p> : null}
    </div>
  );
}

export function EvalDashboardPage() {
  const [reports, setReports] = useState<EvalReport[]>(demoReports);
  const [traceStats, setTraceStats] = useState<TraceStats>(demoTraceStats);
  const [selectedIds, setSelectedIds] = useState<[string, string]>([demoReports[0].eval_id, demoReports[1].eval_id]);

  useEffect(() => {
    let mounted = true;

    async function load() {
      try {
        const [reportsRes, tracesRes] = await Promise.all([
          authFetch("/api/v1/enterprise/eval/reports?limit=20"),
          authFetch("/api/v1/enterprise/eval/traces/stats?hours=24"),
        ]);
        if (!mounted) return;

        if (reportsRes.ok) {
          const data = (await reportsRes.json()) as EvalReport[];
          if (data.length > 0) {
            setReports(data);
            setSelectedIds(data.length >= 2 ? [data[1].eval_id, data[0].eval_id] : [data[0].eval_id, data[0].eval_id]);
          }
        }

        if (tracesRes.ok) {
          setTraceStats((await tracesRes.json()) as TraceStats);
        }
      } catch {
        // Keep demo data when API is unavailable.
      }
    }

    void load();
    return () => {
      mounted = false;
    };
  }, []);

  const selectedA = reports.find((report) => report.eval_id === selectedIds[0]) ?? reports[0];
  const selectedB = reports.find((report) => report.eval_id === selectedIds[1]) ?? reports[Math.min(1, reports.length - 1)] ?? reports[0];

  const compareMetrics = useMemo(() => {
    if (!selectedA || !selectedB) return [] as { label: string; before: number; after: number }[];

    const pairs = [
      { key: "accuracy", label: "Accuracy" },
      { key: "weighted_f1", label: "Weighted F1" },
      { key: "miss_rate", label: "Critical Miss Rate" },
      { key: "llm_judge_score", label: "LLM-as-Judge" },
    ] as const;

    return pairs.map(({ key, label }) => ({
      label,
      before: Number(selectedA.metrics[key]),
      after: Number(selectedB.metrics[key]),
    }));
  }, [selectedA, selectedB]);

  const compareOption = {
    tooltip: { trigger: "axis" as const },
    legend: { data: [selectedA?.prompt_version ?? "A", selectedB?.prompt_version ?? "B"] },
    xAxis: {
      type: "category" as const,
      data: compareMetrics.map((item) => item.label),
      axisLabel: { rotate: 15 },
    },
    yAxis: { type: "value" as const, min: 0, max: 1 },
    series: [
      {
        name: selectedA?.prompt_version ?? "A",
        type: "bar" as const,
        data: compareMetrics.map((item) => Number(item.before.toFixed(3))),
        itemStyle: { color: "#94A3B8" },
      },
      {
        name: selectedB?.prompt_version ?? "B",
        type: "bar" as const,
        data: compareMetrics.map((item) => Number(item.after.toFixed(3))),
        itemStyle: { color: "#2563EB" },
      },
    ],
  };

  const traceOption = {
    tooltip: { trigger: "item" as const },
    series: [
      {
        type: "pie" as const,
        radius: ["45%", "70%"],
        data: Object.entries(traceStats.by_module ?? {}).map(([module, stats]) => ({
          name: module,
          value: stats.calls,
        })),
        label: { formatter: "{b}: {c}" },
      },
    ],
  };

  return (
    <div className="space-y-6 px-1 pb-8">
      <SectionTitle
        title="LLM Evaluation Dashboard"
        subtitle="Use golden cases, prompt comparisons, and traces to prove the gains from RAG and prompt iteration."
      />

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-4">
        <GlassCard padding="md">
          <p className="text-xs uppercase tracking-wider text-slate-500">Latest Accuracy</p>
          <p className="mt-2 text-3xl font-bold text-slate-900">{selectedB ? formatPct(selectedB.metrics.accuracy) : "-"}</p>
          <p className="mt-2 text-xs text-emerald-600">vs baseline {selectedA ? formatPct(selectedA.metrics.accuracy) : "-"}</p>
        </GlassCard>

        <GlassCard padding="md">
          <p className="text-xs uppercase tracking-wider text-slate-500">Critical Miss Rate</p>
          <p className="mt-2 text-3xl font-bold text-slate-900">{selectedB ? formatPct(selectedB.metrics.miss_rate) : "-"}</p>
          <p className="mt-2 text-xs text-slate-500">Most important financial risk metric. Target should be near zero.</p>
        </GlassCard>

        <GlassCard padding="md">
          <p className="text-xs uppercase tracking-wider text-slate-500">24h LLM Success Rate</p>
          <p className="mt-2 text-3xl font-bold text-slate-900">{formatPct(traceStats.success_rate)}</p>
          <p className="mt-2 text-xs text-slate-500">Average latency {traceStats.avg_latency_ms.toFixed(0)} ms</p>
        </GlassCard>

        <GlassCard padding="md">
          <p className="text-xs uppercase tracking-wider text-slate-500">24h Estimated Cost</p>
          <p className="mt-2 text-3xl font-bold text-slate-900">${traceStats.estimated_cost_usd.toFixed(2)}</p>
          <p className="mt-2 text-xs text-slate-500">Total traces {traceStats.total_traces}</p>
        </GlassCard>
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[1.5fr,1fr]">
        <GlassCard padding="md" hoverable={false}>
          <SectionTitle title="Prompt A/B Comparison" subtitle="Compare baseline and RAG-enhanced prompts on the most important metrics." />
          <div className="mb-4 flex flex-wrap gap-3">
            <select
              value={selectedIds[0]}
              onChange={(event) => setSelectedIds([event.target.value, selectedIds[1]])}
              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
            >
              {reports.map((report) => (
                <option key={report.eval_id} value={report.eval_id}>
                  {report.prompt_version} · {report.module} · {new Date(report.generated_at).toLocaleString()}
                </option>
              ))}
            </select>
            <select
              value={selectedIds[1]}
              onChange={(event) => setSelectedIds([selectedIds[0], event.target.value])}
              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
            >
              {reports.map((report) => (
                <option key={report.eval_id} value={report.eval_id}>
                  {report.prompt_version} · {report.module} · {new Date(report.generated_at).toLocaleString()}
                </option>
              ))}
            </select>
          </div>
          <ReactECharts option={compareOption} style={{ height: 320 }} />
        </GlassCard>

        <GlassCard padding="md" hoverable={false}>
          <SectionTitle title="Trace Distribution" subtitle="Volume, latency, and success rate by module over the last 24 hours." />
          <ReactECharts option={traceOption} style={{ height: 260 }} />
          <div className="mt-4 space-y-3">
            {Object.entries(traceStats.by_module ?? {}).map(([module, stats]) => (
              <div key={module} className="flex items-center justify-between rounded-lg bg-white/60 px-3 py-2">
                <div>
                  <p className="text-sm font-semibold text-slate-900">{module}</p>
                  <p className="text-xs text-slate-500">{stats.calls} calls · {stats.avg_latency_ms.toFixed(0)} ms</p>
                </div>
                <StatusBadge status={stats.success_rate >= 0.95 ? "completed" : "running"}>
                  {formatPct(stats.success_rate)}
                </StatusBadge>
              </div>
            ))}
          </div>
        </GlassCard>
      </div>

      <GlassCard padding="md" hoverable={false}>
        <SectionTitle title="Case-level Results" subtitle="Inspect each golden case, including status, latency, and judge score." />
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead>
              <tr className="text-left text-slate-500">
                <th className="px-3 py-2 font-medium">Case ID</th>
                <th className="px-3 py-2 font-medium">Prompt</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium">Latency</th>
                <th className="px-3 py-2 font-medium">Judge Score</th>
                <th className="px-3 py-2 font-medium">Notes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {reports.flatMap((report) =>
                report.results.map((result) => (
                  <tr key={`${report.eval_id}-${result.case_id}`}>
                    <td className="px-3 py-3 font-medium text-slate-900">{result.case_id}</td>
                    <td className="px-3 py-3 text-slate-600">{report.prompt_version}</td>
                    <td className="px-3 py-3">
                      <StatusBadge status={result.passed ? "completed" : "failed"}>
                        {result.passed ? "Passed" : "Failed"}
                      </StatusBadge>
                    </td>
                    <td className="px-3 py-3 text-slate-600">{result.latency_ms} ms</td>
                    <td className="px-3 py-3 text-slate-600">{formatPct(result.score)}</td>
                    <td className="px-3 py-3 text-slate-500">{result.notes ?? "—"}</td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        </div>
      </GlassCard>
    </div>
  );
}
