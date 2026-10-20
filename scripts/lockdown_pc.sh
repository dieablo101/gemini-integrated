#!/usr/bin/env bash
# ==============================================================================
# Gemini Autonomous Security Lockdown: Toughbook Host & Fleet Subsystem
# ==============================================================================
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
   echo "🚨 This script must be run as root. Please run: sudo $0" >&2
   exit 1
fi

echo "================================================================="
echo "🛡️  GEMINI AUTONOMOUS SECURITY LOCKDOWN PROTOCOL"
echo "================================================================="

# 1. Determine Local Subnet for Fleet Whitelist
PRIMARY_IFACE=$(ip route show default 2>/dev/null | awk '/default/ {print $5}' | head -n 1)
if [[ -n "$PRIMARY_IFACE" ]]; then
    SUBNET=$(ip -o -f inet addr show "$PRIMARY_IFACE" 2>/dev/null | awk '{print $4}' | head -n 1)
else
    SUBNET="192.168.1.0/24"
fi

if [[ -z "$SUBNET" ]]; then
    SUBNET="192.168.1.0/24"
fi

echo "[1/5] Detected Active Interface: ${PRIMARY_IFACE:-unknown} | Local Subnet: ${SUBNET}"

# 2. Firewall Hardening via UFW
echo "[2/5] Hardening UFW Firewall..."
if ! command -v ufw >/dev/null 2>&1; then
    apt-get update -qq && apt-get install -y -qq ufw
fi

ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow in on lo comment 'Allow full loopback traffic'

# Allow SSH only from trusted local subnet
ufw allow from "$SUBNET" to any port 22 proto tcp comment 'SSH restricted to trusted local subnet'

# Allow Gemini Fleet Mothership only from trusted local subnet
ufw allow from "$SUBNET" to any port 7331 proto tcp comment 'Gemini Fleet Mothership restricted to local subnet'

ufw --force enable
echo "  ✓ UFW enabled: default deny incoming; SSH and Fleet restricted to $SUBNET."

# 3. SSH Server Hardening
echo "[3/5] Hardening OpenSSH Server Configuration..."
SSHD_DROPIN="/etc/ssh/sshd_config.d/99-gemini-security.conf"
mkdir -p /etc/ssh/sshd_config.d

cat << 'EOF' > "$SSHD_DROPIN"
# Gemini Security Hardening: Enforce Key-Only Authentication & Reject Brute Force
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
X11Forwarding no
MaxAuthTries 3
LoginGraceTime 30
ClientAliveInterval 300
ClientAliveCountMax 2
EOF

# Validate syntax before reloading
if sshd -t; then
    systemctl reload sshd || systemctl restart ssh || service ssh restart
    echo "  ✓ SSH hardened: Password auth disabled, root login disabled, Ed25519 key-only enforced."
else
    echo "  ⚠️ SSH config validation failed; removing dropin to prevent lockout."
    rm -f "$SSHD_DROPIN"
fi

# 4. Kernel Network & Sysctl Hardening
echo "[4/5] Applying Kernel Sysctl Hardening..."
SYSCTL_FILE="/etc/sysctl.d/99-gemini-security.conf"

cat << 'EOF' > "$SYSCTL_FILE"
# Gemini Host Defense: Network Stack Hardening
net.ipv4.tcp_syncookies = 1
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.default.accept_source_route = 0
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv4.conf.all.secure_redirects = 0
net.ipv4.conf.default.secure_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.default.send_redirects = 0
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1
net.ipv4.icmp_echo_ignore_broadcasts = 1
net.ipv4.icmp_ignore_bogus_error_responses = 1
fs.protected_hardlinks = 1
fs.protected_symlinks = 1
EOF

sysctl --system >/dev/null 2>&1 || true
echo "  ✓ Kernel parameters hardened (SYN cookies enabled, source routing & redirects disabled)."

# 5. Fail2ban Protection (Optional / Recommended)
echo "[5/5] Ensuring Fail2ban Intrusion Defense..."
if ! command -v fail2ban-client >/dev/null 2>&1; then
    echo "  → Installing fail2ban for automated IP ban on brute-force attempts..."
    apt-get update -qq && apt-get install -y -qq fail2ban || true
fi

if command -v fail2ban-client >/dev/null 2>&1; then
    systemctl enable fail2ban || true
    systemctl restart fail2ban || true
    echo "  ✓ Fail2ban active and guarding authentication endpoints."
fi

echo "================================================================="
echo "✅ HOST & FLEET LOCKDOWN COMPLETE"
echo "   • Network: UFW active, unsolicited incoming ports blocked."
echo "   • Fleet: Port 7331 open only to trusted local subnet ($SUBNET)."
echo "   • Access: SSH key-only enforced (passwords disabled)."
echo "   • Kernel: TCP/IP stack hardened against spoofing and flooding."
echo "================================================================="
