# ntfy-approve

Approve or deny [Claude Code](https://docs.anthropic.com/en/docs/claude-code) tool calls from your phone via [ntfy](https://ntfy.sh/) push notifications.

## Why this exists

Claude Code is an AI coding agent that runs in your terminal. It can read files, write code, run shell commands — but it asks for permission before doing anything potentially destructive. That permission prompt blocks the terminal until you respond.

This is fine when you're at your desk. But Claude Code sessions can run for minutes at a time, and you might walk away to make coffee, sit on the couch, or be in another room entirely. When that happens, Claude is stuck waiting, and your task stalls.

**ntfy-approve** solves this by sending each permission request as a push notification to your phone. You get a notification with the tool name and command, tap **Approve** or **Deny**, and Claude continues — no need to walk back to your laptop.

## Architecture

The system has three components connected over a [Tailscale](https://tailscale.com/) mesh network:

```
┌─────────────────────────────────────────────────┐
│  YOUR MACHINE                                   │
│                                                 │
│  Claude Code (terminal)                         │
│    ├─ Needs permission for a tool               │
│    └─→ Fires PermissionRequest hook             │
│                                                 │
│  ntfy-approve.py (runs in parallel w/ prompt)   │
│    ├─ POST notification → ntfy server           │
│    └─ Poll response topic every 3s              │
│                                                 │
│  ntfy server (Docker, localhost:8090)            │
│    ├─ Topic: cc-approve  (notifications out)    │
│    └─ Topic: cc-response (decisions back)       │
│                                                 │
└──────────────────────┬──────────────────────────┘
                       │ Tailscale
┌──────────────────────┴──────────────────────────┐
│  YOUR PHONE                                     │
│                                                 │
│  ntfy app                                       │
│    ├─ Subscribed to cc-approve via WebSocket     │
│    ├─ Shows notification with [Approve] [Deny]  │
│    └─ Button tap POSTs to cc-response topic     │
│                                                 │
└─────────────────────────────────────────────────┘
```

Both channels (terminal prompt and phone notification) are active simultaneously. Respond from whichever device is convenient:

- **Phone answers first** — Claude gets the decision, notification auto-dismisses
- **Terminal answers first** — the hook process is killed, cleanup deletes the phone notification
- **Neither answers within 120s** — the hook exits silently, terminal prompt remains active

A second hook (`ntfy-notify.sh`) sends a lightweight push notification whenever Claude is idle and waiting for user input, so you know when to check back.

### How Claude Code hooks work

Claude Code supports [hooks](https://docs.anthropic.com/en/docs/claude-code/hooks) — shell commands that run in response to lifecycle events. This project uses two:

- **`PermissionRequest`** — fires when Claude needs permission for a tool. The hook runs *in parallel* with the normal terminal prompt. If the hook returns a JSON decision (`allow` or `deny`), Claude uses it. If the hook exits without output (timeout, error, or terminal answered first), Claude falls back to the terminal prompt.
- **`Notification`** — fires on events like `idle_prompt`. This hook is fire-and-forget: it sends a notification and exits immediately.

### Why Tailscale

The ntfy server runs on localhost and is not exposed to the internet. [Tailscale](https://tailscale.com/) creates a private mesh VPN between your devices, so your phone can reach the ntfy server at its Tailscale IP without any port forwarding, dynamic DNS, or public exposure.

The credentials file stores two URLs for this reason:
- `NTFY_SERVER` — `http://localhost:8090` for the hook scripts (running on the same machine)
- `NTFY_TAILSCALE_URL` — `http://<tailscale-ip>:8090` for the phone (used in notification action button URLs, since the phone can't reach `localhost`)

### Alternative: LAN-only (no Tailscale)

> **Note:** This approach is untested. It should work in theory but has not been verified.

If your phone and laptop are always on the same WiFi network, you can skip Tailscale entirely. The Docker port mapping (`"8090:80"`) binds to all interfaces by default, so ntfy is already reachable from your LAN. Just set `NTFY_TAILSCALE_URL` to your machine's local IP:

```bash
NTFY_TAILSCALE_URL=http://192.168.1.x:8090
```

This is simpler but comes with limitations: it only works on the same network (no approvals from mobile data or other WiFi), you need to know your laptop's IP and update the credentials file every time you switch WiFi networks, and traffic is unencrypted HTTP rather than a WireGuard tunnel.

### Why self-hosted ntfy

You could use the public ntfy.sh server, but self-hosting means:
- No rate limits on your own topics
- Auth is locked down (`deny-all` default — only your user can access the topics)
- No dependency on an external service
- Full control over message retention and server config

## How it works in detail

```
Claude Code
  |
  +- PermissionRequest hook (ntfy-approve.py)
  |    Runs in parallel with terminal permission prompt.
  |    +- POST notification with Approve/Deny buttons
  |    +- Poll response topic for decision
  |    +- Phone tap -> return allow/deny -> tool executes or is denied
  |    +- Terminal answer first -> notification auto-deleted from phone
  |    +- Timeout (120s) -> exit silently, terminal prompt still active
  |
  +- Notification hook (ntfy-notify.sh)
       +- idle_prompt -> fire-and-forget push notification

ntfy server (Docker, port 8090)
  +- Auth: deny-all default, single user with topic access
  +- Topic: cc-approve  (notifications TO phone)
  +- Topic: cc-response (decisions FROM phone)

Phone (ntfy app)
  +- Connects via Tailscale or LAN
  +- Subscribed to cc-approve, action buttons POST to cc-response
```

## Notification format

Notifications show the project name prominently so you can distinguish between multiple Claude Code sessions:

| Tool | Title | Body | Emoji |
|------|-------|------|-------|
| Bash | `project . description` | `$ command` | computer |
| Edit | `project . Edit filename` | relative path, old/new first line | pencil |
| Write | `project . Write filename` | relative path | page |
| Other | `project . ToolName` | parameters | wrench |

## Prerequisites

- Docker
- Python 3 (stdlib only, no pip packages)
- jq (for the notification hook)
- Phone with the [ntfy app](https://ntfy.sh/) (F-Droid recommended for self-hosted)
- Network access from phone to server (Tailscale or LAN)

## Setup

### 1. Create credentials file

Create `~/.config/ntfy/credentials`:

```bash
NTFY_SERVER=http://localhost:8090
NTFY_TAILSCALE_URL=http://<your-tailscale-ip>:8090
NTFY_USER=<username>
NTFY_PASS=<your-password>
NTFY_TOPIC_APPROVE=cc-approve
NTFY_TOPIC_RESPONSE=cc-response
```

`NTFY_SERVER` is used by the hook scripts (local requests). `NTFY_TAILSCALE_URL` is used in the action button URLs (the phone makes these HTTP calls, so they must be phone-reachable).

### 2. Start the ntfy server

```bash
cp docker/.env.example docker/.env  # edit TZ if needed
cd docker/
docker compose up -d
```

### 3. Create user and grant topic access

The script reads username and topics from the credentials file:

```bash
NTFY_PASSWORD=<your-password> ./docker/setup-auth.sh
```

### 4. Configure Claude Code hooks

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PermissionRequest": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/usr/bin/python3 /path/to/ntfy-approve/hooks/ntfy-approve.py",
            "timeout": 180
          }
        ]
      }
    ],
    "Notification": [
      {
        "matcher": "idle_prompt",
        "hooks": [
          {
            "type": "command",
            "command": "/path/to/ntfy-approve/hooks/ntfy-notify.sh",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

### 5. Phone setup

1. Install ntfy from [F-Droid](https://f-droid.org/packages/io.heckel.ntfy/)
2. Settings -> Manage users -> add your server URL and credentials
3. Subscribe to the `cc-approve` topic on your server
4. Enable WebSockets when prompted
5. Exempt ntfy from battery optimization (Android Settings -> Apps -> ntfy -> Battery -> Unrestricted)

### 6. Verify

```bash
# Server health
curl -u user:pass http://localhost:8090/v1/health

# Test notification on phone
curl -u user:pass -H "Title: Test" -d "Hello" http://localhost:8090/cc-approve

# Test approval hook (tap Approve/Deny on phone within 60s)
echo '{"hook_event_name":"PermissionRequest","tool_name":"Bash","tool_input":{"command":"echo test"},"cwd":"/tmp"}' \
  | python3 hooks/ntfy-approve.py
```

## Files

```
hooks/
  ntfy-approve.py   PermissionRequest hook -- notification + polling + cleanup
  ntfy-notify.sh    Notification hook -- idle prompt alerts
docker/
  docker-compose.yml  ntfy container config (port 8090)
  server.yml          ntfy server settings (deny-all auth, local cache)
  setup-auth.sh       one-time user/topic access setup
  .env.example        environment template (timezone)
```
