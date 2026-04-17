#!/usr/bin/env bash
# Run vault-swap.ts against the localnet fork and capture a structured JSON
# evidence file under data/fork-swap-evidence-<ts>.json. The evidence file is
# what Day 11 uses as proof that the Squads vault-transaction lifecycle works
# end-to-end against a mainnet-forked validator.
#
# Flow:
#   1. Read the fork multisig PDA from keys/fork-multisig.txt (written by
#      fork-bootstrap.sh).
#   2. Capture vault SOL + USDC balances before the swap.
#   3. Invoke vault-swap.ts with SOL -> USDC (0.1 SOL default).
#   4. Capture vault SOL + USDC balances after.
#   5. Parse the per-step signatures out of vault-swap.ts stdout:
#        - vaultTransactionCreate
#        - proposalCreate
#        - proposalApprove x3
#        - vaultTransactionExecute (may fail — fork lacks Jupiter AMM accounts,
#          so this is captured as execute_ok=false with the failure reason,
#          not a hard error).
#   6. Write data/fork-swap-evidence-<ts>.json.
#
# Preconditions:
#   - Fork running (bash packages/solana-agent/scripts/localnet-fork.sh boot).
#   - Fork bootstrapped (bash packages/solana-agent/scripts/fork-bootstrap.sh).
#   - Vault must hold at least --amount SOL; top it up with
#     `solana transfer <vault> <amount> --from keys/operator-1.json --url ...`.
#
# Usage:
#   bash packages/solana-agent/scripts/fork-swap-evidence.sh [AMOUNT_SOL]
#
# Environment overrides:
#   QUORUM_FORK_RPC_URL  (default http://127.0.0.1:18899)
#   QUORUM_MAINNET_RPC   (default https://api.mainnet-beta.solana.com)

set -euo pipefail

FORK_RPC="${QUORUM_FORK_RPC_URL:-http://127.0.0.1:18899}"
MAINNET_RPC="${QUORUM_MAINNET_RPC:-https://api.mainnet-beta.solana.com}"
AMOUNT_SOL="${1:-0.1}"
SLIPPAGE_BPS="${QUORUM_FORK_SLIPPAGE_BPS:-50}"
SOL_MINT="So11111111111111111111111111111111111111112"
USDC_MINT="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../../.." &>/dev/null && pwd)"
KEYS_DIR="${REPO_ROOT}/keys"
DATA_DIR="${REPO_ROOT}/data"
AGENT_DIR="${REPO_ROOT}/packages/solana-agent"
MULTISIG_FILE="${KEYS_DIR}/fork-multisig.txt"

if [ ! -f "${MULTISIG_FILE}" ]; then
  echo "[fork-swap-evidence] missing ${MULTISIG_FILE}" >&2
  echo "                     run: bash packages/solana-agent/scripts/fork-bootstrap.sh" >&2
  exit 1
fi

MULTISIG_PDA="$(tr -d '[:space:]' < "${MULTISIG_FILE}")"
if [ -z "${MULTISIG_PDA}" ]; then
  echo "[fork-swap-evidence] ${MULTISIG_FILE} is empty" >&2
  exit 1
fi

mkdir -p "${DATA_DIR}"

# Resolve vault PDA (index 0) via check-multisig.ts so we do not have to
# reimplement Squads PDA derivation in shell.
VAULT_PDA="$(
  cd "${AGENT_DIR}" \
    && pnpm tsx src/check-multisig.ts --multisig "${MULTISIG_PDA}" --url "${FORK_RPC}" 2>/dev/null \
    | awk '/^Vault PDA \(index 0\):/ {print $NF; exit}'
)"
if [ -z "${VAULT_PDA}" ]; then
  echo "[fork-swap-evidence] could not derive vault PDA" >&2
  exit 1
fi

ts_now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# Returns vault SOL balance in lamports (integer) via solana balance --lamports.
vault_sol_lamports() {
  solana balance "${VAULT_PDA}" --url "${FORK_RPC}" --lamports 2>/dev/null \
    | awk '{print $1; exit}'
}

