import React from 'react';

const QuotaHealthBar = ({ resources, usage }) => {
  if (!resources?.length || !usage) return null;

  const tiers = resources.reduce((acc, r) => {
    const count = usage[r.key];
    if (count == null || count === 'error' || !r.threshold) return acc;
    const pct = count / r.threshold;
    if (pct > 0.8) acc.critical++;
    else if (pct >= 0.5) acc.warning++;
    else acc.healthy++;
    return acc;
  }, { healthy: 0, warning: 0, critical: 0 });

  const total = tiers.healthy + tiers.warning + tiers.critical;
  if (total === 0) return null;
  const w = (n) => `${((n / total) * 100).toFixed(1)}%`;

  const Dot = ({ color, children }) => (
    <span className="flex items-center gap-1 text-[10px] font-medium text-gray-600">
      <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }} />
      {children}
    </span>
  );

  return (
    <div>
      <div className="bg-gray-100 rounded-full h-2 overflow-hidden flex">
        {tiers.healthy > 0 && <div style={{ width: w(tiers.healthy), backgroundColor: '#22c55e' }} />}
        {tiers.warning > 0 && <div style={{ width: w(tiers.warning), backgroundColor: '#f59e0b' }} />}
        {tiers.critical > 0 && <div style={{ width: w(tiers.critical), backgroundColor: '#ef4444' }} />}
      </div>
      <div className="flex items-center gap-3 mt-1.5">
        <Dot color="#22c55e">{tiers.healthy} healthy</Dot>
        <Dot color="#f59e0b">{tiers.warning} warning</Dot>
        <Dot color="#ef4444">{tiers.critical} critical</Dot>
        {tiers.critical > 0 && (
          <span className="text-[10px] font-semibold text-red-600 ml-auto">
            !! {tiers.critical} over 80%
          </span>
        )}
      </div>
    </div>
  );
};

export default QuotaHealthBar;
