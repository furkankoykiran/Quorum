/**
 * Bootstrap a mock-USDC SPL token mint on Solana devnet.
 *
 * Creates a new SPL mint with 6 decimals (matching real USDC), then mints
 * 1,000,000 tokens to operator-1's associated token account. Operator-1 is
 * both the mint authority and the fee payer.
 *
 * Usage:
 *   pnpm tsx src/create-mint.ts [--url <rpc-url>]
 *
 * Defaults to SOLANA_RPC_URL env var or https://api.devnet.solana.com.
 */

import {
  Connection,
  Keypair,
  LAMPORTS_PER_SOL,
} from "@solana/web3.js";
import {
  createMint,
  getOrCreateAssociatedTokenAccount,
  mintTo,
} from "@solana/spl-token";
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const DECIMALS = 6; // same as real USDC
const MINT_SUPPLY_UI = 1_000_000; // 1M tokens
const MINT_SUPPLY_RAW = BigInt(MINT_SUPPLY_UI) * BigInt(10 ** DECIMALS);

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

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function loadKeypair(filePath: string): Keypair {
  const raw = fs.readFileSync(filePath, "utf-8");
  const secretKey = Uint8Array.from(JSON.parse(raw));
  return Keypair.fromSecretKey(secretKey);
}

function explorerLink(address: string, rpcUrl: string): string {
  const isDevnet = rpcUrl.includes("devnet");
  const cluster = isDevnet ? "?cluster=devnet" : "";
  return `https://explorer.solana.com/address/${address}${cluster}`;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  const rpcUrl = getRpcUrl();
  console.log(`RPC URL: ${rpcUrl}`);

  const connection = new Connection(rpcUrl, "confirmed");

  const keyPath = path.join(KEYS_DIR, "operator-1.json");
  if (!fs.existsSync(keyPath)) {
    throw new Error(`Missing keypair: ${keyPath}`);
  }
  const operator1 = loadKeypair(keyPath);
  console.log(`Operator-1: ${operator1.publicKey.toBase58()}`);

  const balance = await connection.getBalance(operator1.publicKey);
  console.log(`Balance:    ${balance / LAMPORTS_PER_SOL} SOL`);
  if (balance < 0.05 * LAMPORTS_PER_SOL) {
    throw new Error(
      "Operator-1 has insufficient SOL. Airdrop at least 0.1 SOL first."
    );
  }

  // Create the SPL mint (operator-1 is mint authority, no freeze authority)
  console.log(`\nCreating SPL mint (${DECIMALS} decimals)...`);
  const mint = await createMint(
    connection,
    operator1, // payer
    operator1.publicKey, // mint authority
    null, // freeze authority (none)
    DECIMALS
  );
  console.log(`Mint:       ${mint.toBase58()}`);
  console.log(`Explorer:   ${explorerLink(mint.toBase58(), rpcUrl)}`);

  // Create operator-1's ATA and mint initial supply
  console.log(`\nCreating operator-1 ATA + minting ${MINT_SUPPLY_UI.toLocaleString()} tokens...`);
  const ata = await getOrCreateAssociatedTokenAccount(
    connection,
    operator1, // payer
    mint,
    operator1.publicKey // owner
  );
  console.log(`ATA:        ${ata.address.toBase58()}`);

  await mintTo(
    connection,
    operator1, // payer
    mint,
    ata.address,
    operator1, // mint authority
    MINT_SUPPLY_RAW
  );

  // Verify
  const updatedAta = await getOrCreateAssociatedTokenAccount(
    connection,
    operator1,
    mint,
    operator1.publicKey
  );
  const uiBalance = Number(updatedAta.amount) / 10 ** DECIMALS;

  console.log(`\nMint created successfully!`);
  console.log(`  Mint pubkey:     ${mint.toBase58()}`);
  console.log(`  Decimals:        ${DECIMALS}`);
  console.log(`  Operator-1 ATA:  ${ata.address.toBase58()}`);
  console.log(`  ATA balance:     ${uiBalance.toLocaleString()} tokens`);
  console.log(`  Explorer:        ${explorerLink(mint.toBase58(), rpcUrl)}`);
}

main().catch((err) => {
  console.error("\nFailed to create mint:", err);
  process.exit(1);
});
