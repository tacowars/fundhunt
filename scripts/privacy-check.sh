#!/bin/bash
# Public-identity guard (see docs/log/2026-10-08-public-identity-username-only.md).
#
#   bash scripts/privacy-check.sh staged   # pre-commit: added lines + identity
#   bash scripts/privacy-check.sh tree     # every tracked file, before a push
#
# Fails when:
#   - the commit identity is not a GitHub noreply address;
#   - a line adds an email address that is not noreply/example;
#   - a line contains a word listed in .privacy-words (untracked, one word
#     or phrase per line, case-insensitive). The words themselves never
#     enter the repo, so this file can stay public.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

mode=${1:-staged}
fail=0

email_ok='users\.noreply\.github\.com|noreply@github\.com|@example\.(com|org|net)'
email_re='[A-Za-z0-9][A-Za-z0-9._%+-]*@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'

if [ "$mode" = staged ]; then
  for who in GIT_AUTHOR_IDENT GIT_COMMITTER_IDENT; do
    ident=$(git var "$who")
    if ! grep -qE "$email_ok" <<<"$ident"; then
      echo "privacy-check: $who is not a noreply address — run:" >&2
      echo "  git config user.email <id>+<user>@users.noreply.github.com" >&2
      fail=1
    fi
  done
  # added lines only, without the diff's own +++ headers
  content=$(git diff --cached --no-color -U0 --diff-filter=ACMR \
    | grep -E '^\+' | grep -vE '^\+\+\+ ' | sed 's/^+//' || true)
else
  content=$(git ls-files -z | xargs -0 grep -IHn '' 2>/dev/null || true)
fi

emails=$(grep -oE "$email_re" <<<"$content" | grep -vE "$email_ok" | sort -u || true)
if [ -n "$emails" ]; then
  echo "privacy-check: non-noreply email address(es) found:" >&2
  sed 's/^/  /' <<<"$emails" >&2
  fail=1
fi

if [ -f .privacy-words ]; then
  while IFS= read -r word || [ -n "$word" ]; do
    [ -z "$word" ] || [[ $word == \#* ]] && continue
    if grep -qiwF -- "$word" <<<"$content"; then
      # never echo the word: the hook output can end up in public logs
      echo "privacy-check: a word from .privacy-words appears in the ${mode} content, in:" >&2
      if [ "$mode" = staged ]; then
        git diff --cached --name-only -z --diff-filter=ACMR | xargs -0 grep -ilwF -- "$word" 2>/dev/null
      else
        git ls-files -z | xargs -0 grep -ilwF -- "$word" 2>/dev/null
      fi | sed 's/^/  /' >&2
      fail=1
    fi
  done < .privacy-words
fi

exit $fail
