/**
 * Shapley-weighted payout instruction scaffold (Day 14).
 *
 * Reads a payout schedule `{operator_pubkey: weight_float}` from stdin and a
 * total fee in lamports from --fee-lamports. Computes `floor(weight * fee)`
 * per operator, routes the rounding residual to the first operator in
 * iteration order (operator-1 by convention), then wraps the resulting
 * SystemProgram.transfer batch in a Squads V4 vault transaction:
 *   multisig.instructions.vaultTransactionCreate
 *   + proposalCreate
 *   + proposalApprove x3  (operators 1..3, meets the 3-of-5 threshold)
 *
 * Gated twice behind `--submit` AND `QUORUM_PAYOUT_LIVE=1`: the default
 * path is dry-run — it logs the planned schedule and prints a JSON line
 * on stdout for the Python bridge (`dry_run_payout`) to parse, then exits
 * 0 without touching the wire. Both gates must align for the script to
 * actually propose/approve on-chain.
 *
 * Uses `multisig.instructions.*` builders and a manual `sendTransaction`
 * path (not `multisig.rpc.*`) because the SDK's rpc helpers wrap errors
 * through a `logs` setter that fails on Node 24 and swallows the real
 * program error — see the `squads_sdk_error_wrapping` project memory.
 *
 * Usage (dry-run):
 *   echo '{"<pubkey>": 0.5, "<pubkey>": 0.5}' \
 *     | pnpm tsx src/payout.ts --fee-lamports 100000
 *
 * Usage (live, double-gated):
 *   QUORUM_PAYOUT_LIVE=1 echo '{...}' \
 *     | pnpm tsx src/payout.ts --fee-lamports 100000 --submit
 */

import {
  Connection,
  Keypair,
  PublicKey,
  SendTransactionError,
  SystemProgram,
  TransactionInstruction,
  TransactionMessage,
  VersionedTransaction,
} from "@solana/web3.js";
import * as multisig from "@sqds/multisig";
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const NUM_OPERATORS = 5;
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const KEYS_DIR = path.resolve(REPO_ROOT, "keys");
const DEFAULT_FORK_MULTISIG_PATH = path.resolve(KEYS_DIR, "fork-multisig.txt");
const DEFAULT_FORK_RPC = "http://127.0.0.1:18899";

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

function getArg(name: string): string | undefined {
  const idx = process.argv.indexOf(name);
  if (idx !== -1 && process.argv[idx + 1]) {
    return process.argv[idx + 1];
  }
  return undefined;
}

function hasFlag(name: string): boolean {
  return process.argv.includes(name);
}

async function readStdin(): Promise<string> {
  return await new Promise((resolve, reject) => {
    let buf = "";
    process.stdin.setEncoding("utf-8");
    process.stdin.on("data", (chunk) => {
      buf += chunk;
    });
    process.stdin.on("end", () => resolve(buf));
    process.stdin.on("error", reject);
    if (process.stdin.isTTY) {
      reject(new Error("stdin is a TTY — pipe the payout-schedule JSON in"));
    }
  });
}

// ---------------------------------------------------------------------------
// Schedule maths (mirrors apps/orchestrator/tools/payout.py)
// ---------------------------------------------------------------------------

export interface ScheduleEntry {
  operator: string;
  weight: number;
  lamports: number;
}

export interface ComputedSchedule {
  entries: ScheduleEntry[];
  total_fee_lamports: number;
  allocated_lamports: number;
  residual_lamports: number;
  residual_operator: string;
}

export function computeSchedule(
  weights: Record<string, number>,
  totalFeeLamports: number
): ComputedSchedule {
  const keys = Object.keys(weights);
  if (keys.length === 0) {
    throw new Error("Empty payout schedule — at least one operator required");
  }
  if (!Number.isFinite(totalFeeLamports) || totalFeeLamports < 0) {
    throw new Error("total fee lamports must be a non-negative finite integer");
  }
  const total = Math.floor(totalFeeLamports);
  const entries: ScheduleEntry[] = [];
  let allocated = 0;
  for (const operator of keys) {
    const w = weights[operator];
    if (!Number.isFinite(w) || w < 0 || w > 1) {
      throw new Error(`Weight for ${operator} must be a finite number in [0, 1]: ${w}`);
    }
    const lamports = Math.floor(w * total);
    allocated += lamports;
    entries.push({ operator, weight: w, lamports });
  }
  // Rounding residual → first key (operator-1 by convention).
  const residual = total - allocated;
  if (residual > 0 && entries.length > 0) {
    entries[0].lamports += residual;
  }
  return {
    entries,
    total_fee_lamports: total,
    allocated_lamports: allocated + residual,
    residual_lamports: residual,
    residual_operator: entries[0].operator,
  };
}

