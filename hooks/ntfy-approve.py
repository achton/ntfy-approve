#!/usr/bin/env python3
"""
Claude Code PermissionRequest hook for ntfy.

Sends a push notification with Approve/Deny action buttons.
Polls the response topic for the user's decision.
Runs in parallel with the terminal permission prompt.

When the terminal is used to answer (killing this process), the
notification is automatically deleted from the phone via cleanup.
"""

import atexit
import json
import os
import signal
import sys
import time
import urllib.request
import urllib.error
import base64

POLL_INTERVAL = 3  # seconds
TIMEOUT = 120  # seconds

# Global state for cleanup
_cleanup_info = {"creds": None, "message_id": None}


def load_credentials():
    cred_path = os.path.expanduser("~/.config/ntfy/credentials")
    creds = {}
    with open(cred_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, value = line.partition("=")
            creds[key.strip()] = value.strip()
    return creds


def auth_header(creds):
    token = base64.b64encode(
        f"{creds['NTFY_USER']}:{creds['NTFY_PASS']}".encode()
    ).decode()
    return f"Basic {token}"


def delete_notification(creds, message_id):
    """Delete the notification from the phone via ntfy API."""
    server = creds["NTFY_SERVER"]
    topic = creds["NTFY_TOPIC_APPROVE"]
    url = f"{server}/{topic}/{message_id}"
    req = urllib.request.Request(url, method="DELETE")
    req.add_header("Authorization", auth_header(creds))
    try:
        urllib.request.urlopen(req, timeout=5)
    except (urllib.error.URLError, OSError):
        pass


def cleanup():
    """Remove the phone notification on exit (terminal answered first)."""
    creds = _cleanup_info.get("creds")
    message_id = _cleanup_info.get("message_id")
    if creds and message_id:
        delete_notification(creds, message_id)


def handle_signal(signum, frame):
    """Ensure cleanup runs on SIGTERM/SIGINT."""
    sys.exit(0)


def _relative_path(filepath, cwd):
    """Make a file path relative to cwd if it's underneath it."""
    if cwd and filepath.startswith(cwd):
        rel = filepath[len(cwd):].lstrip("/")
        return rel or filepath
    return filepath


# ntfy tag shortcodes → rendered as emoji in the app
TOOL_TAGS = {
    "Bash": "computer",
    "Edit": "pencil2",
    "Write": "page_facing_up",
    "Read": "eyes",
    "Glob": "mag",
    "Grep": "mag",
    "WebFetch": "globe_with_meridians",
    "WebSearch": "globe_with_meridians",
}


def build_notification(data):
    """Build title, body, and tag from the hook input."""
    tool_name = data.get("tool_name", "Unknown")
    tool_input = data.get("tool_input", {})
    cwd = data.get("cwd", "")
    project = os.path.basename(cwd) if cwd else "unknown"

    tag = TOOL_TAGS.get(tool_name, "wrench")
    title = f"{project} \u00b7 {tool_name}"

    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        desc = tool_input.get("description", "")
        if desc:
            title = f"{project} \u00b7 {desc[:60]}"
        body = f"$ {cmd}" if cmd else "(empty command)"
    elif tool_name == "Edit":
        fpath = tool_input.get("file_path", "")
        rel = _relative_path(fpath, cwd)
        title = f"{project} \u00b7 Edit {os.path.basename(fpath)}"
        old = (tool_input.get("old_string", "") or "").strip()
        new = (tool_input.get("new_string", "") or "").strip()
        lines = [rel]
        if old:
            lines.append(f"\u2212 {old.splitlines()[0][:80]}")
        if new:
            lines.append(f"+ {new.splitlines()[0][:80]}")
        body = "\n".join(lines)
    elif tool_name == "Write":
        fpath = tool_input.get("file_path", "")
        rel = _relative_path(fpath, cwd)
        title = f"{project} \u00b7 Write {os.path.basename(fpath)}"
        body = rel
    else:
        params = ", ".join(
            f"{k}={str(v)[:60]}" for k, v in list(tool_input.items())[:3]
        )
        body = params or tool_name

    return title, body, tag


def publish_notification(creds, title, body, tool_use_id, tag="wrench"):
    """POST notification to ntfy with Approve/Deny action buttons."""
    server = creds["NTFY_SERVER"]
    tailscale = creds["NTFY_TAILSCALE_URL"]
    topic_approve = creds["NTFY_TOPIC_APPROVE"]
    topic_response = creds["NTFY_TOPIC_RESPONSE"]

    response_url = f"{tailscale}/{topic_response}"

    # Build action button headers
    allow_body = json.dumps({"id": tool_use_id, "decision": "allow"})
    deny_body = json.dumps({"id": tool_use_id, "decision": "deny"})

    actions = "; ".join([
        f"http, Approve, {response_url}, headers.Authorization={auth_header(creds)}, body='{allow_body}', clear=true",
        f"http, Deny, {response_url}, headers.Authorization={auth_header(creds)}, body='{deny_body}', clear=true",
    ])

    # Use tool_use_id as message ID so we can delete it later
    message_id = tool_use_id[:64]  # ntfy has a max ID length

    url = f"{server}/{topic_approve}"
    req = urllib.request.Request(url, data=body.encode(), method="POST")
    req.add_header("Authorization", auth_header(creds))
    req.add_header("Title", title)
    req.add_header("Priority", "4")  # high
    req.add_header("Tags", tag)
    req.add_header("Actions", actions)
    req.add_header("X-Id", message_id)

    urllib.request.urlopen(req, timeout=10)
    return message_id


def poll_response(creds, tool_use_id):
    """Poll the response topic for a matching decision."""
    server = creds["NTFY_SERVER"]
    topic_response = creds["NTFY_TOPIC_RESPONSE"]
    auth = auth_header(creds)

    start = time.time()
    poll_since = int(start)

    while time.time() - start < TIMEOUT:
        try:
            url = f"{server}/{topic_response}/json?poll=1&since={poll_since}"
            req = urllib.request.Request(url)
            req.add_header("Authorization", auth)
            with urllib.request.urlopen(req, timeout=10) as resp:
                for line in resp:
                    line = line.decode().strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if msg.get("event") != "message":
                        continue
                    try:
                        payload = json.loads(msg.get("message", ""))
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if payload.get("id") == tool_use_id:
                        return payload.get("decision")
        except (urllib.error.URLError, OSError):
            pass

        time.sleep(POLL_INTERVAL)

    return None


def main():
    # Register signal handlers so cleanup runs on termination
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    atexit.register(cleanup)

    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)

    tool_use_id = data.get("tool_use_id", "")
    if not tool_use_id:
        sys.exit(0)

    try:
        creds = load_credentials()
    except (FileNotFoundError, KeyError):
        sys.exit(0)

    title, body, tag = build_notification(data)

    try:
        message_id = publish_notification(creds, title, body, tool_use_id, tag)
    except (urllib.error.URLError, OSError):
        sys.exit(0)

    # Store for cleanup (delete notification if terminal answers first)
    _cleanup_info["creds"] = creds
    _cleanup_info["message_id"] = message_id

    decision = poll_response(creds, tool_use_id)

    if decision in ("allow", "deny"):
        # Phone answered — clear cleanup (notification already dismissed via clear=true)
        _cleanup_info["message_id"] = None
        result = {"jsonrpc": "2.0", "result": {"decision": decision}}
        print(json.dumps(result))


if __name__ == "__main__":
    main()
