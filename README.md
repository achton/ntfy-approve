# ntfy-approve

Approve or deny Claude Code tool calls from your phone via [ntfy](https://ntfy.sh/) push notifications.

## How it works

Claude Code blocks when it needs permission to use a tool. This project sends a push notification with **Approve** and **Deny** action buttons, so you can unblock it from your phone without returning to the terminal.

Both channels are active simultaneously — the terminal prompt and the phone notification. Respond from whichever device is convenient. If you respond from the terminal, the phone notification is automatically deleted.

```
Claude Code
  │
  ├─ PermissionRequest hook (ntfy-approve.py)
  │    Runs in parallel with terminal permission prompt.
  │    ├─ POST notification with Approve/Deny buttons
  │    ├─ Poll response topic for decision
  │    ├─ Phone tap → return allow/deny → tool executes or is denied
  │    ├─ Terminal answer first → notification auto-deleted from phone
  │    └─ Timeout (120s) → exit silently, terminal prompt still active
  │
  └─ Notification hook (ntfy-notify.sh)
       └─ idle_prompt → fire-and-forget push notification

ntfy server (Docker, port 8090)
  ├─ Auth: deny-all default, single user with topic access
  ├─ Topic: cc-approve  (notifications TO phone)
  └─ Topic: cc-response (decisions FROM phone)

Phone (ntfy app)
  ├─ Connects via Tailscale or LAN
  └─ Subscribed to cc-approve, action buttons POST to cc-response
```

## Notification format

Notifications show the project name prominently so you can distinguish between multiple Claude Code sessions:

| Tool | Title | Body | Emoji |
|------|-------|------|-------|
| Bash | `project · description` | `$ command` | 🖥️ |
| Edit | `project · Edit filename` | relative path, old/new first line | ✏️ |
| Write | `project · Write filename` | relative path | 📄 |
| Other | `project · ToolName` | parameters | 🔧 |

## Prerequisites

- Docker
- Python 3 (stdlib only, no pip packages)
- Phone with the [ntfy app](https://ntfy.sh/) (F-Droid recommended for self-hosted)
- Network access from phone to server (Tailscale or LAN)

## Setup

### 1. Start the ntfy server

```bash
cd docker/
docker compose up -d
```

### 2. Create user and grant topic access

```bash
NTFY_PASSWORD=<your-password> ./docker/setup-auth.sh
```

### 3. Create credentials file

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
2. Settings → Manage users → add your server URL and credentials
3. Subscribe to the `cc-approve` topic on your server
4. Enable WebSockets when prompted
5. Exempt ntfy from battery optimization (Android Settings → Apps → ntfy → Battery → Unrestricted)

### 6. Verify

```bash
# Server health
curl -u user:pass http://localhost:8090/v1/health

# Test notification on phone
curl -u user:pass -H "Title: Test" -d "Hello" http://localhost:8090/cc-approve

# Test approval hook (tap Approve/Deny on phone within 60s)
echo '{"tool_name":"Bash","tool_input":{"command":"echo test"},"tool_use_id":"test123","cwd":"/tmp"}' \
  | python3 hooks/ntfy-approve.py
```

## Files

```
hooks/
  ntfy-approve.py   PermissionRequest hook — notification + polling + cleanup
  ntfy-notify.sh    Notification hook — idle prompt alerts
docker/
  docker-compose.yml  ntfy container config (port 8090)
  server.yml          ntfy server settings (deny-all auth, local cache)
  setup-auth.sh       one-time user/topic access setup
```

## License

MIT
