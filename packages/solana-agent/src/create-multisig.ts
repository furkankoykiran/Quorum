/**
 * Create a 3-of-5 Squads V4 multisig on Solana devnet.
 *
 * Reads 5 operator keypairs from ../../keys/operator-{1..5}.json,
 * initialises the multisig via multisigCreateV2, and logs the
 * multisig PDA + vault PDA.
 *
 * Usage:
 *   pnpm tsx src/create-multisig.ts [--url <rpc-url>]
 *
 * Defaults to SOLANA_RPC_URL env var or https://api.devnet.solana.com.
 */

import {
  Connection,
  Keypair,
  LAMPORTS_PER_SOL,
} from "@solana/web3.js";
import * as multisig from "@sqds/multisig";
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

const { Permissions } = multisig.types;

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const THRESHOLD = 3;
const NUM_OPERATORS = 5;
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const KEYS_DIR = path.resolve(__dirname, "..", "..", "..", "keys");

function getRpcUrl(): string {
  const urlFlag = process.argv.indexOf("--url");
  if (urlFlag !== -1 && process.argv[urlFlag + 1]) {
    return process.argv[urlFlag + 1];
  }
  return process.env.SOLANA_RPC_URL ?? "https://api.devnet.solana.com";
}

// ---------------------------------------------------------------------------
// Helpers
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
// Main
// ---------------------------------------------------------------------------

async function main() {
  const rpcUrl = getRpcUrl();
  console.log(`RPC URL: ${rpcUrl}`);

  const connection = new Connection(rpcUrl, "confirmed");
  const operators = loadOperators();

  console.log("\nOperator public keys:");
  operators.forEach((op, i) => {
    console.log(`  operator-${i + 1}: ${op.publicKey.toBase58()}`);
  });

  // The creator pays for the transaction and rent
  const creator = operators[0];
  const creatorBalance = await connection.getBalance(creator.publicKey);
  console.log(
    `\nCreator (operator-1) balance: ${creatorBalance / LAMPORTS_PER_SOL} SOL`
  );
  if (creatorBalance < 0.05 * LAMPORTS_PER_SOL) {
    throw new Error(
      "Creator has insufficient SOL (need ≥0.05). Airdrop with: solana airdrop 0.1 <pubkey> --url devnet"
    );
  }

  // Random keypair used to derive the multisig PDA (must be a signer)
  const createKey = Keypair.generate();

  // Derive the multisig PDA
  const [multisigPda] = multisig.getMultisigPda({
    createKey: createKey.publicKey,
  });
  console.log(`\nMultisig PDA: ${multisigPda.toBase58()}`);

  // Derive vault PDA (index 0)
  const [vaultPda] = multisig.getVaultPda({
    multisigPda,
    index: 0,
  });
  console.log(`Vault PDA:    ${vaultPda.toBase58()}`);

  // Fetch program config for the treasury account
  const programConfigPda = multisig.getProgramConfigPda({})[0];
  console.log(`\nProgram Config PDA: ${programConfigPda.toBase58()}`);

  const programConfig =
    await multisig.accounts.ProgramConfig.fromAccountAddress(
      connection,
      programConfigPda
    );
  const configTreasury = programConfig.treasury;
  console.log(`Config Treasury: ${configTreasury.toBase58()}`);

  // Build member list: all 5 operators with full permissions
  const members = operators.map((op) => ({
    key: op.publicKey,
    permissions: Permissions.all(),
  }));

  console.log(`\nCreating ${THRESHOLD}-of-${NUM_OPERATORS} multisig...`);

  const signature = await multisig.rpc.multisigCreateV2({
    connection,
    createKey,
    creator,
    multisigPda,
    configAuthority: null,
    timeLock: 0,
    members,
    threshold: THRESHOLD,
    rentCollector: null,
    treasury: configTreasury,
    sendOptions: { skipPreflight: true },
  });

  await connection.confirmTransaction(signature, "confirmed");

  console.log(`\nMultisig created successfully!`);
  console.log(`  Transaction: ${signature}`);
  console.log(`  Multisig PDA: ${multisigPda.toBase58()}`);
  console.log(`  Vault PDA:    ${vaultPda.toBase58()}`);
  console.log(`  Threshold:    ${THRESHOLD}-of-${NUM_OPERATORS}`);

  // Determine explorer base URL
  const isDevnet =
    rpcUrl.includes("devnet") || rpcUrl.includes("api.devnet");
  const isLocalhost =
    rpcUrl.includes("localhost") || rpcUrl.includes("127.0.0.1");

  let clusterParam = "";
  if (isDevnet) clusterParam = "?cluster=devnet";
  else if (isLocalhost) clusterParam = "?cluster=custom&customUrl=http://localhost:8899";

  console.log(
    `\n  Explorer: https://explorer.solana.com/address/${multisigPda.toBase58()}${clusterParam}`
  );

  // Verify the multisig was created by reading it back
  const multisigAccount = await multisig.accounts.Multisig.fromAccountAddress(
    connection,
    multisigPda
  );
  console.log(`\nVerification:`);
  console.log(`  Members: ${multisigAccount.members.length}`);
  console.log(`  Threshold: ${multisigAccount.threshold}`);
  console.log(`  Transaction index: ${multisigAccount.transactionIndex}`);
}

main().catch((err) => {
  console.error("\nFailed to create multisig:", err);
  process.exit(1);
});
