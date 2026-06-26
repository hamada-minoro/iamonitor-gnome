# IAMonitor for GNOME/Linux

![Ubuntu](https://img.shields.io/badge/Ubuntu-22.04%2B%20%7C%2024.04%2B-E95420?logo=ubuntu&logoColor=white)
![ZorinOS](https://img.shields.io/badge/ZorinOS-16%2B%20%7C%2018.2-15A6F0?logo=zorin&logoColor=white)
![Pop!_OS](https://img.shields.io/badge/Pop!__OS-22.04%2B-48B9C7?logo=system76&logoColor=white)
![Fedora](https://img.shields.io/badge/Fedora-38%2B-294172?logo=fedora&logoColor=white)
![Arch Linux](https://img.shields.io/badge/Arch_Linux-rolling-1793D1?logo=arch-linux&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)

A GNOME/Linux system tray app that monitors your **Claude Pro/Max** API usage in real time — a port of the original [IAMonitor](https://github.com/hamada-minoro/IAMonitor) macOS app.

---

## Compatible Systems

| Distribution | AppIndicator Library | Status |
|---|---|---|
| Ubuntu 24.04 (Noble) | AyatanaAppIndicator3 | ✓ Tested |
| Ubuntu 22.04 (Jammy) | AyatanaAppIndicator3 | ✓ Tested |
| Ubuntu 20.04 (Focal) | AppIndicator3 | ✓ Should work |
| ZorinOS 18.2 | AyatanaAppIndicator3 | ✓ Tested |
| ZorinOS 16/17 | AyatanaAppIndicator3 | ✓ Compatible |
| Pop!_OS 22.04+ | AyatanaAppIndicator3 | ✓ Compatible |
| Linux Mint 21+ | AyatanaAppIndicator3 | ✓ Compatible |
| Fedora 38+ | libappindicator3 | ✓ Compatible |
| Arch / Manjaro | libappindicator-gtk3 | ✓ Compatible |
| openSUSE Tumbleweed | libappindicator3 | ✓ Compatible |

> **Note**: Requires GNOME Shell with an AppIndicator extension (e.g., [AppIndicator and KStatusNotifierItem Support](https://extensions.gnome.org/extension/615/appindicator-support/)) if your GNOME version doesn't support them natively.

---

## Prerequisites

- Python 3.10 or newer
- GTK 3.0 (usually pre-installed on GNOME desktops)
- An Anthropic Claude Pro or Max subscription with OAuth credentials

---

## Installation

```bash
# Clone the repo
git clone https://github.com/hamada-minoro/IAMonitor-Gnome.git
cd IAMonitor-Gnome

# Run the installer (handles system packages + pip deps)
./install.sh
```

The installer will:
1. Detect your distribution and install GTK/AppIndicator system packages
2. Install the `inotify_simple` pip package (with automatic PEP 668 fallback for Ubuntu 24.04+ / ZorinOS 18+)
3. Optionally install system-wide to `/opt/iamonitor`
4. Optionally configure autostart on login

> **Ubuntu 24.04+ / ZorinOS 18+**: These releases enforce PEP 668, which blocks plain `pip3 install --user`. The installer detects this automatically and retries with `--break-system-packages`. Only `inotify_simple` is installed this way — `PyGObject` and `secretstorage` come from apt and are never touched by pip.

### Manual installation

```bash
# System packages (Debian/Ubuntu/ZorinOS)
sudo apt-get install python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
    gir1.2-notify-0.7 gir1.2-ayatanaappindicator3-0.1 \
    python3-secretstorage

# inotify_simple (Ubuntu ≤ 23.10)
pip3 install --user inotify_simple

# inotify_simple (Ubuntu 24.04+ / ZorinOS 18+ — PEP 668 systems)
pip3 install --user --break-system-packages inotify_simple

# Run
python3 iamonitor.py
```

> `inotify_simple` is optional. If missing, the app automatically falls back to 5-second file polling with no loss of functionality.

---

## Usage

```bash
python3 iamonitor.py
```

A bar-chart icon will appear in your system tray. The label shows your current session usage percentage (e.g., `42%`).

- **Left-click / Show-Hide**: Toggle the popup window
- **Popup window**: Three tabs — Dashboard, Tasks, Settings

### First-time setup

1. Open the popup → **Settings** tab
2. Under **OAuth Token**: the app will auto-detect credentials from GNOME Keyring or `~/.claude/.credentials.json`
3. If auto-detection fails, paste your token manually and click **Save**
4. Set your **polling interval** (default: 2 minutes)
5. Choose your **plan** (Pro / Max 5x / Max 20x)

---

## How It Works

### Credential discovery (priority order)

1. **GNOME Keyring** — looks for a secret with service attribute `Claude Code-credentials`, decodes the JSON `{"claudeAiOauth": {"accessToken": "..."}}`
2. **File fallback** — reads `~/.claude/.credentials.json` with the same structure
3. **Manual config** — token saved in `~/.config/iamonitor/config.json`

### API polling

Every N seconds (configurable), the app sends a minimal POST to `https://api.anthropic.com/v1/messages` and reads these response headers:

| Header | Meaning |
|---|---|
| `anthropic-ratelimit-unified-5h-utilization` | Session usage 0.0–1.0 |
| `anthropic-ratelimit-unified-5h-reset` | Unix epoch of session reset |
| `anthropic-ratelimit-unified-7d-utilization` | Weekly usage 0.0–1.0 |
| `anthropic-ratelimit-unified-7d-reset` | Unix epoch of weekly reset |

### Local activity monitoring

Watches `~/.claude/history.jsonl` via **inotify** (falls back to 5-second polling). Each line is JSON:

```json
{"display": "…", "timestamp": 1719400000000, "project": "my-project", "sessionId": "abc123"}
```

Today's entries are filtered by `timestamp >= midnight`. Active time is estimated by summing gaps between consecutive messages — gaps ≥ 600s count as 2 minutes (session start credit).

### Budget management

- Daily budget in minutes (configurable)
- Auto-resets at a configurable hour
- Desktop notification when usage crosses the alert threshold
- Optional manual countdown timer

---

## Differences from macOS Version

| Feature | macOS (Swift/AppKit) | Linux (Python/GTK3) |
|---|---|---|
| Tray | NSStatusItem | AppIndicator3 / AyatanaAppIndicator3 |
| File watching | DispatchSource | inotify_simple (+ polling fallback) |
| Keychain | SecureKeychainAddGenericPassword | secretstorage (D-Bus Secret Service) |
| UI framework | SwiftUI + AppKit | PyGObject / GTK 3 |
| Notifications | UserNotifications | libnotify |
| Persistence | UserDefaults + Keychain | `~/.config/iamonitor/` (JSON) |
| Concurrency | @MainActor + async/await | GLib main loop + daemon threads |
| Entry point | `@main` SwiftUI App | `python3 iamonitor.py` |

---

## Configuration

Config is stored at `~/.config/iamonitor/config.json`:

```json
{
  "polling_interval": 120,
  "plan_type": "pro",
  "daily_budget_minutes": 480,
  "reset_hour": 0,
  "alert_at_percentage": 80,
  "oauth_token": ""
}
```

Tasks are stored in `~/.config/iamonitor/tasks.json`.

---

## Credits

- Original macOS app: [IAMonitor](https://github.com/Tonny-Francis/IAMonitor)
- Polling-via-headers idea: [hamada-minoro/api-claude-usage](https://github.com/hamada-minoro/api-claude-usage)
