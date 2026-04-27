"use client";

import { createContext, useContext } from "react";
import clsx from "clsx";

interface TabsContextValue {
  value: string;
  onChange: (value: string) => void;
}

const TabsContext = createContext<TabsContextValue | null>(null);

function useTabs() {
  const ctx = useContext(TabsContext);
  if (!ctx) throw new Error("Tabs components must be used inside <Tabs>");
  return ctx;
}

interface TabsProps {
  value: string;
  onChange: (value: string) => void;
  children: React.ReactNode;
  className?: string;
}

export function Tabs({ value, onChange, children, className }: TabsProps) {
  return (
    <TabsContext.Provider value={{ value, onChange }}>
      <div className={clsx("flex flex-col", className)}>{children}</div>
    </TabsContext.Provider>
  );
}

interface TabsListProps {
  children: React.ReactNode;
  className?: string;
}

export function TabsList({ children, className }: TabsListProps) {
  return (
    <div
      role="tablist"
      className={clsx(
        "flex items-center gap-1 border-b border-slate-200 bg-white px-4",
        className,
      )}
    >
      {children}
    </div>
  );
}

interface TabsTriggerProps {
  value: string;
  children: React.ReactNode;
  badge?: string | number;
  disabled?: boolean;
}

export function TabsTrigger({ value, children, badge, disabled }: TabsTriggerProps) {
  const { value: active, onChange } = useTabs();
  const selected = active === value;
  return (
    <button
      type="button"
      role="tab"
      aria-selected={selected}
      disabled={disabled}
      onClick={() => onChange(value)}
      className={clsx(
        "relative px-4 py-2.5 text-sm font-medium transition-colors -mb-px",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400/40 rounded-t",
        selected
          ? "text-teal-700 border-b-2 border-teal-500"
          : "text-slate-500 border-b-2 border-transparent hover:text-slate-700",
        disabled && "opacity-40 cursor-not-allowed",
      )}
    >
      <span className="inline-flex items-center gap-1.5">
        {children}
        {badge !== undefined && (
          <span
            className={clsx(
              "text-[10px] font-semibold px-1.5 py-0.5 rounded-full",
              selected ? "bg-teal-100 text-teal-700" : "bg-slate-100 text-slate-500",
            )}
          >
            {badge}
          </span>
        )}
      </span>
    </button>
  );
}

interface TabsContentProps {
  value: string;
  children: React.ReactNode;
  className?: string;
}

export function TabsContent({ value, children, className }: TabsContentProps) {
  const { value: active } = useTabs();
  if (active !== value) return null;
  return (
    <div role="tabpanel" className={clsx("flex-1 overflow-y-auto", className)}>
      {children}
    </div>
  );
}
