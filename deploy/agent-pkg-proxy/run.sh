#!/bin/sh
# The agent network's web proxy (see proxy.py). ALLOW_ALL=1: every public host (owner's choice, 2026-11-21); inside-the-server addresses are always refused.
docker rm -f agent-pkg-proxy >/dev/null 2>&1
docker run -d --name agent-pkg-proxy --restart unless-stopped --memory 192m --cpus 0.5 --pids-limit 256 --read-only --cap-drop ALL \
  --security-opt no-new-privileges -e ALLOW_ALL=1 -v /opt/ai-render/deploy/agent-pkg-proxy/proxy.py:/proxy.py:ro \
  --entrypoint python3 "${IMAGE:-$(docker inspect ai-render-app-1 --format '{{.Config.Image}}')}" /proxy.py
docker network connect --alias pkg-proxy ai-render_pro_net agent-pkg-proxy
