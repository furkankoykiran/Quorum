#!/usr/bin/env bash
# Boot a local solana-test-validator that clones just enough mainnet state
# (Jupiter v6 program + USDC mint) for `vault-swap.ts` to route and execute
# against. RAM expectation: 2-4 GB. First boot pulls the program + mint over
# the network, so allow ~60 s before the first RPC call.
#
# Usage:
#   bash scripts/localnet-fork.sh           # foreground: boot the validator
#   bash scripts/localnet-fork.sh check     # smoke-check a running validator
#
# Fallback when the fork won't boot (e.g. host RAM constrained, mainnet RPC
# rate-limits the clone): skip the live execute proof and ship Day 10's
# Python dry-run hook only — see /root/.claude/plans/quorum-days-9-10-plan.md
# Risk R5.

set -euo pipefail

# Mainnet program / mint pins. Update only if Jupiter publishes a new program.
JUPITER_V6_PROGRAM="JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"  # Jupiter v6 mainnet program
USDC_MINT="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"            # mainnet USDC mint
MAINNET_RPC="https://api.mainnet-beta.solana.com"
# Non-default ports so we don't fight a co-tenant uvicorn/gossip on 8000.
GOSSIP_PORT="${QUORUM_FORK_GOSSIP_PORT:-18000}"
RPC_PORT="${QUORUM_FORK_RPC_PORT:-18899}"
FAUCET_PORT="${QUORUM_FORK_FAUCET_PORT:-19900}"
FORK_RPC="http://127.0.0.1:${RPC_PORT}"

cmd="${1:-boot}"

case "$cmd" in
  boot)
    echo "[localnet-fork] starting solana-test-validator"
    echo "  cloning Jupiter v6 program: ${JUPITER_V6_PROGRAM}"
    echo "  cloning USDC mint:          ${USDC_MINT}"
    echo "  mainnet upstream:           ${MAINNET_RPC}"
    echo "  fork RPC:                   ${FORK_RPC}"
    echo "  ports:                      gossip=${GOSSIP_PORT} rpc=${RPC_PORT} faucet=${FAUCET_PORT}"
    echo
    exec solana-test-validator \
      --bind-address 127.0.0.1 \
      --gossip-port "${GOSSIP_PORT}" \
      --rpc-port "${RPC_PORT}" \
      --faucet-port "${FAUCET_PORT}" \
      --url "${MAINNET_RPC}" \
      --clone "${JUPITER_V6_PROGRAM}" \
      --clone "${USDC_MINT}" \
      --reset
    ;;
  check)
    echo "[localnet-fork] cluster-version on ${FORK_RPC}"
    solana cluster-version --url "${FORK_RPC}"
    echo
    echo "[localnet-fork] Jupiter v6 program executable check"
    solana account "${JUPITER_V6_PROGRAM}" --url "${FORK_RPC}" --output json \
      | jq '{executable: .account.executable, owner: .account.owner}'
    echo
    echo "[localnet-fork] USDC mint exists check"
    solana account "${USDC_MINT}" --url "${FORK_RPC}" --output json \
      | jq '{lamports: .account.lamports, owner: .account.owner}'
    ;;
  *)
    echo "usage: $0 [boot|check]" >&2
    exit 2
    ;;
esac
