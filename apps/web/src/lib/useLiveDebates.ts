import { useEffect, useRef, useState } from "react";

import type { DebateSummary } from "./api";

type LiveMessage =
  | ({ type: "debate" } & DebateSummary)
  | { type: "ping"; mono: number };

const MAX_BUFFER = 10;
const BACKOFF_MIN_MS = 1_000;
const BACKOFF_MAX_MS = 30_000;

export function useLiveDebates(): { debates: DebateSummary[]; connected: boolean } {
  const [debates, setDebates] = useState<DebateSummary[]>([]);
  const [connected, setConnected] = useState(false);
  const backoffRef = useRef(BACKOFF_MIN_MS);
  const wsRef = useRef<WebSocket | null>(null);
  const stopRef = useRef(false);

  useEffect(() => {
    stopRef.current = false;

    const connect = () => {
      if (stopRef.current) return;
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${window.location.host}/live/debates`);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        backoffRef.current = BACKOFF_MIN_MS;
      };
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data) as LiveMessage;
          if (msg.type === "debate") {
            setDebates((prev) => {
              if (prev[0]?.debate_id === msg.debate_id) return prev;
              return [msg, ...prev].slice(0, MAX_BUFFER);
            });
          }
        } catch {
          // ignore malformed frames
        }
      };
      ws.onclose = () => {
        setConnected(false);
        if (stopRef.current) return;
        const delay = backoffRef.current;
        backoffRef.current = Math.min(delay * 2, BACKOFF_MAX_MS);
        window.setTimeout(connect, delay);
      };
      ws.onerror = () => ws.close();
    };

    connect();

    return () => {
      stopRef.current = true;
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, []);

  return { debates, connected };
}
