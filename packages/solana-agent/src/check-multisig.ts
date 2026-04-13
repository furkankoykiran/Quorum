/**
 * Read and display the state of a Squads V4 multisig on Solana.
 *
 * Fetches the Multisig account, derives the vault PDA at index 0, and prints
 * members, threshold, transaction index, time lock, and the vault's SOL
 * balance.
 *
 * Usage:
 *   pnpm tsx src/check-multisig.ts --multisig <pda> [--mint <pubkey>] [--url <rpc-url>]
 *
 * --multisig is required. --mint is optional (prints vault ATA balance for
 * that SPL mint). --url defaults to SOLANA_RPC_URL or
 * https://api.devnet.solana.com.
 */

import {
  Connection,
  LAMPORTS_PER_SOL,
  PublicKey,
} from "@solana/web3.js";
import {
  getAssociatedTokenAddressSync,
  getAccount,
  getMint,
  TokenAccountNotFoundError,
  TokenInvalidAccountOwnerError,
} from "@solana/spl-token";
import * as multisig from "@sqds/multisig";

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
        "Usage: pnpm tsx src/check-multisig.ts --multisig <pda> [--url <rpc>]"
    );
  }
  return new PublicKey(pda);
}

// Squads V4 Permissions bitmask: Initiate=1, Vote=2, Execute=4, All=7.
function describePermissions(mask: number): string {
  const parts: string[] = [];
  if (mask & 1) parts.push("propose");
  if (mask & 2) parts.push("vote");
  if (mask & 4) parts.push("execute");
  return parts.length > 0 ? parts.join("+") : "none";
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
  const multisigPda = getMultisigPda();

  console.log(`RPC URL:      ${rpcUrl}`);
  console.log(`Multisig PDA: ${multisigPda.toBase58()}`);

  const connection = new Connection(rpcUrl, "confirmed");

  const multisigAccount = await multisig.accounts.Multisig.fromAccountAddress(
    connection,
    multisigPda
  );

  const [vaultPda] = multisig.getVaultPda({
    multisigPda,
    index: 0,
  });
  const vaultBalance = await connection.getBalance(vaultPda);

  // beet.bignum can be number | BN — .toString() is safe on both and lets us
  // build a BigInt for downstream arithmetic.
  const txIndex = BigInt(multisigAccount.transactionIndex.toString());
  const staleIndex = BigInt(multisigAccount.staleTransactionIndex.toString());

  console.log(`\nThreshold:          ${multisigAccount.threshold}-of-${multisigAccount.members.length}`);
  console.log(`Transaction index:  ${txIndex.toString()}`);
  console.log(`Stale tx index:     ${staleIndex.toString()}`);
  console.log(`Time lock:          ${multisigAccount.timeLock}s`);

  console.log(`\nMembers (${multisigAccount.members.length}):`);
  multisigAccount.members.forEach((member, i) => {
    const mask = member.permissions.mask;
    console.log(
      `  [${i}] ${member.key.toBase58()}  mask=0x${mask.toString(16)} (${describePermissions(mask)})`
    );
  });

  console.log(`\nVault PDA (index 0): ${vaultPda.toBase58()}`);
  console.log(`Vault balance:       ${vaultBalance / LAMPORTS_PER_SOL} SOL (${vaultBalance} lamports)`);

  // Optional: display vault SPL token balance for a given mint
  const mintArg = getArg("--mint");
  if (mintArg) {
    const mintPubkey = new PublicKey(mintArg);
    const vaultAta = getAssociatedTokenAddressSync(mintPubkey, vaultPda, true);
    console.log(`\nVault ATA (mint ${mintPubkey.toBase58()}):`);
    console.log(`  ATA address: ${vaultAta.toBase58()}`);
    try {
      const ataAccount = await getAccount(connection, vaultAta);
      const mintAccount = await getMint(connection, mintPubkey);
      const uiBalance =
        Number(ataAccount.amount) / 10 ** mintAccount.decimals;
      console.log(
        `  Balance:     ${uiBalance.toLocaleString()} tokens (${ataAccount.amount.toString()} raw)`
      );
    } catch (err) {
      if (
        err instanceof TokenAccountNotFoundError ||
        err instanceof TokenInvalidAccountOwnerError
      ) {
        console.log(`  Balance:     ATA not yet created`);
      } else {
        throw err;
      }
    }
  }

  console.log(`\nExplorer:`);
  console.log(`  Multisig: ${explorerLink(multisigPda.toBase58(), rpcUrl)}`);
  console.log(`  Vault:    ${explorerLink(vaultPda.toBase58(), rpcUrl)}`);
}

main().catch((err) => {
  console.error("\nFailed to read multisig:", err);
  process.exit(1);
});
