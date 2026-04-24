const sha = (import.meta.env.VITE_GIT_SHA as string | undefined) ?? "dev";

const chips: Array<{ label: string; tone?: "accent" }> = [
  { label: "PROTOCOL TELEMETRY", tone: "accent" },
  { label: "23 / 23 TESTS" },
  { label: "DEVNET / FORK" },
  { label: "RFB-04" },
  { label: "RFB-05" },
  { label: "RFB-02" },
  { label: `git ${sha}` },
];

export default function ProtocolTelemetryFooter() {
  return (
    <footer className="border-t border-zinc-800/70 px-6 py-3 flex flex-wrap gap-2 text-xs">
      {chips.map((chip) => (
        <span
          key={chip.label}
          className={`px-2 py-1 rounded border ${
            chip.tone === "accent"
              ? "border-accent/70 text-accent"
              : "border-zinc-700 text-zinc-400"
          }`}
        >
          {chip.label}
        </span>
      ))}
    </footer>
  );
}
