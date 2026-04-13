/**
 * Run a full Squads V4 SPL token vault transaction round-trip on Solana.
 *
 * Moves SPL tokens from the vault PDA (index 0) to a recipient by:
 *   0. Setup:  create vault ATA + fund it from operator-1 (direct SPL transfers)
 *   1. vaultTransactionCreate   (wrap a Token Program transfer)
 *   2. proposalCreate           (creator = operator-1)
 *   3. proposalApprove x3       (operators 1..3, meets 3-of-5 threshold)
 *   4. vaultTransactionExecute  (any member can execute once approved)
 * then verifies the recipient ATA balance delta on-chain.
 *
 * Uses @sqds/multisig instruction builders (not the higher-level rpc helpers)
 * so that SendTransactionError logs surface directly — the SDK's rpc wrappers
 * trip over a read-only `logs` getter on Node 24 and swallow the real error.
 *
 * Usage:
 *   pnpm tsx src/vault-spl-transaction.ts --multisig <pda> --mint <pubkey> \
 *     [--recipient <pubkey>] [--amount <ui-tokens>] [--url <rpc>]
 *
 * Defaults:
 *   --recipient = operator-2's pubkey
 *   --amount    = 100 tokens (UI amount, multiplied by mint decimals)
 *   --url       = SOLANA_RPC_URL or https://api.devnet.solana.com
 */

import {
  Connection,
  Keypair,
  PublicKey,
  SendTransactionError,
  TransactionInstruction,
  TransactionMessage,
  VersionedTransaction,
} from "@solana/web3.js";
import {
  createAssociatedTokenAccountInstruction,
  createTransferInstruction,
  getAccount,
  getAssociatedTokenAddressSync,
  getMint,
  getOrCreateAssociatedTokenAccount,
  TokenAccountNotFoundError,
  TokenInvalidAccountOwnerError,
} from "@solana/spl-token";
import * as multisig from "@sqds/multisig";
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const NUM_OPERATORS = 5;
const DEFAULT_AMOUNT_UI = 100;
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
        "Usage: pnpm tsx src/vault-spl-transaction.ts --multisig <pda> " +
        "--mint <pubkey> [--recipient <pubkey>] [--amount <tokens>] [--url <rpc>]"
    );
  }
  return new PublicKey(pda);
}

function getMintPubkey(): PublicKey {
  const mint = getArg("--mint");
  if (!mint) {
    throw new Error(
      "Missing required --mint <pubkey> argument.\n" +
        "Usage: pnpm tsx src/vault-spl-transaction.ts --multisig <pda> " +
        "--mint <pubkey> [--recipient <pubkey>] [--amount <tokens>] [--url <rpc>]"
    );
  }
  return new PublicKey(mint);
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
 * Build a signed VersionedTransaction carrying one or more instructions,
 * send it, and wait for confirmation. Returns the signature.
 */
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
      console.error(`\n[${label}] send failed:`, err.message);
      try {
        const logs = await err.getLogs(connection);
        console.error("Program logs:");
        for (const line of logs) {
          console.error(`  ${line}`);
        }
      } catch {
        // ignore
      }
    }
    throw err;
  }
}

/**
 * Check whether an ATA exists on-chain. Returns true if the account is valid.
 */
