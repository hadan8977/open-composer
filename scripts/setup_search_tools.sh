#!/usr/bin/env bash
# Build the search-tools stack that scripts/harvest_search.py runs on.
#
# Everything lives outside the repo and outside the project venv: a browser stack
# must never touch the project's pinned packages (on 2026-09-23 a transitive
# install replaced polars-lts-cpu with an AVX2 build and crashed pytest).
#
#   $OC_SEARCH_HOME/venv    curl_cffi, camoufox + its Firefox build, trafilatura, agent-reach
#   $OC_SEARCH_HOME/sxvenv  SearXNG at a pinned commit, served on 127.0.0.1:8888 only
#   $OC_SEARCH_HOME/cache   page-text cache
#
# Keys stay in /root/.config/open-composer/search.env (mode 600): JEV_API_KEY,
# optionally GITHUB_TOKEN. Re-running is safe; it only fills in what is missing.
set -euo pipefail

HOME_DIR="${OC_SEARCH_HOME:-/opt/oc-search}"
UV="${UV:-/root/.local/bin/uv}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/open-composer-uv-cache}"
SEARXNG_COMMIT="2ed96e6fcfc96ca1045155fc52a12f5f7b070417"
AGENT_REACH_COMMIT="a19a171fa980a0785849596492e0af4db800c82f"

mkdir -p "$HOME_DIR/cache"

# 1. Fetch/read tools.
[ -x "$HOME_DIR/venv/bin/python" ] || "$UV" venv -q "$HOME_DIR/venv" --python 3.12
"$UV" pip install -q --python "$HOME_DIR/venv/bin/python" \
  "curl_cffi==0.16.3" "camoufox==0.5.6" "trafilatura==2.2.0" \
  "agent-reach @ https://github.com/Panniantong/agent-reach/archive/${AGENT_REACH_COMMIT}.zip"
"$HOME_DIR/venv/bin/python" -m camoufox fetch >/dev/null

# 2. SearXNG, local only.
if [ ! -d "$HOME_DIR/searxng/.git" ]; then
  git init -q "$HOME_DIR/searxng"
  git -C "$HOME_DIR/searxng" remote add origin https://github.com/searxng/searxng.git
fi
if [ "$(git -C "$HOME_DIR/searxng" rev-parse HEAD 2>/dev/null)" != "$SEARXNG_COMMIT" ]; then
  git -C "$HOME_DIR/searxng" fetch -q --depth 1 origin "$SEARXNG_COMMIT"
  git -C "$HOME_DIR/searxng" checkout -q FETCH_HEAD
fi
[ -x "$HOME_DIR/sxvenv/bin/python" ] || "$UV" venv -q "$HOME_DIR/sxvenv" --python 3.12
"$UV" pip install -q --python "$HOME_DIR/sxvenv/bin/python" \
  -r "$HOME_DIR/searxng/requirements.txt" msgspec setuptools wheel
"$UV" pip install -q --python "$HOME_DIR/sxvenv/bin/python" --no-build-isolation \
  -e "$HOME_DIR/searxng"

SETTINGS="$HOME_DIR/searxng-settings.yml"
if [ ! -f "$SETTINGS" ]; then
  umask 077
  SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
  # Engines enabled below answered from this server on 2026-09-23 or are worth
  # retrying; duckduckgo, baidu, quark, startpage and mojeek returned captchas.
  cat > "$SETTINGS" <<EOF
use_default_settings: true
general:
  instance_name: "oc-search"
  enable_metrics: false
server:
  bind_address: "127.0.0.1"
  port: 8888
  secret_key: "${SECRET}"
  limiter: false
  public_instance: false
  image_proxy: false
search:
  safe_search: 0
  formats: [html, json]
outgoing:
  request_timeout: 8.0
  max_request_timeout: 20.0
engines:
  - name: bing
    disabled: false
  - name: google
    disabled: false
  - name: 360search
    disabled: false
  - name: sogou wechat
    disabled: false
  - name: brave
    disabled: false
  - name: yahoo
    disabled: false
  - name: github
    disabled: false
  - name: arxiv
    disabled: false
EOF
fi

echo "search tools ready in $HOME_DIR"
echo "check: $HOME_DIR/venv/bin/agent-reach doctor"
echo "run:   $HOME_DIR/venv/bin/python scripts/harvest_search.py run --channel exa --query '...'"
