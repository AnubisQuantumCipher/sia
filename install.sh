#!/usr/bin/env bash
# SIA — the Omarchy Brain · installer
# Idempotent. Run from the cloned repo / plugin directory:
#   omarchy plugin add https://github.com/AnubisQuantumCipher/sia
#   cd ~/.config/omarchy/plugins/khephri.sia && ./install.sh
# or: git clone … && cd sia && ./install.sh
#
# What you get: a resident daemon that turns YOUR machine's evidence
# streams into a private, associative, self-consolidating memory —
# fresh keys, empty corpus, your history. Nothing leaves the machine.

set -euo pipefail
REPO="$(cd "$(dirname "$0")" && pwd)"
SHARE="$HOME/.local/share/sia"
STATE="$HOME/.local/state/sia"
BINDIR="$SHARE/bin"
step() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

step "SIA — the Omarchy Brain"
for dep in python3 git curl tar; do
  have "$dep" || { echo "missing dependency: $dep"; exit 1; }
done
ARCH="$(uname -m)"; case "$ARCH" in
  aarch64|arm64) OLLAMA_ARCH=arm64 ;;
  x86_64)        OLLAMA_ARCH=amd64 ;;
  *) echo "unsupported arch: $ARCH"; exit 1 ;;
esac
python3 -c "import cryptography" 2>/dev/null || {
  echo "python-cryptography is required (pacman -S python-cryptography)"; exit 1; }

step "1/9 bun + gbrain (the memory engine, by Garry Tan)"
export PATH="$HOME/.bun/bin:$HOME/.local/bin:$PATH"
have bun || curl -fsSL https://bun.sh/install | bash
export PATH="$HOME/.bun/bin:$PATH"
have gbrain || bun install -g github:garrytan/gbrain
gbrain --version | tail -1

step "2/9 ollama (local embeddings — nothing leaves the machine)"
if ! have ollama && [ ! -x "$HOME/opt/ollama/bin/ollama" ]; then
  mkdir -p "$HOME/opt/ollama" && cd "$HOME/opt/ollama"
  TAG="$(curl -fsSL https://api.github.com/repos/ollama/ollama/releases/latest | python3 -c 'import json,sys;print(json.load(sys.stdin)["tag_name"])')"
  curl -fL -o ollama.tar.zst "https://github.com/ollama/ollama/releases/download/${TAG}/ollama-linux-${OLLAMA_ARCH}.tar.zst"
  tar --zstd -xf ollama.tar.zst && rm ollama.tar.zst
  ln -sf "$HOME/opt/ollama/bin/ollama" "$HOME/.local/bin/ollama"
  cd "$REPO"
fi
mkdir -p "$HOME/.config/systemd/user"
if [ -x "$HOME/opt/ollama/bin/ollama" ]; then
  cp "$REPO/systemd/sia-ollama.service" "$HOME/.config/systemd/user/ollama.service"
  systemctl --user daemon-reload
  systemctl --user enable --now ollama.service
fi
sleep 2
"$HOME/.local/bin/ollama" pull nomic-embed-text 2>/dev/null \
  || ollama pull nomic-embed-text

step "3/9 runtime"
mkdir -p "$BINDIR" "$SHARE/corpus" "$STATE" "$HOME/.config/sia"
cp "$REPO"/bin/sialib.py "$REPO"/bin/siamind.py "$REPO"/bin/siatakes.py \
   "$REPO"/bin/siabench.py "$REPO"/bin/sia-brainstem "$REPO"/bin/sia-ledger \
   "$REPO"/bin/sia-mcp "$BINDIR/"
chmod +x "$BINDIR"/sia-brainstem "$BINDIR"/sia-ledger "$BINDIR"/sia-mcp
install -m 0755 "$REPO/bin/sia" "$HOME/.local/bin/sia"
[ -f "$HOME/.config/sia/config.json" ] || cp "$REPO/config.example.json" "$HOME/.config/sia/config.json"

step "4/9 the corpus (your memory, as files, in git)"
if [ ! -d "$SHARE/corpus/.git" ]; then
  git -C "$SHARE/corpus" init -q
  echo "# SIA corpus — this machine's memory" > "$SHARE/corpus/README.md"
  git -C "$SHARE/corpus" add -A
  git -C "$SHARE/corpus" -c user.email=sia@localhost -c user.name=SIA commit -qm genesis
