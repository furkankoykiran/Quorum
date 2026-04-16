/**
 * Read-only Jupiter swap simulation (no signing, no broadcast).
 *
 * Quotes Jupiter for the requested mint pair, builds the swap instruction
 * set as if the supplied --fee-payer would execute it, packs into a v0
 * VersionedTransaction with the resolved address-lookup-tables, then asks
 * a Solana RPC to `simulateTransaction` with sigVerify=false and
 * replaceRecentBlockhash=true. No keypairs are loaded.
 *
 * The orchestrator calls this every BUY/SELL cycle and attaches the
 * returned `tx_message_b64` to the debate state as `dry_run_signature`,
 * so 24/7 demo cycles produce verifiable provenance without flipping
 * QUORUM_LIVE.
 *
 * Output: a single JSON line on stdout with shape:
 *   {
 *     "simulated": true,
 *     "logs_tail": ["last", "5", "log", "lines"],
 *     "err": null | <RPC error JSON>,
 *     "compute_units": <number|null>,
 *     "tx_message_b64": "<base64 of the v0 message>"
 *   }
 *
 * Exit codes: 0 on a completed simulation (even when err is non-null);
 * 1 on quote / RPC / build failure.
 *
 * Usage:
 *   pnpm tsx src/vault-swap-dry.ts \
 *     --input-mint <pubkey> \
 *     --output-mint <pubkey> \
 *     --amount-raw <bigint> \
 *     [--slippage 50] \
 *     [--rpc-url https://api.mainnet-beta.solana.com] \
 *     [--fee-payer <pubkey>] \
 *     [--jup-base-url https://lite-api.jup.ag/swap/v1]
 */

import {
  AddressLookupTableAccount,
  Connection,
  PublicKey,
  TransactionInstruction,
  TransactionMessage,
  VersionedTransaction,
} from "@solana/web3.js";
import {
  Configuration,
  type Instruction as JupiterInstruction,
  SwapApi,
} from "@jup-ag/api";

const DEFAULT_RPC = "https://api.mainnet-beta.solana.com";
const DEFAULT_JUP_BASE = "https://lite-api.jup.ag/swap/v1";
// Default fee-payer is operator-1's public key — a regular keypair address
// (not a program account) so simulation's account-offset sanitiser doesn't
// trip on a duplicated programId. With sigVerify=false and
// replaceRecentBlockhash=true we don't actually need this address to hold
// any mainnet SOL; the RPC simulate path skips fee deduction.
const DEFAULT_FEE_PAYER = "8CBCG78opffKEFwfSN3bKXcL8Te8wGDQHBCDdcBWiBYz";

function getArg(name: string): string | undefined {
  const idx = process.argv.indexOf(name);
  if (idx !== -1 && process.argv[idx + 1]) {
    return process.argv[idx + 1];
  }
  return undefined;
}

function requirePubkey(arg: string, label: string): PublicKey {
  try {
    return new PublicKey(arg);
  } catch {
    throw new Error(`Invalid base58 public key for ${label}: "${arg}"`);
  }
}

function toTxIx(ix: JupiterInstruction): TransactionInstruction {
  return new TransactionInstruction({
    programId: new PublicKey(ix.programId),
    keys: ix.accounts.map((a) => ({
      pubkey: new PublicKey(a.pubkey),
      isSigner: a.isSigner,
      isWritable: a.isWritable,
    })),
    data: Buffer.from(ix.data, "base64"),
  });
}

async function fetchLookupTables(
  connection: Connection,
  addresses: string[]
): Promise<AddressLookupTableAccount[]> {
  if (addresses.length === 0) return [];
  const out: AddressLookupTableAccount[] = [];
  for (const addr of addresses) {
    const resp = await connection.getAddressLookupTable(new PublicKey(addr));
    if (!resp.value) {
      throw new Error(`Address lookup table not found: ${addr}`);
    }
    out.push(resp.value);
  }
  return out;
}

async function main(): Promise<void> {
  const inputMintArg = getArg("--input-mint");
  const outputMintArg = getArg("--output-mint");
  const amountRawArg = getArg("--amount-raw");
  if (!inputMintArg || !outputMintArg || !amountRawArg) {
    throw new Error(
      "Missing required args: --input-mint <pk> --output-mint <pk> --amount-raw <bigint>"
    );
  }

  const inputMint = requirePubkey(inputMintArg, "--input-mint");
  const outputMint = requirePubkey(outputMintArg, "--output-mint");
  const amountRaw = BigInt(amountRawArg);
  const slippageBps = parseInt(getArg("--slippage") ?? "50", 10);
  const rpcUrl = getArg("--rpc-url") ?? DEFAULT_RPC;
  const jupBase = getArg("--jup-base-url") ?? DEFAULT_JUP_BASE;
  const feePayer = requirePubkey(
    getArg("--fee-payer") ?? DEFAULT_FEE_PAYER,
    "--fee-payer"
  );

  const jup = new SwapApi(new Configuration({ basePath: jupBase }));
  const quote = await jup.quoteGet({
    inputMint: inputMint.toBase58(),
    outputMint: outputMint.toBase58(),
    amount: Number(amountRaw),
    slippageBps,
    restrictIntermediateTokens: true,
  });

  const swapIxResp = await jup.swapInstructionsPost({
    swapRequest: {
      quoteResponse: quote,
      userPublicKey: feePayer.toBase58(),
      wrapAndUnwrapSol: false,
      useSharedAccounts: true,
    },
  });

  const innerInstructions: TransactionInstruction[] = [
    ...swapIxResp.computeBudgetInstructions.map(toTxIx),
    ...swapIxResp.setupInstructions.map(toTxIx),
    toTxIx(swapIxResp.swapInstruction),
    ...(swapIxResp.cleanupInstruction
      ? [toTxIx(swapIxResp.cleanupInstruction)]
      : []),
  ];

  const connection = new Connection(rpcUrl, "confirmed");
  const lookupTables = await fetchLookupTables(
    connection,
    swapIxResp.addressLookupTableAddresses
  );

  const { blockhash } = await connection.getLatestBlockhash();
  const message = new TransactionMessage({
    payerKey: feePayer,
    recentBlockhash: blockhash,
    instructions: innerInstructions,
  }).compileToV0Message(lookupTables);
  const tx = new VersionedTransaction(message);

  const sim = await connection.simulateTransaction(tx, {
    sigVerify: false,
    replaceRecentBlockhash: true,
    commitment: "confirmed",
  });

  const logs = sim.value.logs ?? [];
  const messageB64 = Buffer.from(message.serialize()).toString("base64");

  const payload = {
    simulated: true,
    err: sim.value.err ?? null,
    compute_units: sim.value.unitsConsumed ?? null,
    logs_tail: logs.slice(-5),
    tx_message_b64: messageB64,
    quote_out_amount: quote.outAmount,
    quote_route_hops: quote.routePlan.length,
  };

  // Single JSON line on stdout for the Python wrapper to consume.
  process.stdout.write(JSON.stringify(payload) + "\n");
}

main().catch((err) => {
  console.error(
    "vault-swap-dry failed:",
    err instanceof Error ? err.message : err
  );
  process.exit(1);
});
