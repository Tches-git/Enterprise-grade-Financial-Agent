import { useSidebarStore } from "@/store/SidebarStore";
import { cn } from "@/util/utils";
import { SidebarContent } from "./SidebarContent";

function Sidebar() {
  const collapsed = useSidebarStore((state) => state.collapsed);

  return (
    <aside
      className={cn(
        "glass-sidebar fixed hidden h-screen min-h-screen lg:block",
        {
          "w-64": !collapsed,
          "w-20": collapsed,
        },
      )}
    >
      <SidebarContent useCollapsedState />
    </aside>
  );
}

export { Sidebar };
