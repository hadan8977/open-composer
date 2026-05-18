#!/usr/bin/env bash
# Open Composer — Local Setup (Linux / macOS)
#
# Usage:
#   ./scripts/setup-local.sh                # full run, ends with dashboard serve in background
#   ./scripts/setup-local.sh --skip-serve   # everything except the serve step
#   ./scripts/setup-local.sh --port 8001    # use a different port
#   ./scripts/setup-local.sh --dry-run      # show what would run, change nothing
#
# Behaviour:
#   - Runs 10 ordered steps, prints [N/10] <title>  <status> for each.
#   - Skips already-done steps (idempotent).
#   - Stops at the first hard failure with an actionable hint.
#   - At the end prints what's still optional (env keys, etc.) and how to fix it.
#
# Sister script: scripts/setup-local.ps1 (Windows).
# Full guide:    docs/setup-local.zh.md

set -uo pipefail

# ---------- options ----------
SKIP_SERVE=0
DRY_RUN=0
PORT=8000

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-serve) SKIP_SERVE=1; shift ;;
    --dry-run)    DRY_RUN=1; shift ;;
    --port)       PORT="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,25p' "$0"
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

# ---------- locate repo root ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# ---------- ansi colors ----------
if [[ -t 1 ]]; then
  C_RESET=$'\033[0m'
  C_CYAN=$'\033[36m'
  C_GREEN=$'\033[32m'
  C_YELLOW=$'\033[33m'
  C_RED=$'\033[31m'
  C_DIM=$'\033[2m'
else
  C_RESET=""; C_CYAN=""; C_GREEN=""; C_YELLOW=""; C_RED=""; C_DIM=""
fi

# ---------- state ----------
TOTAL=10
WARNINGS=()
NEXT_ACTIONS=()
FAILED=0

# ---------- helpers ----------
step()  { printf "%s[%2d/%d]%s %-34s" "$C_CYAN" "$1" "$TOTAL" "$C_RESET" "$2"; }
ok()    { printf "  %sOK%s   %s\n" "$C_GREEN"  "$C_RESET" "$1"; }
warn()  { printf "  %sWARN%s %s\n" "$C_YELLOW" "$C_RESET" "$1"; }
fail()  { printf "  %sFAIL%s %s\n" "$C_RED"    "$C_RESET" "$1"; }
skip()  { printf "  %sSKIP%s %s\n" "$C_DIM"    "$C_RESET" "$1"; }
sub()   { printf "        %s%s%s\n" "$C_DIM" "$1" "$C_RESET"; }

run_cmd() {
  local desc="$1"; shift
  if [[ $DRY_RUN -eq 1 ]]; then
    skip "(dry-run) would: $desc"
    return 0
  fi
  "$@" >/dev/null 2>&1
}

# ---------- Step 1: uv ----------
step 1 "uv toolchain"
if command -v uv >/dev/null 2>&1; then
  uv_v=$(uv --version 2>&1 | awk '{print $2}')
  ok "uv $uv_v"
else
  fail "uv not found in PATH"
  sub "Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
  sub "Then: source \$HOME/.cargo/env  (or restart shell)"
  exit 1
fi

# ---------- Step 2: node + npm ----------
step 2 "node + npm"
if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
  ok "$(node --version) / npm $(npm --version)"
else
  fail "node or npm not found"
  sub "Install: https://nodejs.org/ (LTS) or 'nvm install --lts'"
  exit 1
fi

# ---------- Step 3: Python deps ----------
step 3 "Python deps (.venv)"
if [[ -d .venv && -x .venv/bin/python ]] || [[ -d .venv && -x .venv/Scripts/python.exe ]]; then
  run_cmd "uv sync (idempotent)" uv sync || true
  ok ".venv synced"
else
  sub "First-time install can take 5-10 minutes."
  if [[ $DRY_RUN -eq 1 ]]; then
    skip "(dry-run) would: uv sync"
  else
    uv sync >/dev/null 2>&1
  fi
  if [[ -x .venv/bin/python ]] || [[ $DRY_RUN -eq 1 ]]; then
    ok "installed"
  else
    fail "uv sync failed"
    FAILED=1
  fi
fi

