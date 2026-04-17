#!/usr/bin/env bash
# Bootstrap the localnet fork for Milestone 3 close:
#   - Airdrop each of the 5 operator keypairs so any of them can pay fees
#     (the devnet operator-1-pays-everything pattern is unnecessary on the
#     fork; direct airdrops are simpler).
#   - Create a fresh 3-of-5 Squads V4 multisig on the fork and capture the
#     resulting multisig PDA into keys/fork-multisig.txt (gitignored).
#
# Preconditions:
#   - `solana-test-validator` already running on 127.0.0.1:18899 (see
#     localnet-fork.sh). This script does not boot it.
#   - Operator keypairs 1..5 exist at <repo>/keys/operator-{1..5}.json.
#
# Usage:
#   bash packages/solana-agent/scripts/fork-bootstrap.sh

set -euo pipefail

FORK_RPC="${QUORUM_FORK_RPC_URL:-http://127.0.0.1:18899}"
AIRDROP_SOL="${QUORUM_FORK_AIRDROP_SOL:-100}"
NUM_OPERATORS=5

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../../.." &>/dev/null && pwd)"
KEYS_DIR="${REPO_ROOT}/keys"
OUT_FILE="${KEYS_DIR}/fork-multisig.txt"
AGENT_DIR="${REPO_ROOT}/packages/solana-agent"

echo "[fork-bootstrap] RPC:        ${FORK_RPC}"
echo "[fork-bootstrap] keys dir:   ${KEYS_DIR}"
echo "[fork-bootstrap] airdrop:    ${AIRDROP_SOL} SOL per operator"
echo

if ! solana cluster-version --url "${FORK_RPC}" >/dev/null 2>&1; then
  echo "[fork-bootstrap] fork RPC not reachable at ${FORK_RPC}" >&2
  echo "                 run: bash packages/solana-agent/scripts/localnet-fork.sh boot" >&2
  exit 1
fi

for i in $(seq 1 "${NUM_OPERATORS}"); do
  key_path="${KEYS_DIR}/operator-${i}.json"
  if [ ! -f "${key_path}" ]; then
    echo "[fork-bootstrap] missing keypair: ${key_path}" >&2
    exit 1
  fi
  pubkey="$(solana-keygen pubkey "${key_path}")"
  echo "[airdrop] operator-${i}  ${pubkey}"
  solana airdrop "${AIRDROP_SOL}" "${pubkey}" --url "${FORK_RPC}" >/dev/null
  balance="$(solana balance "${pubkey}" --url "${FORK_RPC}")"
  echo "          balance=${balance}"
done

echo
echo "[fork-bootstrap] creating fresh multisig on fork"
# create-multisig.ts accepts --url and prints "Multisig PDA: <base58>".
create_log="$(cd "${AGENT_DIR}" && pnpm tsx src/create-multisig.ts --url "${FORK_RPC}" 2>&1)"
echo "${create_log}"

# Extract the final Verification "Members" section's sibling PDA. The script
# prints "Multisig PDA: <pda>" both at derivation time and in the "created
# successfully" block — grab the first occurrence.
pda="$(printf '%s\n' "${create_log}" | awk '/^Multisig PDA:/ {print $3; exit}')"
if [ -z "${pda}" ]; then
  echo "[fork-bootstrap] failed to parse multisig PDA from create-multisig.ts output" >&2
  exit 1
fi

mkdir -p "${KEYS_DIR}"
printf '%s\n' "${pda}" > "${OUT_FILE}"
echo
echo "[fork-bootstrap] fork multisig PDA: ${pda}"
echo "                 written to:        ${OUT_FILE}"