async function ataExists(
  connection: Connection,
  ata: PublicKey
): Promise<boolean> {
  try {
    await getAccount(connection, ata);
    return true;
  } catch (err) {
    if (
      err instanceof TokenAccountNotFoundError ||
      err instanceof TokenInvalidAccountOwnerError
    ) {
      return false;
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
  const mintPubkey = getMintPubkey();

  const connection = new Connection(rpcUrl, "confirmed");
  const operators = loadOperators();
  const creator = operators[0]; // operator-1: proposes + executes + pays all fees

  // Default recipient is operator-2
  const recipientArg = getArg("--recipient");
  const recipient = recipientArg
    ? new PublicKey(recipientArg)
    : operators[1].publicKey;

  // Read mint account to get decimals
  const mintAccount = await getMint(connection, mintPubkey);
  const decimals = mintAccount.decimals;

  // Parse UI amount and compute raw
  const amountUiRaw = getArg("--amount");
  const amountUi = amountUiRaw ? parseFloat(amountUiRaw) : DEFAULT_AMOUNT_UI;
  if (!Number.isFinite(amountUi) || amountUi <= 0) {
    throw new Error(`--amount must be a positive number, got: ${amountUiRaw}`);
  }
  const amountRaw = BigInt(Math.round(amountUi * 10 ** decimals));

  console.log(`RPC URL:       ${rpcUrl}`);
  console.log(`Multisig PDA:  ${multisigPda.toBase58()}`);
  console.log(`Mint:          ${mintPubkey.toBase58()} (${decimals} decimals)`);
  console.log(`Recipient:     ${recipient.toBase58()}`);
  console.log(`Amount:        ${amountUi} tokens (${amountRaw.toString()} raw)`);

  // Derive the vault PDA (index 0)
  const [vaultPda] = multisig.getVaultPda({ multisigPda, index: 0 });
  console.log(`\nVault PDA:     ${vaultPda.toBase58()}`);

  // Derive ATAs
  const vaultAta = getAssociatedTokenAddressSync(mintPubkey, vaultPda, true);
  const recipientAta = getAssociatedTokenAddressSync(
    mintPubkey,
    recipient,
    false
  );

  console.log(`Vault ATA:     ${vaultAta.toBase58()}`);
  console.log(`Recipient ATA: ${recipientAta.toBase58()}`);

  // -------------------------------------------------------------------------
  // [Setup A] Create vault ATA if it doesn't exist
  // -------------------------------------------------------------------------
  if (!(await ataExists(connection, vaultAta))) {
    console.log(`\n[Setup A] Creating vault ATA (operator-1 pays rent)...`);
    const createAtaIx = createAssociatedTokenAccountInstruction(
      creator.publicKey, // payer
      vaultAta,
      vaultPda, // owner (PDA)
      mintPubkey
    );
    const sig = await sendAndConfirmIx(
      connection,
      createAtaIx,
      creator,
      [creator],
      "createVaultATA"
    );
    console.log(`      sig: ${sig}`);
    console.log(`      ${explorerTxLink(sig, rpcUrl)}`);
  } else {
    console.log(`\n[Setup A] Vault ATA already exists, skipping creation.`);
  }

  // -------------------------------------------------------------------------
  // [Setup B] Fund vault ATA from operator-1 (direct SPL transfer, not multisig)
  // -------------------------------------------------------------------------
  console.log(`\n[Setup B] Funding vault ATA with ${amountUi} tokens from operator-1...`);
  const operator1Ata = await getOrCreateAssociatedTokenAccount(
    connection,
    creator, // payer
    mintPubkey,
    creator.publicKey // owner
  );

  const operator1Balance = operator1Ata.amount;
  if (operator1Balance < amountRaw) {
    throw new Error(
      `Operator-1 ATA has ${operator1Balance.toString()} raw tokens, ` +
        `needs ${amountRaw.toString()}. Mint more tokens first.`
    );
  }

  const fundIx = createTransferInstruction(
    operator1Ata.address, // source
    vaultAta, // destination
    creator.publicKey, // authority (operator-1 owns the source)
    amountRaw
  );
  const fundSig = await sendAndConfirmIx(
    connection,
    fundIx,
    creator,
    [creator],
    "fundVaultATA"
  );
  console.log(`      sig: ${fundSig}`);
  console.log(`      ${explorerTxLink(fundSig, rpcUrl)}`);

  // -------------------------------------------------------------------------
  // [Setup C] Create recipient ATA if it doesn't exist
  // -------------------------------------------------------------------------
  if (!(await ataExists(connection, recipientAta))) {
    console.log(`\n[Setup C] Creating recipient ATA (operator-1 pays rent)...`);
    const createRecipientAtaIx = createAssociatedTokenAccountInstruction(
      creator.publicKey, // payer
      recipientAta,
      recipient, // owner
      mintPubkey
    );
    const sig = await sendAndConfirmIx(
      connection,
      createRecipientAtaIx,
      creator,
      [creator],
      "createRecipientATA"
    );
    console.log(`      sig: ${sig}`);
    console.log(`      ${explorerTxLink(sig, rpcUrl)}`);
  } else {
    console.log(`\n[Setup C] Recipient ATA already exists, skipping creation.`);
  }

  // Capture recipient balance BEFORE execution
  let recipientBalanceBefore = 0n;
  try {
    const acct = await getAccount(connection, recipientAta);
    recipientBalanceBefore = acct.amount;
  } catch {
    // ATA might have just been created — balance is 0
  }
  console.log(`\nRecipient balance before: ${recipientBalanceBefore.toString()} raw`);

  // -------------------------------------------------------------------------
  // Build the inner SPL transfer instruction for the vault transaction.
  // The vault PDA is the authority — Squads signs as the vault on execute.
  // -------------------------------------------------------------------------
  const innerTransferIx = createTransferInstruction(
    vaultAta, // source
    recipientAta, // destination
    vaultPda, // authority (Squads program substitutes the vault PDA)
    amountRaw
  );
  const { blockhash: innerBlockhash } = await connection.getLatestBlockhash();
  const innerMessage = new TransactionMessage({
    payerKey: vaultPda,
    recentBlockhash: innerBlockhash,
    instructions: [innerTransferIx],
  });

  // Fetch the multisig account to compute the next transaction index
  const multisigAccount = await multisig.accounts.Multisig.fromAccountAddress(
    connection,
    multisigPda
  );
  const currentIndex = BigInt(multisigAccount.transactionIndex.toString());
  const newIndex = currentIndex + 1n;
  console.log(`\nCurrent tx index: ${currentIndex}`);
  console.log(`New tx index:     ${newIndex}`);

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
    memo: "quorum day-6 SPL vault transaction round-trip",
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
  // own devnet SOL.
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
  // Verification: recipient ATA balance must have increased by amountRaw.
  // -------------------------------------------------------------------------
  const recipientAcctAfter = await getAccount(connection, recipientAta);
  const recipientBalanceAfter = recipientAcctAfter.amount;
  const delta = recipientBalanceAfter - recipientBalanceBefore;
  const deltaUi = Number(delta) / 10 ** decimals;

  console.log(`\nRecipient balance after: ${recipientBalanceAfter.toString()} raw`);
  console.log(`Delta:                  ${delta.toString()} raw (${deltaUi} tokens)`);

  if (delta !== amountRaw) {
    throw new Error(
      `Verification failed: expected +${amountRaw.toString()} raw, got +${delta.toString()}`
    );
  }

  console.log(`\nSPL round-trip complete. Signatures:`);
  console.log(`  fund vault: ${fundSig}`);
  console.log(`  create:     ${createSig}`);
  console.log(`  proposal:   ${proposalSig}`);
  approveSigs.forEach((sig, i) => {
    console.log(`  approve${i + 1}:   ${sig}`);
  });
  console.log(`  execute:    ${executeSig}`);
}

main().catch((err) => {
  console.error("\nSPL vault transaction round-trip failed:", err);
  process.exit(1);
});