# ---------- Step 4: dashboard node deps ----------
step 4 "Dashboard node deps"
if [[ -d dashboard/node_modules ]]; then
  ok "node_modules present"
else
  sub "First-time install can take 1-2 minutes."
  if [[ $DRY_RUN -eq 1 ]]; then
    skip "(dry-run) would: npm --prefix dashboard install"
  else
    (cd dashboard && npm install >/dev/null 2>&1)
  fi
  if [[ -d dashboard/node_modules ]] || [[ $DRY_RUN -eq 1 ]]; then
    ok "installed"
  else
    fail "npm install failed"
    FAILED=1
  fi
fi

if [[ $FAILED -eq 1 ]]; then
  echo
  echo "${C_YELLOW}Setup stopped at step 3 or 4. Fix dep install and re-run.${C_RESET}"
  exit 1
fi

# ---------- Step 5: repo consistency ----------
step 5 "Repo consistency check"
if [[ $DRY_RUN -eq 1 ]]; then
  skip "(dry-run)"
else
  repo_out=$(uv run oc repo check 2>&1)
  if echo "$repo_out" | grep -q "status=ok ready=yes"; then
    ok "all checks passed"
  else
    warn "blocked / warning - see reports/repo/repo-check.md"
    echo "$repo_out" | grep -i "blocked" | head -3 | while IFS= read -r line; do
      sub "$line"
    done
    WARNINGS+=("repo check has blocked items - see reports/repo/repo-check.md")
    NEXT_ACTIONS+=("Resolve repo blocks: open reports/repo/repo-check.md and follow 'Next action'")
  fi
fi

# ---------- Step 6: .env ----------
step 6 ".env file"
if [[ -f .env ]]; then
  configured=$(grep -E '^[A-Z][A-Z_0-9]+=.+' .env 2>/dev/null | grep -v '=$' | grep -v '=<' | grep -v '=YOUR_' | wc -l | tr -d ' ')
  ok "$configured keys configured"
else
  if [[ -f .env.example ]]; then
    if [[ $DRY_RUN -eq 1 ]]; then
      skip "(dry-run) would: cp .env.example .env"
    else
      cp .env.example .env
    fi
    warn ".env created from example (placeholders only)"
    WARNINGS+=("Edit .env to add real API keys - see docs/setup-local.zh.md section 3")
    NEXT_ACTIONS+=("Configure .env keys: docs/setup-local.zh.md section 3")
  else
    warn "no .env (running with fixtures only)"
  fi
fi

# ---------- Step 7: doctor ----------
step 7 "Doctor (env check)"
if [[ $DRY_RUN -eq 1 ]]; then
  skip "(dry-run)"
else
  doctor_out=$(uv run oc doctor --plain 2>&1)
  missing_count=$(echo "$doctor_out" | awk -F'\t' '$2=="missing"' | wc -l | tr -d ' ')
  ok_count=$(echo "$doctor_out" | awk -F'\t' '$2=="ok"' | wc -l | tr -d ' ')
  if [[ $missing_count -gt 0 ]]; then
    missing_names=$(echo "$doctor_out" | awk -F'\t' '$2=="missing" {print $1}' | tr '\n' ',' | sed 's/,$//')
    warn "$ok_count ok / $missing_count missing (optional: $missing_names)"
    WARNINGS+=("$missing_count optional keys missing - capabilities will use fixtures: $missing_names")
  else
    ok "$ok_count checks ok, no missing"
  fi
fi

# ---------- Step 8: dashboard catalog ----------
step 8 "Dashboard catalog"
if [[ $DRY_RUN -eq 1 ]]; then
  skip "(dry-run)"
else
  uv run oc dashboard catalog >/dev/null 2>&1
  if [[ -f reports/dashboard/catalog.json ]]; then
    s_strat=$(uv run python -c "import json; print(json.load(open('reports/dashboard/catalog.json'))['summary'].get('strategy_count', 0))" 2>/dev/null || echo "?")
    s_ver=$(uv run python -c "import json; print(json.load(open('reports/dashboard/catalog.json'))['summary'].get('version_count', 0))" 2>/dev/null || echo "?")
    s_sig=$(uv run python -c "import json; print(json.load(open('reports/dashboard/catalog.json'))['summary'].get('signal_count', 0))" 2>/dev/null || echo "?")
    ok "${s_strat} strategies / ${s_ver} versions / ${s_sig} signals"
  else
    fail "catalog not generated"
    FAILED=1
  fi
