/**
 * Status badge with color-coded labels for task states.
 */

import { cn } from "@/util/utils";

type TaskStatus =
  | "running"
  | "completed"
  | "failed"
  | "pending_approval"
  | "needs_human"
  | "paused"
  | "queued"
  | "timeout"
  | "created"
  | "terminated"
  | "canceled";

const statusConfig: Record<string, { bg: string; text: string; label: string }> = {
  running:          { bg: "bg-blue-50",    text: "text-blue-700",    label: "Running" },
  completed:        { bg: "bg-green-50",   text: "text-green-700",   label: "Completed" },
  failed:           { bg: "bg-red-50",     text: "text-red-700",     label: "Failed" },
  pending_approval: { bg: "bg-amber-50",   text: "text-amber-700",   label: "Pending Approval" },
  needs_human:      { bg: "bg-orange-50",  text: "text-orange-700",  label: "Needs Human" },
  paused:           { bg: "bg-purple-50",  text: "text-purple-700",  label: "Paused" },
  queued:           { bg: "bg-gray-50",    text: "text-gray-600",    label: "Queued" },
  timeout:          { bg: "bg-red-50",     text: "text-red-800",     label: "Timeout" },
  created:          { bg: "bg-sky-50",     text: "text-sky-700",     label: "Created" },
  terminated:       { bg: "bg-gray-100",   text: "text-gray-700",    label: "Terminated" },
  canceled:         { bg: "bg-gray-100",   text: "text-gray-600",    label: "Canceled" },
};

type StatusBadgeProps = {
  status: TaskStatus | string;
  className?: string;
};

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const config = statusConfig[status] ?? {
    bg: "bg-gray-50",
    text: "text-gray-600",
    label: status,
  };

  return (
    <span
      className={cn(
        "glass-badge",
        config.bg,
        config.text,
        className,
      )}
    >
      {config.label}
    </span>
  );
}
