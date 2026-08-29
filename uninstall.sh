#!/usr/bin/env bash
# SIA uninstaller — removes daemon, plugin, CLI, and (with --purge) the
# brain itself. Without --purge, your corpus/ledger/keys are kept.
set -uo pipefail
systemctl --user disable --now sia-brainstem 2>/dev/null
command -v omarchy >/dev/null && omarchy plugin disable khephri.sia 2>/dev/null
command -v claude >/dev/null && claude mcp remove sia 2>/dev/null
command -v grok >/dev/null && grok mcp remove sia 2>/dev/null
rm -f ~/.local/bin/sia ~/.config/systemd/user/sia-brainstem.service
rm -rf ~/.claude/skills/sia ~/.config/omarchy/plugins/khephri.sia ~/.local/state/sia
sed -i '/-- BEGIN SIA/,/-- END SIA/d' ~/.config/hypr/bindings.lua 2>/dev/null
if [ "${1:-}" = "--purge" ]; then
  rm -rf ~/.local/share/sia ~/.config/sia
  echo "purged: brain, corpus, ledger, keys are gone."
else
  echo "removed. Your memory survives at ~/.local/share/sia (corpus+ledger+keys)."
  echo "To erase it too: ./uninstall.sh --purge"
fi
echo "note: ollama (~/opt/ollama), bun, and gbrain are left installed."
