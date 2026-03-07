/**
 * Enterprise sidebar navigation with frosted-glass style.
 * Replaces original SideNav with enterprise menu items.
 */

import { NavLink } from "react-router-dom";
import { Icon, type IconName } from "@/components/Icon";
import { cn } from "@/util/utils";
import { useSidebarStore } from "@/store/SidebarStore";

type NavItem = {
  label: string;
  to: string;
  icon: IconName;
};

const buildSection: NavItem[] = [
  { label: "Discover",   to: "/discover",  icon: "search" },
  { label: "Tasks",       to: "/tasks",     icon: "task" },
  { label: "Workflows",   to: "/workflows", icon: "workflow" },
  { label: "Runs",        to: "/runs",      icon: "refresh" },
];

const enterpriseSection: NavItem[] = [
  { label: "Dashboard",   to: "/enterprise/dashboard",    icon: "dashboard" },
  { label: "Approvals",   to: "/enterprise/approvals",    icon: "approval" },
  { label: "Audit Logs",  to: "/enterprise/audit",        icon: "audit" },
  { label: "Permissions", to: "/enterprise/permissions",  icon: "permissions" },
];

const generalSection: NavItem[] = [
  { label: "Settings",    to: "/settings",     icon: "settings" },
];

function NavSection({
  title,
  items,
  collapsed,
}: {
  title: string;
  items: NavItem[];
  collapsed: boolean;
}) {
  return (
    <div className="mb-6">
      {!collapsed && (
        <div
          className="mb-2 px-3 text-[11px] font-semibold uppercase tracking-widest"
          style={{ color: "var(--finrpa-text-muted)" }}
        >
          {title}
        </div>
      )}
      <div className="space-y-1">
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              cn("glass-nav-item", {
                active: isActive,
                "justify-center px-2": collapsed,
              })
            }
            title={collapsed ? item.label : undefined}
          >
            <Icon
              name={item.icon}
              size={20}
            />
            {!collapsed && <span>{item.label}</span>}
          </NavLink>
        ))}
      </div>
    </div>
  );
}

export function EnterpriseSideNav() {
  const { collapsed } = useSidebarStore();

  return (
    <nav className="flex-1 overflow-y-auto py-2">
      <NavSection title="Build"      items={buildSection}      collapsed={collapsed} />
      <NavSection title="Enterprise" items={enterpriseSection} collapsed={collapsed} />
      <NavSection title="General"    items={generalSection}    collapsed={collapsed} />
    </nav>
  );
}
