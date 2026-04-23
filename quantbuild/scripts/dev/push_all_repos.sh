#!/usr/bin/env bash
# Push alle ecosysteem-repos in één keer (losse git-remotes).
# Standaard: sibling-mappen onder de ouder van quantbuild.
# Mappen: QuantBuild (quantbuild), QuantBridge (quantbridge), QuantLog (quantlog), QuantOS (quantmetrics_os).
#
# Usage:
#   ./scripts/dev/push_all_repos.sh
#   REMOTE=upstream DRY_RUN=1 ./scripts/dev/push_all_repos.sh
#   QUANT_ECOSYSTEM_ROOT=/srv/src ./scripts/dev/push_all_repos.sh

set -uo pipefail

REMOTE="${REMOTE:-origin}"
DRY_RUN="${DRY_RUN:-0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUANTBUILD_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
if [[ -n "${QUANT_ECOSYSTEM_ROOT:-}" ]]; then
  ECOSYSTEM_ROOT="$QUANT_ECOSYSTEM_ROOT"
else
  ECOSYSTEM_ROOT="$(dirname "$QUANTBUILD_ROOT")"
fi

REPOS=(quantbuild quantbridge quantlog quantmetrics_os)
FAILED=()

echo "Ecosystem root: $ECOSYSTEM_ROOT"
echo "Remote: $REMOTE"
echo

for name in "${REPOS[@]}"; do
  full="${ECOSYSTEM_ROOT}/${name}"
  if [[ ! -d "$full" ]]; then
    echo "WARN: overgeslagen (map ontbreekt): $name -> $full" >&2
    continue
  fi
  if [[ ! -d "$full/.git" ]]; then
    echo "WARN: overgeslagen (geen git-repo): $name" >&2
    continue
  fi

  branch="$(git -C "$full" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  if [[ "$branch" == "HEAD" ]]; then
    echo "WARN: overgeslagen (detached HEAD): $name" >&2
    continue
  fi

  echo "=== $name ($branch) ==="
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "  git -C \"$full\" push $REMOTE"
    continue
  fi

  if ! git -C "$full" push "$REMOTE"; then
    FAILED+=("$name")
  fi
  echo
done

if ((${#FAILED[@]} > 0)); then
  echo "Mislukt voor: ${FAILED[*]}" >&2
  exit 1
fi

echo "Klaar — alle uitgevoerde pushes geslaagd."
exit 0
