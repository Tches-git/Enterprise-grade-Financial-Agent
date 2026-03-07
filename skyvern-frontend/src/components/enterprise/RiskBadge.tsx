/**
 * Risk level badge with color coding.
 */

import { cn } from "@/util/utils";

type RiskLevel = "low" | "medium" | "high" | "critical";

const riskConfig: Record<RiskLevel, { bg: string; text: string; label: string }> = {
  low:      { bg: "bg-green-50",  text: "text-green-700",  label: "Low" },
  medium:   { bg: "bg-amber-50",  text: "text-amber-700",  label: "Medium" },
  high:     { bg: "bg-red-50",    text: "text-red-700",    label: "High" },
  critical: { bg: "bg-red-100",   text: "text-red-900",    label: "Critical" },
};

type RiskBadgeProps = {
  level: RiskLevel | string;
  className?: string;
};

export function RiskBadge({ level, className }: RiskBadgeProps) {
  const config = riskConfig[level as RiskLevel] ?? {
    bg: "bg-gray-50",
    text: "text-gray-600",
    label: level,
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