fi

# ---------- Step 9: dashboard frontend ----------
step 9 "Dashboard frontend (Vite)"
if [[ ! -f dashboard/dist/index.html ]] || [[ $DRY_RUN -eq 1 ]]; then
  if [[ $DRY_RUN -eq 1 ]]; then
    skip "(dry-run) would: npm --prefix dashboard run build"
  else
    (cd dashboard && npm run build >/dev/null 2>&1)
  fi
fi
if [[ -f dashboard/dist/index.html ]]; then
  bundle=$(find dashboard/dist/assets -name 'index-*.js' 2>/dev/null | head -1)
  if [[ -n "$bundle" ]]; then
    size_kb=$(( $(stat -c%s "$bundle" 2>/dev/null || stat -f%z "$bundle" 2>/dev/null) / 1024 ))
    ok "built (${size_kb} KB JS)"
  else
    ok "built"
  fi
elif [[ $DRY_RUN -eq 1 ]]; then
  ok "would build"
else
  fail "vite build failed"
  FAILED=1
fi

if [[ $FAILED -eq 1 ]]; then
  echo
  echo "${C_YELLOW}Setup stopped before dashboard serve. Fix above errors and re-run.${C_RESET}"
  exit 1
fi

# ---------- Step 10: dashboard serve ----------
step 10 "Dashboard serve"
if [[ $SKIP_SERVE -eq 1 ]]; then
  skip "skip (--skip-serve)"
  NEXT_ACTIONS+=("Start manually: uv run oc dashboard serve --port $PORT")
elif [[ $DRY_RUN -eq 1 ]]; then
  skip "(dry-run)"
else
  if lsof -i ":$PORT" >/dev/null 2>&1 || ss -tln 2>/dev/null | grep -q ":$PORT "; then
    warn "port $PORT already in use"
    WARNINGS+=("Port $PORT is busy. Stop the other process or pass --port <other>")
  else
    LOG="${TMPDIR:-/tmp}/oc-dashboard.log"
    nohup uv run oc dashboard serve --host 127.0.0.1 --port "$PORT" >"$LOG" 2>&1 &
    pid=$!
    sleep 3
    if curl -sf -o /dev/null --max-time 5 "http://127.0.0.1:$PORT/api/dashboard/health"; then
      ok "ready at http://127.0.0.1:$PORT (PID $pid)"
      NEXT_ACTIONS+=("Open: http://127.0.0.1:$PORT")
      NEXT_ACTIONS+=("Stop server: kill $pid")
    else
      fail "started but /api/dashboard/health did not respond"
      sub "log: $LOG"
      FAILED=1
    fi
  fi
fi

# ---------- Summary ----------
echo
printf "%s%s%s\n" "$C_DIM" "$(printf '%.0s-' {1..70})" "$C_RESET"
if [[ $FAILED -eq 0 ]]; then
  printf "%sOpen Composer is ready locally.%s\n" "$C_GREEN" "$C_RESET"
else
  printf "%sSetup completed with failures - see above.%s\n" "$C_RED" "$C_RESET"
fi

if [[ ${#WARNINGS[@]} -gt 0 ]]; then
  echo
  printf "%sWarnings (non-blocking):%s\n" "$C_YELLOW" "$C_RESET"
  for w in "${WARNINGS[@]}"; do printf "  %s- %s%s\n" "$C_YELLOW" "$w" "$C_RESET"; done
fi

echo
printf "%sNext steps:%s\n" "$C_CYAN" "$C_RESET"
if [[ ${#NEXT_ACTIONS[@]} -gt 0 ]]; then
  for a in "${NEXT_ACTIONS[@]}"; do echo "  - $a"; done
else
  echo "  - Open: http://127.0.0.1:$PORT"
fi
echo "  - Configure env keys:  docs/setup-local.zh.md section 3"
echo "  - Try a strategy:      uv run oc strategy draft --idea \"...\""
echo "  - VPS deployment:      docs/remote-dashboard-deploy.zh.md"
printf "%s%s%s\n" "$C_DIM" "$(printf '%.0s-' {1..70})" "$C_RESET"

exit $FAILED