// ---------------------------------------------------------------------------
// Keypair helpers (mirrors vault-swap.ts)
// ---------------------------------------------------------------------------

function loadKeypair(filePath: string): Keypair {
  const raw = fs.readFileSync(filePath, "utf-8");
  return Keypair.fromSecretKey(Uint8Array.from(JSON.parse(raw)));
}

function loadOperators(): Keypair[] {
  const operators: Keypair[] = [];
  for (let i = 1; i <= NUM_OPERATORS; i++) {
    const keyPath = path.join(KEYS_DIR, `operator-${i}.json`);
    if (!fs.existsSync(keyPath)) {
      throw new Error(`Missing keypair: ${keyPath}`);
    }
    operators.push(loadKeypair(keyPath));
  }
  return operators;
}

function readMultisigPda(pathStr: string): PublicKey {
  if (!fs.existsSync(pathStr)) {
    throw new Error(
      `Fork multisig PDA file not found at ${pathStr}. Run fork-bootstrap.sh first.`
    );
  }
  const raw = fs.readFileSync(pathStr, "utf-8").trim();
  return new PublicKey(raw);
}

async function sendAndConfirmIx(
  connection: Connection,
  instruction: TransactionInstruction,
  feePayer: Keypair,
  signers: Keypair[],
  label: string
): Promise<string> {
  const latest = await connection.getLatestBlockhash();
  const messageV0 = new TransactionMessage({
    payerKey: feePayer.publicKey,
    recentBlockhash: latest.blockhash,
    instructions: [instruction],
  }).compileToV0Message();
  const tx = new VersionedTransaction(messageV0);
  tx.sign(signers);

  try {
    const sig = await connection.sendTransaction(tx, { skipPreflight: false });
    await connection.confirmTransaction(
      {
        signature: sig,
        blockhash: latest.blockhash,
        lastValidBlockHeight: latest.lastValidBlockHeight,
      },
      "confirmed"
    );
    return sig;
  } catch (err) {
    if (err instanceof SendTransactionError) {
      console.error(`[${label}] send failed:`, err.message);
      try {
        const logs = await err.getLogs(connection);
        console.error("Program logs:");
        for (const line of logs) console.error(`  ${line}`);
      } catch {
        // logs may be unavailable
      }
    }
    throw err;
  }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  const feeArg = getArg("--fee-lamports");
  if (!feeArg) {
    throw new Error("Missing required --fee-lamports <n>");
  }
  const totalFeeLamports = Number.parseInt(feeArg, 10);
  if (!Number.isInteger(totalFeeLamports) || totalFeeLamports < 0) {
    throw new Error(`--fee-lamports must be a non-negative integer: ${feeArg}`);
  }

  const submit = hasFlag("--submit");
  const payoutLive = process.env.QUORUM_PAYOUT_LIVE === "1";
  const rpcUrl =
    getArg("--url") ?? process.env.SOLANA_RPC_URL ?? DEFAULT_FORK_RPC;
  const multisigPath = getArg("--multisig-file") ?? DEFAULT_FORK_MULTISIG_PATH;

  const stdinRaw = await readStdin();
  let weights: Record<string, number>;
  try {
    const parsed = JSON.parse(stdinRaw);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      throw new Error("stdin must be an object {pubkey: weight_float}");
    }
    weights = parsed as Record<string, number>;
  } catch (err) {
    throw new Error(
      `Could not parse stdin as JSON: ${err instanceof Error ? err.message : err}`
    );
  }

  // Validate every pubkey up-front so the error is surfaced before network IO.
  for (const key of Object.keys(weights)) {
    try {
      new PublicKey(key);
    } catch {
      throw new Error(`Invalid base58 operator pubkey: "${key}"`);
    }
  }

  const schedule = computeSchedule(weights, totalFeeLamports);

  // The dry-run JSON is printed regardless of gating so the Python bridge has
  // a machine-readable contract.
  const dryRunPayload = {
    dry_run: !(submit && payoutLive),
    submit,
    payout_live: payoutLive,
    rpc_url: rpcUrl,
    multisig_path: multisigPath,
    schedule: schedule.entries,
    total_fee_lamports: schedule.total_fee_lamports,
    residual_lamports: schedule.residual_lamports,
    residual_operator: schedule.residual_operator,
  };

  console.error(
    `[payout] mode=${dryRunPayload.dry_run ? "DRY-RUN" : "LIVE (fork)"}` +
      `  operators=${schedule.entries.length}` +
      `  fee=${schedule.total_fee_lamports} lamports` +
      `  residual=${schedule.residual_lamports} -> ${schedule.residual_operator}`
  );
  for (const entry of schedule.entries) {
    console.error(
      `  ${entry.operator}  weight=${entry.weight.toFixed(4)}  lamports=${entry.lamports}`
    );
  }

  if (!(submit && payoutLive)) {
    // Refuse to broadcast unless both gates are set. Print the schedule as a
    // single JSON line on stdout so tools/payout.py::dry_run_payout can parse
    // the last line (same pattern as tools/dry_run.py).
    if (submit && !payoutLive) {
      console.error(
        "[payout] --submit set but QUORUM_PAYOUT_LIVE!=1; refusing to broadcast."
      );
    }
    console.log(JSON.stringify(dryRunPayload));
    return;
  }

  // -------------------------------------------------------------------------
  // LIVE branch — only reachable when both gates align.
  // -------------------------------------------------------------------------
  const multisigPda = readMultisigPda(multisigPath);
  const connection = new Connection(rpcUrl, "confirmed");
  const operators = loadOperators();
  const creator = operators[0];
  const [vaultPda] = multisig.getVaultPda({ multisigPda, index: 0 });

  const transferIxs: TransactionInstruction[] = schedule.entries.map((entry) =>
    SystemProgram.transfer({
      fromPubkey: vaultPda,
      toPubkey: new PublicKey(entry.operator),
      lamports: entry.lamports,
    })
  );

  const { blockhash: innerBlockhash } = await connection.getLatestBlockhash();
  const innerMessage = new TransactionMessage({
    payerKey: vaultPda,
    recentBlockhash: innerBlockhash,
    instructions: transferIxs,
  });

  const multisigAccount = await multisig.accounts.Multisig.fromAccountAddress(
    connection,
    multisigPda
  );
  const newIndex = BigInt(multisigAccount.transactionIndex.toString()) + 1n;
  console.error(`[payout] next transactionIndex = ${newIndex}`);

  const createIx = multisig.instructions.vaultTransactionCreate({
    multisigPda,
    transactionIndex: newIndex,
    creator: creator.publicKey,
    vaultIndex: 0,
    ephemeralSigners: 0,
    transactionMessage: innerMessage,
    memo: "quorum payout",
  });
  const createSig = await sendAndConfirmIx(
    connection,
    createIx,
    creator,
    [creator],
    "vaultTransactionCreate"
  );

  const proposalIx = multisig.instructions.proposalCreate({
    multisigPda,
    creator: creator.publicKey,
    transactionIndex: newIndex,
  });
  const proposalSig = await sendAndConfirmIx(
    connection,
    proposalIx,
    creator,
    [creator],
    "proposalCreate"
  );

  const approveSigs: string[] = [];
  for (let i = 0; i < 3; i++) {
    const member = operators[i];
    const approveIx = multisig.instructions.proposalApprove({
      multisigPda,
      transactionIndex: newIndex,
      member: member.publicKey,
    });
    const signers = i === 0 ? [creator] : [creator, member];
    const sig = await sendAndConfirmIx(
      connection,
      approveIx,
      creator,
      signers,
      `proposalApprove-operator-${i + 1}`
    );
    approveSigs.push(sig);
  }

  const livePayload = {
    ...dryRunPayload,
    dry_run: false,
    signatures: {
      vault_transaction_create: createSig,
      proposal_create: proposalSig,
      proposal_approve_1: approveSigs[0],
      proposal_approve_2: approveSigs[1],
      proposal_approve_3: approveSigs[2],
    },
    transaction_index: newIndex.toString(),
  };
  console.log(JSON.stringify(livePayload));
}

// Allow this file to be imported for unit tests without running main().
const isMain =
  process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  main().catch((err) => {
    console.error("payout failed:", err instanceof Error ? err.message : err);
    process.exit(1);
  });
}
