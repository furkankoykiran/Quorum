/**
 * Wrap a Jupiter swap inside a Squads V4 vault transaction.
 *
 * Flow:
 *   1. Quote SOL->USDC (or any pair) via @jup-ag/api against the Jupiter prod API.
 *   2. Fetch raw swap instructions for the vault PDA as the user.
 *   3. Convert each Jupiter Instruction (programId/accounts/data-base64) into a
 *      web3.js TransactionInstruction.
 *   4. Compose an inner v0 message: [computeBudget..., setup..., swap, cleanup?].
 *   5. Resolve any address lookup tables from a mainnet RPC.
 *   6. multisig.instructions.vaultTransactionCreate (passes ALTs through),
 *      proposalCreate, proposalApprove x3 (operators 1..3 — meets 3-of-5),
 *      vaultTransactionExecute.
 *
 * Devnet caveat: Jupiter routes reference mainnet AMM accounts and lookup
 * tables that do NOT exist on devnet. The propose+approve flow succeeds, but
 * the on-chain execute step is expected to fail with "AccountNotFound" or
 * similar. We log the failure and exit 0 — the goal of Day 8 is to prove the
 * Squads integration, not to land a swap on devnet.
 *
 * Use --dry-run to skip the multisig flow entirely and just print the planned
 * inner message (useful for CI smoke and orchestrator stubs).
 *
 * Usage:
 *   pnpm tsx src/vault-swap.ts \
 *     --multisig <pda> \
 *     --input-mint <pubkey> \
 *     --output-mint <pubkey> \
 *     --amount <ui-tokens> \
 *     [--slippage 50] \
 *     [--url <devnet-rpc>] \
 *     [--mainnet-rpc <url>] \
 *     [--jup-base-url <url>] \
 *     [--dry-run]
 *
 * Defaults:
 *   --slippage      = 50 (bps)
 *   --url           = SOLANA_RPC_URL or https://api.devnet.solana.com
 *   --mainnet-rpc   = https://api.mainnet-beta.solana.com  (for ALT fetches)
 *   --jup-base-url  = https://lite-api.jup.ag/swap/v1      (free tier)
 */

import {
  AddressLookupTableAccount,
  Connection,
  Keypair,
  PublicKey,
  SendTransactionError,
  TransactionInstruction,
  TransactionMessage,
  VersionedTransaction,
} from "@solana/web3.js";
import { getMint } from "@solana/spl-token";
import {
  Configuration,
  type Instruction as JupiterInstruction,
  SwapApi,
} from "@jup-ag/api";
import * as multisig from "@sqds/multisig";
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const NUM_OPERATORS = 5;
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const KEYS_DIR = path.resolve(__dirname, "..", "..", "..", "keys");
const NATIVE_SOL_MINT = "So11111111111111111111111111111111111111112";

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

function requirePubkey(arg: string, label: string): PublicKey {
  try {
    return new PublicKey(arg);
  } catch {
    throw new Error(`Invalid base58 public key for ${label}: "${arg}"`);
  }
}

// ---------------------------------------------------------------------------
// Keypair helpers (mirrors vault-spl-transaction.ts)
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

function explorerTxLink(signature: string, rpcUrl: string): string {
  const cluster = rpcUrl.includes("devnet") ? "?cluster=devnet" : "";
  return `https://explorer.solana.com/tx/${signature}${cluster}`;
}

// ---------------------------------------------------------------------------
// Jupiter -> web3.js conversion
// ---------------------------------------------------------------------------

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
  const results = await Promise.all(
    addresses.map(async (addr) => {
      const resp = await connection.getAddressLookupTable(new PublicKey(addr));
      if (!resp.value) {
        throw new Error(`Address lookup table not found: ${addr}`);
      }
      return resp.value;
    })
  );
  return results;
}

// ---------------------------------------------------------------------------
// Multisig send helper (operator-1 pays all fees; mirrors vault-spl pattern)
// ---------------------------------------------------------------------------

