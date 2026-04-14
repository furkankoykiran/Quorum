/**
 * Run a full Squads V4 vault transaction round-trip on Solana.
 *
 * Moves SOL from the vault PDA (index 0) to a recipient by:
 *   1. vaultTransactionCreate   (wrap a SystemProgram.transfer)
 *   2. proposalCreate           (creator = operator-1)
 *   3. proposalApprove x3       (operators 1..3, meets 3-of-5 threshold)
 *   4. vaultTransactionExecute  (any member can execute once approved)
 * then verifies the recipient balance delta on-chain.
 *
 * Uses @sqds/multisig instruction builders (not the higher-level rpc helpers)
 * so that SendTransactionError logs surface directly — the SDK's rpc wrappers
 * trip over a read-only `logs` getter on Node 24 and swallow the real error.
 *
 * Usage:
 *   pnpm tsx src/vault-transaction.ts --multisig <pda> \
 *     [--recipient <pubkey>] [--amount <sol>] [--url <rpc>]
 *
 * Defaults:
 *   --recipient = operator-2's pubkey
 *   --amount    = 0.01 SOL
 *   --url       = SOLANA_RPC_URL or https://api.devnet.solana.com
 */

import {
  Connection,
  Keypair,
  LAMPORTS_PER_SOL,
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
const DEFAULT_AMOUNT_SOL = 0.01;
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const KEYS_DIR = path.resolve(__dirname, "..", "..", "..", "keys");

// ---------------------------------------------------------------------------
// CLI args
// ---------------------------------------------------------------------------

function getArg(name: string): string | undefined {
  const idx = process.argv.indexOf(name);
  if (idx !== -1 && process.argv[idx + 1]) {
    return process.argv[idx + 1];
  }
  return undefined;
}

function getRpcUrl(): string {
  return (
    getArg("--url") ??
    process.env.SOLANA_RPC_URL ??
    "https://api.devnet.solana.com"
  );
}

function getMultisigPda(): PublicKey {
  const pda = getArg("--multisig");
  if (!pda) {
    throw new Error(
      "Missing required --multisig <pda> argument.\n" +
        "Usage: pnpm tsx src/vault-transaction.ts --multisig <pda> " +
        "[--recipient <pubkey>] [--amount <sol>] [--url <rpc>]"
    );
  }
  try {
    return new PublicKey(pda);
  } catch {
    throw new Error(`Invalid base58 public key for --multisig: "${pda}"`);
  }
}

function getAmountLamports(): number {
  const raw = getArg("--amount");
  const sol = raw ? parseFloat(raw) : DEFAULT_AMOUNT_SOL;
  if (!Number.isFinite(sol) || sol <= 0) {
    throw new Error(`--amount must be a positive number, got: ${raw}`);
  }
  return Math.round(sol * LAMPORTS_PER_SOL);
}

// ---------------------------------------------------------------------------
// Keypair helpers
// ---------------------------------------------------------------------------

function loadKeypair(filePath: string): Keypair {
  const raw = fs.readFileSync(filePath, "utf-8");
  const secretKey = Uint8Array.from(JSON.parse(raw));
  return Keypair.fromSecretKey(secretKey);
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

// ---------------------------------------------------------------------------
// Transaction helpers
// ---------------------------------------------------------------------------

function explorerTxLink(signature: string, rpcUrl: string): string {
  const isDevnet = rpcUrl.includes("devnet");
  const cluster = isDevnet ? "?cluster=devnet" : "";
  return `https://explorer.solana.com/tx/${signature}${cluster}`;
}

/**
 * Build a signed VersionedTransaction carrying a single Squads instruction,
 * send it, and wait for confirmation. Returns the signature.
 *
 * Uses `sendTransaction` + `confirmTransaction` directly so that any
 * `SendTransactionError` bubbles up with its `logs` intact.
 */
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
      console.error(`\n[${label}] send failed:`, err.message);
      try {
        const logs = await err.getLogs(connection);
        console.error("Program logs:");
        for (const line of logs) {
          console.error(`  ${line}`);
        }
      } catch (_err) {
        // ignore — getLogs() can fail if the tx was dropped
      }
    }
    throw err;
  }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  const rpcUrl = getRpcUrl();
  const multisigPda = getMultisigPda();
  const amountLamports = getAmountLamports();

  const connection = new Connection(rpcUrl, "confirmed");
  const operators = loadOperators();
  const creator = operators[0]; // operator-1: proposes + executes

  // Default recipient is operator-2 so the script is runnable with just
  // --multisig. Operator-2 is a known devnet address we can observe for the
  // balance delta.
  const recipientArg = getArg("--recipient");
  const recipient = recipientArg
    ? new PublicKey(recipientArg)
    : operators[1].publicKey;

  console.log(`RPC URL:       ${rpcUrl}`);
  console.log(`Multisig PDA:  ${multisigPda.toBase58()}`);
  console.log(`Recipient:     ${recipient.toBase58()}`);
  console.log(`Amount:        ${amountLamports / LAMPORTS_PER_SOL} SOL (${amountLamports} lamports)`);

  // Fetch the multisig account to compute the next transaction index.
  const multisigAccount = await multisig.accounts.Multisig.fromAccountAddress(
    connection,
    multisigPda
  );
  const currentIndex = BigInt(multisigAccount.transactionIndex.toString());
  const newIndex = currentIndex + 1n;
  console.log(`\nCurrent tx index: ${currentIndex}`);
  console.log(`New tx index:     ${newIndex}`);

  // Derive the vault PDA (index 0) and verify it has funds.
  const [vaultPda] = multisig.getVaultPda({ multisigPda, index: 0 });
  const vaultBalance = await connection.getBalance(vaultPda);
  console.log(`\nVault PDA:     ${vaultPda.toBase58()}`);
  console.log(`Vault balance: ${vaultBalance / LAMPORTS_PER_SOL} SOL`);
  if (vaultBalance < amountLamports) {
    throw new Error(
      `Vault has ${vaultBalance} lamports, needs ${amountLamports}. ` +
        `Fund it with: solana transfer ${vaultPda.toBase58()} <sol> --url devnet`
    );
  }

  // Capture recipient balance BEFORE execution so we can verify the delta.
  const balanceBefore = await connection.getBalance(recipient);
  console.log(`\nRecipient balance before: ${balanceBefore / LAMPORTS_PER_SOL} SOL`);

  // Build the inner transfer instruction. The vault PDA is the funding
  // source; the Squads program substitutes the real fee payer at execution.
  const transferIx = SystemProgram.transfer({
    fromPubkey: vaultPda,
    toPubkey: recipient,
    lamports: amountLamports,
  });
  const { blockhash: innerBlockhash } = await connection.getLatestBlockhash();
  const innerMessage = new TransactionMessage({
    payerKey: vaultPda,
    recentBlockhash: innerBlockhash,
    instructions: [transferIx],
  });

  // -------------------------------------------------------------------------
  // [1/6] vaultTransactionCreate
  // -------------------------------------------------------------------------
  console.log(`\n[1/6] vaultTransactionCreate...`);
  const createIx = multisig.instructions.vaultTransactionCreate({
    multisigPda,
    transactionIndex: newIndex,
    creator: creator.publicKey,
    vaultIndex: 0,
    ephemeralSigners: 0,
    transactionMessage: innerMessage,
    memo: "quorum day-5 vault transaction round-trip",
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

  // -------------------------------------------------------------------------
  // [2/6] proposalCreate
  // -------------------------------------------------------------------------
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

  // -------------------------------------------------------------------------
  // [3..5/6] proposalApprove x3 (operators 1, 2, 3 — meets 3-of-5 threshold)
  //
  // Operator-1 pays all approval fees so operators 2 and 3 don't need their
  // own devnet SOL. Each approve ix names the member whose vote is being
  // cast, and both the payer (operator-1) and the member co-sign the tx.
  // -------------------------------------------------------------------------
  const approveSigs: string[] = [];
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
    const approveSig = await sendAndConfirmIx(
      connection,
      approveIx,
      creator,
      signers,
      `proposalApprove-operator-${i + 1}`
    );
    approveSigs.push(approveSig);
    console.log(`      sig: ${approveSig}`);
    console.log(`      ${explorerTxLink(approveSig, rpcUrl)}`);
  }

  // -------------------------------------------------------------------------
  // [6/6] vaultTransactionExecute
  // -------------------------------------------------------------------------
  console.log(`\n[6/6] vaultTransactionExecute...`);
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

  // -------------------------------------------------------------------------
  // Verification: recipient balance must have increased by amountLamports.
  // -------------------------------------------------------------------------
  const balanceAfter = await connection.getBalance(recipient);
  const delta = balanceAfter - balanceBefore;
  console.log(`\nRecipient balance after: ${balanceAfter / LAMPORTS_PER_SOL} SOL`);
  console.log(`Delta:                   ${delta} lamports`);

  if (delta !== amountLamports) {
    throw new Error(
      `Verification failed: expected +${amountLamports} lamports, got +${delta}`
    );
  }

  console.log(`\nRound-trip complete. Signatures:`);
  console.log(`  create:   ${createSig}`);
  console.log(`  proposal: ${proposalSig}`);
  approveSigs.forEach((sig, i) => {
    console.log(`  approve${i + 1}: ${sig}`);
  });
  console.log(`  execute:  ${executeSig}`);
}

main().catch((err) => {
  console.error("\nVault transaction round-trip failed:", err);
  process.exit(1);
});
