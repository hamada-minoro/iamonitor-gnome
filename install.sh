#!/bin/bash
# IAMonitor installer for GNOME/Linux
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/iamonitor"
DESKTOP_AUTOSTART_DIR="$HOME/.config/autostart"

echo "==> IAMonitor Installer"
echo "    Source: $SCRIPT_DIR"

# -----------------------------------------------------------------------
# 1. Detect distro and install system packages
# -----------------------------------------------------------------------
detect_and_install_packages() {
    echo "==> Detecting distribution…"

    PKG_GTK=""
    PKG_INDICATOR=""
    PKG_GLIB=""
    PKG_NOTIFY=""

    if command -v apt-get &>/dev/null; then
        echo "    Detected: Debian/Ubuntu/ZorinOS/Pop!_OS"

        # GObject introspection + GTK3
        PACKAGES="python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-glib-2.0 gir1.2-notify-0.7"

        # Try AyatanaAppIndicator first (Ubuntu 22+, ZorinOS, Pop)
        if apt-cache show gir1.2-ayatanaappindicator3-0.1 &>/dev/null 2>&1; then
            PACKAGES="$PACKAGES gir1.2-ayatanaappindicator3-0.1 libayatana-appindicator3-dev"
        elif apt-cache show gir1.2-appindicator3-0.1 &>/dev/null 2>&1; then
            PACKAGES="$PACKAGES gir1.2-appindicator3-0.1 libappindicator3-dev"
        else
            echo "    WARNING: No AppIndicator package found — system tray may not work."
            echo "    Try: sudo apt-get install gir1.2-ayatanaappindicator3-0.1"
        fi

        # libdbus for secretstorage
        PACKAGES="$PACKAGES python3-secretstorage libsecret-1-dev"

        echo "==> Installing system packages (requires sudo)…"
        sudo apt-get install -y $PACKAGES

    elif command -v dnf &>/dev/null; then
        echo "    Detected: Fedora/RHEL"
        PACKAGES="python3-gobject python3-gobject-base gtk3 libnotify"
        if dnf list available libappindicator-gtk3 &>/dev/null 2>&1; then
            PACKAGES="$PACKAGES libappindicator-gtk3"
        fi
        PACKAGES="$PACKAGES python3-secretstorage libsecret"
        echo "==> Installing system packages (requires sudo)…"
        sudo dnf install -y $PACKAGES

    elif command -v pacman &>/dev/null; then
        echo "    Detected: Arch Linux / Manjaro"
        PACKAGES="python-gobject gtk3 libnotify python-secretstorage"
        if pacman -Ss libappindicator-gtk3 &>/dev/null 2>&1; then
            PACKAGES="$PACKAGES libappindicator-gtk3"
        fi
        echo "==> Installing system packages (requires sudo)…"
        sudo pacman -S --needed --noconfirm $PACKAGES

    elif command -v zypper &>/dev/null; then
        echo "    Detected: openSUSE"
        PACKAGES="python3-gobject python3-gobject-cairo typelib-1_0-Gtk-3_0 typelib-1_0-Notify-0_7 python3-SecretStorage"
        echo "==> Installing system packages (requires sudo)…"
        sudo zypper install -y $PACKAGES

    else
        echo "    WARNING: Unknown distribution. Please install GTK3 bindings manually."
        echo "    Required: python3-gi, gir1.2-gtk-3.0, gir1.2-notify-0.7, appindicator bindings"
    fi
}

# -----------------------------------------------------------------------
# 2. Install Python dependencies
# -----------------------------------------------------------------------
install_python_deps() {
    echo "==> Installing Python dependencies…"

    # On Debian/Ubuntu/ZorinOS, PyGObject and secretstorage are already
    # provided as system packages (python3-gi, python3-secretstorage).
    # Only inotify_simple is not available via apt and must come from pip.
    # On other distros we install the full requirements.txt.
    if command -v apt-get &>/dev/null; then
        PIP_PKGS="inotify_simple"
    else
        PIP_PKGS="-r $SCRIPT_DIR/requirements.txt"
    fi

    # Try a normal --user install first (works on Ubuntu ≤ 23.10)
    if pip3 install --user $PIP_PKGS 2>/dev/null; then
        echo "    Python dependencies installed."
        return 0
    fi

    # Ubuntu 24.04+ / ZorinOS 18+ / any distro enforcing PEP 668 blocks
    # plain pip installs to prevent breaking system packages.
    # --break-system-packages is safe here: we are only adding a small
    # user-local package (inotify_simple) that has no system-level impact.
    echo "    pip3 blocked (PEP 668 — externally managed Python environment)."
    echo "    Detected Ubuntu 24.04+ or ZorinOS 18+. Retrying with --break-system-packages…"
    if pip3 install --user --break-system-packages $PIP_PKGS; then
        echo "    Python dependencies installed (--break-system-packages)."
        return 0
    fi

    echo ""
    echo "    WARNING: Could not install pip packages automatically."
    echo "    inotify_simple is optional — the app will fall back to 5-second polling."
    echo "    To install manually: pip3 install --user --break-system-packages inotify_simple"
}

# -----------------------------------------------------------------------
# 3. Make entry point executable
# -----------------------------------------------------------------------
make_executable() {
    chmod +x "$SCRIPT_DIR/iamonitor.py"
    echo "==> Made iamonitor.py executable"
}

# -----------------------------------------------------------------------
# 4. Optional: install to /opt and set up autostart
# -----------------------------------------------------------------------
install_system_wide() {
    read -r -p "Install system-wide to $INSTALL_DIR? [y/N] " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        echo "==> Installing to $INSTALL_DIR (requires sudo)…"
        sudo mkdir -p "$INSTALL_DIR"
        sudo cp -r "$SCRIPT_DIR/"* "$INSTALL_DIR/"
        sudo chmod +x "$INSTALL_DIR/iamonitor.py"

        # Create symlink
        sudo ln -sf "$INSTALL_DIR/iamonitor.py" /usr/local/bin/iamonitor
        echo "    Installed symlink: /usr/local/bin/iamonitor"
    fi
}

# -----------------------------------------------------------------------
# 5. Optional: autostart
# -----------------------------------------------------------------------
setup_autostart() {
    read -r -p "Enable autostart on login? [y/N] " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        mkdir -p "$DESKTOP_AUTOSTART_DIR"
        DESKTOP_FILE="$DESKTOP_AUTOSTART_DIR/iamonitor.desktop"
        cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=IAMonitor
Comment=Claude Pro/Max usage monitor
Exec=/usr/bin/python3 $SCRIPT_DIR/iamonitor.py
Icon=$SCRIPT_DIR/data/icons/iamonitor.svg
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
        echo "    Autostart configured: $DESKTOP_FILE"
    fi
}

# -----------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------
detect_and_install_packages
install_python_deps
make_executable
install_system_wide
setup_autostart

echo ""
echo "==> Installation complete!"
echo ""
echo "    Run with: python3 $SCRIPT_DIR/iamonitor.py"
echo "    Or if installed system-wide: iamonitor"
echo ""
echo "    On first run, open Settings tab to configure your OAuth token"
echo "    (or the app will auto-detect it from GNOME Keyring / ~/.claude/.credentials.json)"
echo ""
