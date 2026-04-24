import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { api } from "../lib/api";

function JsonBlock({ title, value }: { title: string; value: unknown }) {
  if (value == null) return null;
  return (
    <section className="space-y-1">
      <div className="text-[10px] uppercase tracking-widest text-zinc-500">{title}</div>
      <pre className="border border-zinc-800 rounded p-3 bg-black/40 text-xs overflow-auto">
        {JSON.stringify(value, null, 2)}
      </pre>
    </section>
  );
}

export default function DebateDetail() {
  const { debateId = "" } = useParams();
  const q = useQuery({
    queryKey: ["debate", debateId],
    queryFn: () => api.getDebate(debateId),
    enabled: Boolean(debateId),
  });

  if (q.isLoading) return <div className="text-zinc-400">loading…</div>;
  if (q.isError) return <div className="text-red-400">error: {String(q.error)}</div>;
  if (!q.data) return null;

  const d = q.data;
  return (
    <div className="space-y-5">
      <div>
        <Link to="/debates" className="text-xs text-zinc-500 hover:text-accent">
          ← all debates
        </Link>
        <h1 className="mt-1 text-sm uppercase tracking-widest text-zinc-400">
          {d.symbol} · {new Date(d.ts).toISOString().replace("T", " ").slice(0, 19)} ·{" "}
          <span className="text-accent">{d.final_decision}</span>
        </h1>
      </div>

      <section className="space-y-2">
        <div className="text-[10px] uppercase tracking-widest text-zinc-500">transcript</div>
        {d.transcript.map((turn, idx) => {
          const parseFailed = turn.rationale.startsWith("[parse_failed]");
          return (
            <div
              key={idx}
              className={`border rounded p-3 text-xs ${
                parseFailed ? "border-zinc-800 text-zinc-600" : "border-zinc-700"
              }`}
            >
              <div className="flex items-center gap-3">
                <span className="text-accent">[{turn.agent}]</span>
                <span className="text-zinc-200">{turn.vote}</span>
                {parseFailed && (
                  <span className="text-[10px] text-red-400 border border-red-500/30 rounded px-1">
                    parse_failed
                  </span>
                )}
              </div>
              <div className="mt-1 text-zinc-400 whitespace-pre-wrap">{turn.rationale}</div>
            </div>
          );
        })}
      </section>

      <JsonBlock title="pyth" value={d.pyth_price} />
      <JsonBlock title="jupiter quote" value={d.jupiter_quote} />
      {d.dry_run_signature && (
        <section className="space-y-1">
          <div className="text-[10px] uppercase tracking-widest text-zinc-500">
            dry-run signature
          </div>
          <div className="text-xs text-zinc-300 break-all">{d.dry_run_signature}</div>
        </section>
      )}

      {d.shapley_weights && (
        <section className="space-y-2">
          <div className="text-[10px] uppercase tracking-widest text-zinc-500">
            shapley weights
          </div>
          <div className="flex gap-3 text-xs">
            {Object.entries(d.shapley_weights).map(([agent, w]) => (
              <span key={agent} className="border border-zinc-700 rounded px-2 py-1">
                {agent} · <span className="text-accent">{w.toFixed(3)}</span>
              </span>
            ))}
          </div>
          {d.shapley_rationale && (
            <pre className="border border-zinc-800 rounded p-3 bg-black/40 text-xs whitespace-pre-wrap">
              {d.shapley_rationale}
            </pre>
          )}
        </section>
      )}

      <JsonBlock title="shapley rolling" value={d.shapley_rolling_weights} />
    </div>
  );
}