# Returns vault USDC balance (raw) via spl-token. Prints "0" if the ATA has
# not been created yet — the swap setup creates it.
vault_usdc_raw() {
  local ata
  ata="$(spl-token address --token "${USDC_MINT}" --owner "${VAULT_PDA}" \
    --verbose --url "${FORK_RPC}" 2>/dev/null \
    | awk '/Associated token address/ {print $NF; exit}')"
  if [ -z "${ata}" ]; then
    echo "0"
    return
  fi
  local raw
  raw="$(solana account "${ata}" --url "${FORK_RPC}" --output json 2>/dev/null \
    | jq -r '.account.data.parsed.info.tokenAmount.amount // "0"' 2>/dev/null \
    || true)"
  if [ -z "${raw}" ] || [ "${raw}" = "null" ]; then
    echo "0"
  else
    echo "${raw}"
  fi
}

OPERATOR_1_PUBKEY="$(solana-keygen pubkey "${KEYS_DIR}/operator-1.json")"
op1_sol_lamports() {
  solana balance "${OPERATOR_1_PUBKEY}" --url "${FORK_RPC}" --lamports 2>/dev/null \
    | awk '{print $1; exit}'
}

echo "[fork-swap-evidence] multisig:        ${MULTISIG_PDA}"
echo "[fork-swap-evidence] vault:           ${VAULT_PDA}"
echo "[fork-swap-evidence] amount:          ${AMOUNT_SOL} SOL"
echo "[fork-swap-evidence] fork RPC:        ${FORK_RPC}"
echo "[fork-swap-evidence] mainnet RPC:     ${MAINNET_RPC}"

VAULT_SOL_BEFORE="$(vault_sol_lamports)"
VAULT_USDC_BEFORE="$(vault_usdc_raw)"
OP1_SOL_BEFORE="$(op1_sol_lamports)"
TS_START="$(ts_now)"

# Capture vault-swap.ts output to a scratch log; we parse it below.
LOG_PATH="$(mktemp)"
SWAP_EXIT=0
(
  cd "${AGENT_DIR}"
  pnpm tsx src/vault-swap.ts \
    --multisig "${MULTISIG_PDA}" \
    --input-mint "${SOL_MINT}" \
    --output-mint "${USDC_MINT}" \
    --amount "${AMOUNT_SOL}" \
    --slippage "${SLIPPAGE_BPS}" \
    --url "${FORK_RPC}" \
    --mainnet-rpc "${MAINNET_RPC}"
) > "${LOG_PATH}" 2>&1 || SWAP_EXIT=$?

TS_END="$(ts_now)"
VAULT_SOL_AFTER="$(vault_sol_lamports)"
VAULT_USDC_AFTER="$(vault_usdc_raw)"
OP1_SOL_AFTER="$(op1_sol_lamports)"

cat "${LOG_PATH}"
echo "[fork-swap-evidence] vault-swap.ts exit: ${SWAP_EXIT}"

# Extract per-step signatures by matching lines like "      sig: <base58>".
# Relies on vault-swap.ts stable stdout format. There should be 5 sig lines
# on success (create, proposalCreate, approve x3) and 6 on full success
# (plus execute). If the execute step fails, vault-swap.ts catches and logs
# without emitting a sig for the execute step.
mapfile -t SIGS < <(grep -E '^ {6}sig: ' "${LOG_PATH}" | awk '{print $2}')

# Jupiter quote outAmount (raw USDC units).
QUOTE_OUT="$(grep -Eo 'out=[0-9]+' "${LOG_PATH}" | head -n1 | cut -d= -f2 || true)"
QUOTE_OUT="${QUOTE_OUT:-0}"

