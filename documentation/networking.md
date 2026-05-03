# Networking & Tunnels

Configuration for LAN access, ngrok tunnels, HTTPS dev mode, and firewall rules — primarily for phone pairing on campus or restricted networks.

## Relevant Files

| File | Role |
|------|------|
| `start-dev.ps1` | Main dev launcher with `-DevHttps` flag |
| `start-dev-ngrok.ps1` | Dev launcher with ngrok tunnel support |
| `scripts/allow-dev-ports-firewall.ps1` | Open firewall ports 5000 + 5173 |
| `scripts/diagnose-dev-lan.ps1` | Diagnose LAN connectivity issues |
| `frontend/vite.config.ts` | Proxy rules and allowed tunnel hosts |
| `frontend/src/api/ngrokAgentTunnels.ts` | Auto-detect ngrok tunnel URL |
| `frontend/src/api/tunnelFetchInit.ts` | Bypass ngrok browser warning headers |
| `frontend/src/env/pairing.ts` | `VITE_PAIRING_ORIGIN` override |
| `frontend/.env.example` | Example env config for tunnels |
| `backend/programAPI.py` | `/host-info` endpoint (LAN IP detection) |

## LAN IP Detection

`/host-info` returns the laptop's LAN IPv4 addresses, used to construct phone-accessible URLs:
1. UDP socket heuristic (connect to `8.8.8.8:80`)
2. PowerShell `Get-NetIPAddress` (Windows)
3. `socket.getaddrinfo()` fallback
4. Sorted by preference: `192.168.x.x` > `10.x.x.x` > `172.16-31.x.x` > others

## ngrok Tunnels

For campus Wi-Fi (eduroam) where LAN traffic between devices is blocked:

```powershell
.\start-dev-ngrok.ps1
```

The frontend auto-detects the ngrok tunnel URL from the local agent API at `localhost:4040` (proxied via Vite to avoid CORS). Alternatively, set `VITE_PAIRING_ORIGIN` in `frontend/.env.local`.

## HTTPS Dev Mode

Chrome on Android blocks camera access on non-HTTPS origins. Enable HTTPS:

```powershell
.\start-dev.ps1 -DevHttps
# or
cd frontend && npm run dev:https
```

This uses `@vitejs/plugin-basic-ssl` to serve with a self-signed certificate.

## Vite Proxy Rules

All API paths are proxied from the Vite dev server (port 5173) to Flask (port 5000):
- `/analyze`, `/health`, `/host-info`, `/voice-to-text` → Flask
- `/session/*`, `/prompts/*` → Flask
- `/__vite_dev/ngrok-agent/tunnels` → `localhost:4040/api/tunnels`

## Firewall

On Windows, run as Administrator once:
```powershell
.\scripts\allow-dev-ports-firewall.ps1
```
Opens inbound TCP on ports 5000 and 5173.
