import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../lib/api";
import type { DebateSummary, Stats } from "../lib/api";
import { useLiveDebates } from "../lib/useLiveDebates";

const statCards: Array<{ key: keyof Stats; label: string; fmt?: (v: number) => string }> = [
  { key: "total", label: "runs" },
  { key: "success_rate", label: "success %", fmt: (v) => `${v.toFixed(1)}%` },
  { key: "shapley_attached", label: "shapley attached" },
  { key: "pyth_gate_holds", label: "pyth holds" },
  { key: "parse_failures", label: "parse failures" },
  { key: "avg_latency", label: "avg latency", fmt: (v) => `${v.toFixed(1)}s` },
];

export default function Observatory() {
  const statsQ = useQuery({ queryKey: ["stats"], queryFn: api.getStats });
  const recentQ = useQuery({
    queryKey: ["debates", "recent", 20],
    queryFn: () => api.getRecentDebates(20),
  });
  const { debates: live, connected } = useLiveDebates();

  const recent: DebateSummary[] = recentQ.data ?? [];
  const stdout = live.length > 0 ? live : recent.slice(0, 10);

  return (
    <div className="space-y-6">
      <section className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {statCards.map((card) => {
          const raw = statsQ.data ? Number(statsQ.data[card.key] ?? 0) : 0;
          const value = card.fmt ? card.fmt(raw) : String(raw);
          return (
            <div
              key={card.key}
              className="border border-zinc-800 rounded p-3 bg-zinc-950/40"
            >
              <div className="text-[10px] uppercase tracking-widest text-zinc-500">
                {card.label}
              </div>
              <div className="text-xl mt-1 text-zinc-100">{value}</div>
            </div>
          );
        })}
      </section>

      <section>
        <h2 className="text-xs uppercase tracking-widest text-zinc-500 mb-2">
          agent reasoning · {connected ? "live" : "reconnecting…"}
        </h2>
        <div className="border border-zinc-800 rounded bg-black/40 p-3 text-xs leading-relaxed max-h-80 overflow-auto">
          {stdout.length === 0 && <div className="text-zinc-500">no debates yet</div>}
          {stdout.map((d) => (
            <div key={d.debate_id} className="mb-2">
              <span className="text-accent">
                [{new Date(d.ts).toISOString().slice(11, 19)}]
              </span>{" "}
              <span className="text-zinc-400">{d.symbol}</span>{" "}
              <span className="text-zinc-200">→ {d.final_decision}</span>{" "}
              <span className="text-zinc-500">
                (pyth:{d.pyth_gate ?? "n/a"}, top:{d.shapley_top_agent ?? "n/a"})
              </span>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-xs uppercase tracking-widest text-zinc-500 mb-2">recent debates</h2>
        <div className="border border-zinc-800 rounded overflow-hidden">
          <table className="w-full text-xs">
            <thead className="bg-zinc-900/60 text-zinc-500 uppercase tracking-widest">
              <tr>
                <th className="text-left px-3 py-2">ts</th>
                <th className="text-left px-3 py-2">symbol</th>
                <th className="text-left px-3 py-2">decision</th>
                <th className="text-left px-3 py-2">pyth</th>
                <th className="text-left px-3 py-2">top agent</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((d) => (
                <tr key={d.debate_id} className="border-t border-zinc-900 hover:bg-zinc-900/30">
                  <td className="px-3 py-2 text-zinc-400">
                    <Link to={`/debates/${encodeURIComponent(d.debate_id)}`}>
                      {new Date(d.ts).toISOString().slice(0, 19).replace("T", " ")}
                    </Link>
                  </td>
                  <td className="px-3 py-2">{d.symbol}</td>
                  <td className="px-3 py-2 text-accent">{d.final_decision}</td>
                  <td className="px-3 py-2 text-zinc-400">{d.pyth_gate ?? "-"}</td>
                  <td className="px-3 py-2 text-zinc-400">{d.shapley_top_agent ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
