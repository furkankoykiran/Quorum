import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";

export default function Payout() {
  const q = useQuery({ queryKey: ["payout", "latest"], queryFn: api.getPayoutLatest });

  return (
    <div className="space-y-4">
      <h1 className="text-sm uppercase tracking-widest text-zinc-400">payout ledger</h1>
      <div className="border border-zinc-800 rounded p-4 bg-zinc-950/40 text-xs">
        {q.data?.payout == null ? (
          <div className="space-y-2">
            <div className="text-zinc-300">no payout entries yet</div>
            <div className="text-zinc-500">{q.data?.message ?? "loading…"}</div>
            <div className="text-zinc-500">
              Fee skim + Shapley-weighted payout graph hook arrive in M6 (Day 21–22). This view
              will render the dry-run schedule and, on demo day, the fork-broadcast payout txid.
            </div>
          </div>
        ) : (
          <pre className="whitespace-pre-wrap">{JSON.stringify(q.data.payout, null, 2)}</pre>
        )}
      </div>
    </div>
  );
}
