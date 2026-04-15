/**
 * Pyth Hermes price reader.
 *
 * Fetches a single price feed (default: SOL/USD) from Pyth's Hermes REST endpoint
 * and prints the latest price, ±1σ confidence interval, publish timestamp, and
 * staleness in seconds.
 *
 * Exit codes:
 *   0  success and staleness <= --max-stale (default 60s)
 *   1  network error, missing parsed payload, or staleness above threshold
 *
 * The Risk agent (Day 9+) will call the same code path before approving a
 * proposed Jupiter swap, so the threshold and output format are kept stable.
 *
 * Usage:
 *   pnpm tsx src/check-price.ts [--feed <hex-id>] [--endpoint <url>] [--max-stale <seconds>]
 *
 * Defaults:
 *   --feed       = ef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d  (SOL/USD)
 *   --endpoint   = https://hermes.pyth.network
 *   --max-stale  = 60
 */

import { HermesClient } from "@pythnetwork/hermes-client";

const SOL_USD_FEED_ID =
  "ef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d";
const DEFAULT_ENDPOINT = "https://hermes.pyth.network";
const DEFAULT_MAX_STALE_SECONDS = 60;

function getArg(name: string): string | undefined {
  const idx = process.argv.indexOf(name);
  if (idx !== -1 && process.argv[idx + 1]) {
    return process.argv[idx + 1];
  }
  return undefined;
}

function normaliseFeedId(raw: string): string {
  return raw.toLowerCase().replace(/^0x/, "");
}

function scalePrice(rawPrice: string, expo: number): number {
  // Pyth encodes prices as int64 strings with a base-10 exponent.
  // expo is typically negative (e.g. -8 for SOL/USD => price * 1e-8).
  return Number(rawPrice) * 10 ** expo;
}

async function main(): Promise<void> {
  const feedId = normaliseFeedId(getArg("--feed") ?? SOL_USD_FEED_ID);
  const endpoint = getArg("--endpoint") ?? DEFAULT_ENDPOINT;
  const maxStale = Number(getArg("--max-stale") ?? DEFAULT_MAX_STALE_SECONDS);

  const client = new HermesClient(endpoint);
  const update = await client.getLatestPriceUpdates([feedId], { parsed: true });

  if (!update.parsed || update.parsed.length === 0) {
    console.error(`No parsed price update returned for feed ${feedId}`);
    process.exit(1);
  }

  const entry = update.parsed[0];
  const price = scalePrice(entry.price.price, entry.price.expo);
  const conf = scalePrice(entry.price.conf, entry.price.expo);
  const publishTime = entry.price.publish_time;
  const publishedIso = new Date(publishTime * 1000).toISOString();
  const stalenessSec = Math.floor(Date.now() / 1000) - publishTime;

  console.log(`feed=${feedId.slice(0, 16)}…   endpoint=${endpoint}`);
  console.log(`price=$${price.toFixed(4)}  ±$${conf.toFixed(4)} (1σ)`);
  console.log(`published=${publishedIso}  staleness=${stalenessSec}s`);

  if (stalenessSec > maxStale) {
    console.error(
      `STALE: ${stalenessSec}s > --max-stale ${maxStale}s — refusing.`
    );
    process.exit(1);
  }
}

main().catch((err) => {
  console.error("check-price failed:", err instanceof Error ? err.message : err);
  process.exit(1);
});
