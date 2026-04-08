import type { ReactNode } from 'react';

interface IndicatorPaneProps {
  label: string;
  children: ReactNode;
}

export function IndicatorPane({ label, children }: IndicatorPaneProps) {
  return (
    <div className="flex flex-col gap-1 w-full">
      <div className="text-xs text-[#94a3b8] font-medium px-2">{label}</div>
      <div className="w-full rounded-lg border border-[#1e293b] bg-[#0f172a] overflow-hidden">
        {children}
      </div>
    </div>
  );
}