fi

step "5/9 the brain (gbrain · PGLite · local embeddings)"
export GBRAIN_HOME="$SHARE" GBRAIN_SKIP_STARTUP_HOOKS=1
if [ ! -d "$SHARE/.gbrain/brain.pglite" ]; then
  gbrain init --pglite --embedding-model ollama:nomic-embed-text
fi
gbrain config set self_upgrade.mode off >/dev/null || true
gbrain sources add sia --path "$SHARE/corpus" 2>/dev/null || true
mkdir -p "$SHARE/.gbrain/schema-packs/sia-pack"
cp "$REPO/schema-pack/pack.yaml" "$SHARE/.gbrain/schema-packs/sia-pack/"
gbrain schema validate sia-pack >/dev/null && gbrain schema use sia-pack >/dev/null

step "6/9 your signed run ledger (fresh Ed25519 keys)"
python3 "$BINDIR/sia-ledger" init "$SHARE"

step "7/9 first light — backfilling YOUR machine's history"
systemctl --user stop sia-brainstem 2>/dev/null || true
SIA_BACKFILL=1 "$HOME/.local/bin/sia" pulse || true
cp "$REPO/systemd/sia-brainstem.service" "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable --now sia-brainstem.service
echo "  brainstem: $(systemctl --user is-active sia-brainstem)"

step "8/9 desktop (Omarchy plugin + keybinding)"
PLUGDIR="$HOME/.config/omarchy/plugins/khephri.sia"
if [ "$REPO" != "$PLUGDIR" ] && have omarchy; then
  mkdir -p "$PLUGDIR"
  cp "$REPO"/{manifest.json,Panel.qml,Cockpit.qml,Model.js} "$PLUGDIR/"
  cp -r "$REPO/docs" "$PLUGDIR/" 2>/dev/null || true
fi
if have omarchy; then
  omarchy plugin enable khephri.sia 2>/dev/null || true
  BINDINGS="$HOME/.config/hypr/bindings.lua"
  if [ -f "$BINDINGS" ] && ! grep -q "BEGIN SIA" "$BINDINGS"; then
    cat >> "$BINDINGS" <<'LUA'

-- BEGIN SIA (managed by khephri.sia/install.sh)
hl.unbind("SUPER + SHIFT + B")   -- displaces Browser (still on SUPER+SHIFT+RETURN)
o.bind("SUPER + SHIFT + B", "SIA: brain cockpit", "omarchy-shell shell summon khephri.sia '{}'")
-- END SIA
LUA
    hyprctl reload || true
  fi
else
  echo "  (omarchy shell not found — CLI + MCP still fully functional)"
fi

step "9/9 agents (skill + MCP, wherever you have harnesses)"
mkdir -p "$HOME/.claude/skills/sia"
cp "$REPO/skill/SKILL.md" "$HOME/.claude/skills/sia/"
have claude && claude mcp add --scope user sia -- python3 "$BINDIR/sia-mcp" 2>/dev/null || true
have grok   && grok mcp add sia python3 "$BINDIR/sia-mcp" 2>/dev/null || true
if have codex && ! grep -q "mcp_servers.sia" "$HOME/.codex/config.toml" 2>/dev/null; then
  printf '\n[mcp_servers.sia]\ncommand = "python3"\nargs = ["%s/sia-mcp"]\n' "$BINDIR" >> "$HOME/.codex/config.toml"
fi

step "done — your machine has a brain"
cat <<'EOF'
  cockpit    SUPER+SHIFT+B      (or: omarchy-shell shell summon khephri.sia '{}')
  ask it     sia ask "what happened today"
  thoughts   sia think          status   sia status
  predict    sia take "..." --confidence 0.8 --by YYYY-MM-DD
  configure  ~/.config/sia/config.json   (judge model, custom senses, chains)
  docs       docs/MANUAL.md · docs/WHITEPAPER.md

  It dreams at 03:33: consolidation, musing, grading. Everything stays
  on this machine. The corpus (~/.local/share/sia/corpus) IS the brain —
  back it up and you have everything.
EOF
