import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import type { ShapleyPoint } from "../lib/api";

const AGENT_COLORS: Record<string, string> = {
  tech_agent: "#4ade80",
  news_agent: "#60a5fa",
  risk_agent: "#f472b6",
};

function TrendSvg({ points }: { points: ShapleyPoint[] }) {
  const width = 720;
  const height = 180;
  const pad = 24;
  if (points.length === 0) return <div className="text-zinc-500 text-xs">no history yet</div>;

  const agents = Array.from(
    new Set(points.flatMap((p) => Object.keys(p.weights))),
  ).sort();
  const stepX = points.length > 1 ? (width - 2 * pad) / (points.length - 1) : 0;

  const paths = agents.map((agent) => {
    const d = points
      .map((p, i) => {
        const w = p.weights[agent] ?? 0;
        const x = pad + i * stepX;
        const y = height - pad - w * (height - 2 * pad);
        return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
      })
      .join(" ");
    return { agent, d };
  });

  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} className="border border-zinc-800 rounded bg-black/40">
      {[0, 0.25, 0.5, 0.75, 1].map((frac) => {
        const y = height - pad - frac * (height - 2 * pad);
        return (
          <g key={frac}>
            <line x1={pad} y1={y} x2={width - pad} y2={y} stroke="#27272a" strokeDasharray="2 3" />
            <text x={4} y={y + 3} fontSize="9" fill="#52525b">
              {frac.toFixed(2)}
            </text>
          </g>
        );
      })}
      {paths.map(({ agent, d }) => (
        <path
          key={agent}
          d={d}
          fill="none"
          stroke={AGENT_COLORS[agent] ?? "#a1a1aa"}
          strokeWidth="1.5"
        />
      ))}
      <g transform={`translate(${pad}, 12)`}>
        {agents.map((agent, i) => (
          <g key={agent} transform={`translate(${i * 130}, 0)`}>
            <rect width="10" height="10" fill={AGENT_COLORS[agent] ?? "#a1a1aa"} />
            <text x="14" y="9" fontSize="10" fill="#d4d4d8">
              {agent}
            </text>
          </g>
        ))}
      </g>
    </svg>
  );
}

export default function Shapley() {
  const leaderQ = useQuery({
    queryKey: ["shapley", "leaderboard"],
    queryFn: api.getShapleyLeaderboard,
  });
  const historyQ = useQuery({
    queryKey: ["shapley", "history", 10, 100],
    queryFn: () => api.getShapleyHistory(10, 100),
  });

  const leader = leaderQ.data;
  const history = historyQ.data?.points ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-sm uppercase tracking-widest text-zinc-400">shapley leaderboard</h1>
        {leader && Object.keys(leader.weights).length > 0 ? (
          <div className="flex gap-3 text-xs mt-2">
            {Object.entries(leader.weights)
              .sort((a, b) => b[1] - a[1])
              .map(([agent, w]) => (
                <span key={agent} className="border border-zinc-700 rounded px-3 py-2">
                  <span className="text-zinc-400">{agent}</span>{" "}
                  <span className="text-accent">{w.toFixed(3)}</span>
                </span>
              ))}
          </div>
        ) : (
          <div className="text-zinc-500 text-xs mt-2">no shapley rows yet</div>
        )}
      </div>

      <div>
        <h2 className="text-xs uppercase tracking-widest text-zinc-500 mb-2">
          rolling weights (last {history.length} aggregations)
        </h2>
        <TrendSvg points={history} />
      </div>
    </div>
  );
}
