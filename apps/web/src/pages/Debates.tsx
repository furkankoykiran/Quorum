import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../lib/api";

export default function Debates() {
  const q = useQuery({ queryKey: ["debates", "recent", 100], queryFn: () => api.getRecentDebates(100) });

  return (
    <div className="space-y-4">
      <h1 className="text-sm uppercase tracking-widest text-zinc-400">debates</h1>
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
            {(q.data ?? []).map((d) => (
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
    </div>
  );
}
