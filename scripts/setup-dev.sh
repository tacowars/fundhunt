#!/bin/bash
# One-time setup for people developing fundhunt itself (not needed to *use*
# it): installs the privacy pre-commit hook.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
git config core.hooksPath scripts/hooks
chmod +x scripts/hooks/* scripts/*.sh
[ -f .privacy-words ] || {
  echo "# one word or phrase per line; never committed (see scripts/privacy-check.sh)" > .privacy-words
  echo "created .privacy-words — add the words that must never appear in the repo"
}
echo "pre-commit privacy hook installed"