async function sendAndConfirmIx(
  connection: Connection,
  instruction: TransactionInstruction | TransactionInstruction[],
  feePayer: Keypair,
  signers: Keypair[],
  label: string
): Promise<string> {
  const instructions = Array.isArray(instruction) ? instruction : [instruction];
  const latest = await connection.getLatestBlockhash();
  const messageV0 = new TransactionMessage({
    payerKey: feePayer.publicKey,
    recentBlockhash: latest.blockhash,
    instructions,
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
  const rpcUrl =
    getArg("--url") ??
    process.env.SOLANA_RPC_URL ??
    "https://api.devnet.solana.com";
  const mainnetRpc =
    getArg("--mainnet-rpc") ?? "https://api.mainnet-beta.solana.com";
  const jupBasePath =
    getArg("--jup-base-url") ?? "https://lite-api.jup.ag/swap/v1";
  const dryRun = hasFlag("--dry-run");

  const multisigArg = getArg("--multisig");
  if (!multisigArg) {
    throw new Error("Missing --multisig <pda>");
  }
  const multisigPda = requirePubkey(multisigArg, "--multisig");

  const inputMintArg = getArg("--input-mint");
  const outputMintArg = getArg("--output-mint");
  if (!inputMintArg || !outputMintArg) {
    throw new Error("Missing --input-mint and/or --output-mint");
  }
  const inputMint = requirePubkey(inputMintArg, "--input-mint");
  const outputMint = requirePubkey(outputMintArg, "--output-mint");

  const amountUi = parseFloat(getArg("--amount") ?? "0");
  if (!Number.isFinite(amountUi) || amountUi <= 0) {
    throw new Error("--amount must be a positive number of UI tokens");
  }
  const slippageBps = parseInt(getArg("--slippage") ?? "50", 10);

  // Decimals: native SOL is 9; otherwise read from mint on mainnet (devnet
  // won't have the mainnet mint accounts).
  const decimalsConnection = new Connection(mainnetRpc, "confirmed");
  const inputDecimals =
    inputMint.toBase58() === NATIVE_SOL_MINT
      ? 9
      : (await getMint(decimalsConnection, inputMint)).decimals;
  const amountRaw = BigInt(Math.round(amountUi * 10 ** inputDecimals));

  const [vaultPda] = multisig.getVaultPda({ multisigPda, index: 0 });

  console.log(`mode:          ${dryRun ? "DRY-RUN" : "LIVE (devnet)"}`);
  console.log(`devnet RPC:    ${rpcUrl}`);
  console.log(`mainnet RPC:   ${mainnetRpc}    (ALT + mint reads)`);
  console.log(`Jupiter API:   ${jupBasePath}`);
  console.log(`multisig:      ${multisigPda.toBase58()}`);
  console.log(`vault PDA:     ${vaultPda.toBase58()}`);
  console.log(
    `swap:          ${amountUi} (${amountRaw}) ${inputMint.toBase58().slice(0, 8)}… → ${outputMint.toBase58().slice(0, 8)}…  slippage=${slippageBps}bps`
  );

  // -------------------------------------------------------------------------
  // [1] Quote
  // -------------------------------------------------------------------------
  const jup = new SwapApi(new Configuration({ basePath: jupBasePath }));
  const quote = await jup.quoteGet({
    inputMint: inputMint.toBase58(),
    outputMint: outputMint.toBase58(),
    amount: Number(amountRaw),
    slippageBps,
    restrictIntermediateTokens: true,
  });
  console.log(
    `\n[quote]  in=${quote.inAmount}  out=${quote.outAmount}  routePlan hops=${quote.routePlan.length}  priceImpactPct=${quote.priceImpactPct}`
  );

  // -------------------------------------------------------------------------
  // [2] Swap instructions for vault PDA as the user
  // -------------------------------------------------------------------------
  const swapIxResp = await jup.swapInstructionsPost({
    swapRequest: {
      quoteResponse: quote,
      userPublicKey: vaultPda.toBase58(),
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

  console.log(
    `[ixs]    computeBudget=${swapIxResp.computeBudgetInstructions.length}  setup=${swapIxResp.setupInstructions.length}  swap=1  cleanup=${swapIxResp.cleanupInstruction ? 1 : 0}  ALTs=${swapIxResp.addressLookupTableAddresses.length}`
  );

  const lookupTables = await fetchLookupTables(
    decimalsConnection,
    swapIxResp.addressLookupTableAddresses
  );

  if (dryRun) {
    console.log("\n[dry-run] Skipping multisig propose/approve/execute.");
    console.log(
      `[dry-run] Inner v0 message would carry ${innerInstructions.length} ix + ${lookupTables.length} ALTs.`
    );
    return;
  }

  // -------------------------------------------------------------------------
  // [3] Devnet multisig flow — mirrors vault-spl-transaction.ts
  // -------------------------------------------------------------------------
  const connection = new Connection(rpcUrl, "confirmed");
  const operators = loadOperators();
  const creator = operators[0]; // operator-1 pays all fees

  // Inner message anchored to vault PDA as payer (Squads substitutes on execute).
  const { blockhash: innerBlockhash } = await connection.getLatestBlockhash();
  const innerMessage = new TransactionMessage({
    payerKey: vaultPda,
    recentBlockhash: innerBlockhash,
    instructions: innerInstructions,
  });

  const multisigAccount = await multisig.accounts.Multisig.fromAccountAddress(
    connection,
    multisigPda
  );
  const newIndex = BigInt(multisigAccount.transactionIndex.toString()) + 1n;
  console.log(`\n[index]  next transactionIndex = ${newIndex}`);

  console.log(`\n[1/6] vaultTransactionCreate...`);
  const createIx = multisig.instructions.vaultTransactionCreate({
    multisigPda,
    transactionIndex: newIndex,
    creator: creator.publicKey,
    vaultIndex: 0,
    ephemeralSigners: 0,
    transactionMessage: innerMessage,
    addressLookupTableAccounts: lookupTables,
    memo: "quorum day-8 jupiter swap",
  });
  const createSig = await sendAndConfirmIx(
    connection,
    createIx,
    creator,
    [creator],
    "vaultTransactionCreate"
  );
  console.log(`      sig: ${createSig}`);
  console.log(`      ${explorerTxLink(createSig, rpcUrl)}`);

  console.log(`\n[2/6] proposalCreate...`);
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
  console.log(`      sig: ${proposalSig}`);
  console.log(`      ${explorerTxLink(proposalSig, rpcUrl)}`);

  for (let i = 0; i < 3; i++) {
    const member = operators[i];
    const step = i + 3;
    console.log(`\n[${step}/6] proposalApprove (operator-${i + 1})...`);
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
    console.log(`      sig: ${sig}`);
    console.log(`      ${explorerTxLink(sig, rpcUrl)}`);
  }

  console.log(`\n[6/6] vaultTransactionExecute (devnet — expected to fail)...`);
  try {
    const executeBuild = await multisig.instructions.vaultTransactionExecute({
      connection,
      multisigPda,
      transactionIndex: newIndex,
      member: creator.publicKey,
    });
    const executeSig = await sendAndConfirmIx(
      connection,
      executeBuild.instruction,
      creator,
      [creator],
      "vaultTransactionExecute"
    );
    console.log(`      sig: ${executeSig}`);
    console.log(`      ${explorerTxLink(executeSig, rpcUrl)}`);
    console.log(`\n[done] Execute landed on devnet — Jupiter route was reachable.`);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    console.warn(
      `\n[expected] vaultTransactionExecute failed on devnet (Jupiter routes are mainnet-only).`
    );
    console.warn(`           ${msg}`);
    console.log(
      `\nProposal ${newIndex} created + approved 3-of-5. Auditable on Solana Explorer.`
    );
  }
}

main().catch((err) => {
  console.error("\nvault-swap failed:", err);
  process.exit(1);
});