# Execute failure reason if we see the "[expected]" catch block.
EXECUTE_OK="true"
EXECUTE_ERR=""
if [ "${#SIGS[@]}" -lt 6 ]; then
  EXECUTE_OK="false"
  EXECUTE_ERR="$(grep -E '^ +[A-Z][a-z]' "${LOG_PATH}" \
    | grep -iE 'not found|failed|error' \
    | head -n1 \
    | sed 's/^[[:space:]]*//' || true)"
fi

# Safely pick elements from SIGS — missing indices become empty strings so
# the JSON emit below never fails.
get_sig() {
  local i="$1"
  if [ "${i}" -lt "${#SIGS[@]}" ]; then
    printf '%s' "${SIGS[$i]}"
  fi
}

OUT_PATH="${DATA_DIR}/fork-swap-evidence-$(date -u +%Y%m%dT%H%M%SZ).json"

jq -n \
  --arg ts_start "${TS_START}" \
  --arg ts_end "${TS_END}" \
  --arg fork_rpc "${FORK_RPC}" \
  --arg mainnet_rpc "${MAINNET_RPC}" \
  --arg multisig "${MULTISIG_PDA}" \
  --arg vault "${VAULT_PDA}" \
  --arg operator_1 "${OPERATOR_1_PUBKEY}" \
  --arg amount_sol "${AMOUNT_SOL}" \
  --arg slippage "${SLIPPAGE_BPS}" \
  --arg sol_before "${VAULT_SOL_BEFORE}" \
  --arg sol_after "${VAULT_SOL_AFTER}" \
  --arg usdc_before "${VAULT_USDC_BEFORE}" \
  --arg usdc_after "${VAULT_USDC_AFTER}" \
  --arg op1_before "${OP1_SOL_BEFORE}" \
  --arg op1_after "${OP1_SOL_AFTER}" \
  --arg quote_out "${QUOTE_OUT}" \
  --arg create_sig "$(get_sig 0)" \
  --arg proposal_sig "$(get_sig 1)" \
  --arg approve1_sig "$(get_sig 2)" \
  --arg approve2_sig "$(get_sig 3)" \
  --arg approve3_sig "$(get_sig 4)" \
  --arg execute_sig "$(get_sig 5)" \
  --arg execute_ok "${EXECUTE_OK}" \
  --arg execute_err "${EXECUTE_ERR}" \
  --arg swap_exit "${SWAP_EXIT}" \
  '{
    ts_start: $ts_start,
    ts_end: $ts_end,
    fork_rpc: $fork_rpc,
    mainnet_rpc: $mainnet_rpc,
    multisig_pda: $multisig,
    vault_pda: $vault,
    operator_1: $operator_1,
    amount_sol: ($amount_sol | tonumber),
    slippage_bps: ($slippage | tonumber),
    jupiter_quote_out_raw: $quote_out,
    vault_before: {
      sol_lamports: ($sol_before | tonumber),
      usdc_raw: $usdc_before
    },
    vault_after: {
      sol_lamports: ($sol_after | tonumber),
      usdc_raw: $usdc_after
    },
    operator_1_fees: {
      sol_lamports_before: ($op1_before | tonumber),
      sol_lamports_after: ($op1_after | tonumber),
      sol_lamports_spent: (($op1_before | tonumber) - ($op1_after | tonumber))
    },
    signatures: {
      vault_transaction_create: $create_sig,
      proposal_create: $proposal_sig,
      proposal_approve_1: $approve1_sig,
      proposal_approve_2: $approve2_sig,
      proposal_approve_3: $approve3_sig,
      vault_transaction_execute: $execute_sig
    },
    execute: {
      ok: ($execute_ok == "true"),
      error: $execute_err
    },
    vault_swap_exit: ($swap_exit | tonumber)
  }' > "${OUT_PATH}"

rm -f "${LOG_PATH}"

echo
echo "[fork-swap-evidence] wrote ${OUT_PATH}"
jq '{
  multisig_pda,
  vault_pda,
  amount_sol,
  jupiter_quote_out_raw,
  signatures,
  execute,
  vault_after
}' "${OUT_PATH}"
