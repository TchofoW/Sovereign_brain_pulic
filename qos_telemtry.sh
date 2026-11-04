#!/bin/sh

# =====================================================================
# Configuration - Match this to your Sovereign Brain API
# =====================================================================
SERVER_URL="http://your-sovereign-server-ip:8000/api/telemetry"

# =====================================================================
# STEP 1: Dynamic Interface Detection (Wired WAN vs Wireless STA)
# =====================================================================
# Pulls the active interface handling outbound internet traffic right now
WAN_IFACE=$(ip route | grep default | awk '{print $5}' | head -n 1)

# Fallback mechanism if the routing table is temporarily settling
if [ -z "$WAN_IFACE" ]; then
    if ip link show wlan0-1 >/dev/null 2>&1; then
        WAN_IFACE="wlan0-1" # Common OpenWrt wireless station interface name
    elif ip link show wlan0 >/dev/null 2>&1; then
        WAN_IFACE="wlan0"
    else
        WAN_IFACE="eth0" # Strict legacy hardware fallback
    fi
fi

# Detect if the chosen active interface belongs to a wireless system
IS_WIRELESS=0
if [ -d "/sys/class/net/$WAN_IFACE/wireless" ] || iw dev "$WAN_IFACE" info >/dev/null 2>&1; then
    IS_WIRELESS=1
fi

# =====================================================================
# STEP 2: Gather Universal Metrics (Telemetry Agent)
# =====================================================================
# Interface Byte & Packet counters
RX_BYTES=$(cat /sys/class/net/$WAN_IFACE/statistics/rx_bytes 2>/dev/null || echo 0)
TX_BYTES=$(cat /sys/class/net/$WAN_IFACE/statistics/tx_bytes 2>/dev/null || echo 0)
RX_PACKETS=$(cat /sys/class/net/$WAN_IFACE/statistics/rx_packets 2>/dev/null || echo 0)
TX_PACKETS=$(cat /sys/class/net/$WAN_IFACE/statistics/tx_packets 2>/dev/null || echo 0)
RX_ERRORS=$(cat /sys/class/net/$WAN_IFACE/statistics/rx_errors 2>/dev/null || echo 0)
TX_ERRORS=$(cat /sys/class/net/$WAN_IFACE/statistics/tx_errors 2>/dev/null || echo 0)

# Network Performance Diagnostics (Latency & Drop rates)
PING_RES=$(ping -c 3 -W 2 8.8.8.8 2>&1)
if [ $? -eq 0 ]; then
    LATENCY_AVG=$(echo "$PING_RES" | tail -n 1 | awk -F '/' '{print $5}')
    PACKET_LOSS=$(echo "$PING_RES" | grep -oE '[0-9]+% packet loss' | awk '{print $1}' | sed 's/%//')
else
    LATENCY_AVG=0
    PACKET_LOSS=100
fi

# Tracking state limits (Active connection flows)
if [ -f /proc/sys/net/netfilter/nf_conntrack_count ]; then
    TOTAL_FLOWS=$(cat /proc/sys/net/netfilter/nf_conntrack_count)
    TCP_ESTABLISHED=$(grep -c "ESTABLISHED" /proc/net/nf_conntrack 2>/dev/null || echo 0)
else
    TOTAL_FLOWS=$(awk 'END{print NR}' /proc/net/arp 2>/dev/null || echo 0)
    TCP_ESTABLISHED=0
fi

LOAD_AVG=$(uptime | awk -F'load average:' '{print $2}' | awk -F',' '{print $1}' | sed 's/ //g')
UPTIME_SEC=$(awk '{print int($1)}' /proc/uptime)

# =====================================================================
# STEP 3: Gather Conditional Wireless Profiles (Optimized)
# =====================================================================
SIGNAL_DBM=0
NOISE_DBM=0
TX_BITRATE="0.0"
RX_BITRATE="0.0"
EXPECTED_THROUGHPUT="0.0"
IFACE_TYPE="wired"

if [ "$IS_WIRELESS" -eq 1 ] && command -v iw >/dev/null 2>&1; then
    IFACE_TYPE="wireless"
    IW_INFO=$(iw dev "$WAN_IFACE" station dump 2>/dev/null)
    if [ -n "$IW_INFO" ]; then
        SIGNAL_DBM=$(echo "$IW_INFO" | grep "signal:" | awk '{print $2}' || echo 0)
        NOISE_DBM=$(echo "$IW_INFO" | grep "signal avg:" | awk '{print $3}' || echo 0)
        TX_BITRATE=$(echo "$IW_INFO" | grep "tx bitrate:" | awk '{print $3}' || echo 0)
        RX_BITRATE=$(echo "$IW_INFO" | grep "rx bitrate:" | awk '{print $3}' || echo 0)
        EXPECTED_THROUGHPUT=$(echo "$IW_INFO" | grep "expected throughput:" | awk '{print $3}' | sed 's/Mbps//' || echo 0)
    fi
fi

# =====================================================================
# STEP 4: Construct the Hybrid Telemetry JSON Payload (Using Unique MAC)
# =====================================================================
# Read the globally unique hardware MAC address of the active outbound interface
ROUTER_ID=$(cat /sys/class/net/$WAN_IFACE/address 2>/dev/null | tr -d ':')

# If the system file is unreadable, fall back to the system hostname 
if [ -z "$ROUTER_ID" ]; then
    ROUTER_ID=$(uci get system.@system[0].hostname 2>/dev/null || echo "unknown-router")
fi

JSON_PAYLOAD=$(cat <<EOF
{
  "router_id": "$ROUTER_ID",
  "timestamp": $(date +%s),
  "uptime_seconds": $UPTIME_SEC,
  "system_load": $LOAD_AVG,
  "interface": {
    "name": "$WAN_IFACE",
    "type": "$IFACE_TYPE",
    "rx_bytes": $RX_BYTES,
    "tx_bytes": $TX_BYTES,
    "rx_packets": $RX_PACKETS,
    "tx_packets": $TX_PACKETS,
    "rx_errors": $RX_ERRORS,
    "tx_errors": $TX_ERRORS
  },
  "wireless_profile": {
    "signal_strength_dbm": ${SIGNAL_DBM:-0},
    "noise_floor_dbm": ${NOISE_DBM:-0},
    "tx_bitrate_mbps": ${TX_BITRATE:-0},
    "rx_bitrate_mbps": ${RX_BITRATE:-0},
    "expected_throughput_mbps": ${EXPECTED_THROUGHPUT:-0}
  },
  "latency_profile": {
    "ping_target": "8.8.8.8",
    "avg_latency_ms": ${LATENCY_AVG:-0},
    "packet_loss_percent": ${PACKET_LOSS:-0}
  },
  "active_flows": {
    "total_tracked": $TOTAL_FLOWS,
    "tcp_established": $TCP_ESTABLISHED
  }
}
EOF
)

# =====================================================================
# STEP 5: Transmit Data and Await Sovereign Brain Response
# =====================================================================
RESPONSE=$(curl -s -X POST \
  -H "Content-Type: application/json" \
  -d "$JSON_PAYLOAD" \
  "$SERVER_URL")

# =====================================================================
# STEP 6: Parse & Execute Target Tailored QoS Controls
# =====================================================================
if [ -n "$RESPONSE" ] && command -v jq >/dev/null 2>&1; then

    QOS_ENABLED=$(echo "$RESPONSE" | jq -r '.qos_enabled // empty')
    DOWN_LIMIT=$(echo "$RESPONSE" | jq -r '.download_limit // empty')
    UP_LIMIT=$(echo "$RESPONSE" | jq -r '.upload_limit // empty')
    QDISC_ALGO=$(echo "$RESPONSE" | jq -r '.qdisc_algo // empty') 

    CHANGES_MADE=0

    if [ -n "$QOS_ENABLED" ]; then
        uci set sqm.wan.enabled="$QOS_ENABLED"
        CHANGES_MADE=1
    fi

    if [ -n "$DOWN_LIMIT" ]; then
        uci set sqm.wan.download="$DOWN_LIMIT"
        CHANGES_MADE=1
    fi

    if [ -n "$UP_LIMIT" ]; then
        uci set sqm.wan.upload="$UP_LIMIT"
        CHANGES_MADE=1
    fi

    if [ -n "$QDISC_ALGO" ]; then
        uci set sqm.wan.qdisc="$QDISC_ALGO"
        CHANGES_MADE=1
    fi

    # Dynamically repoint SQM structure to the currently active interface
    if [ -n "$WAN_IFACE" ]; then
        CURRENT_SQM_IFACE=$(uci get sqm.wan.interface 2>/dev/null)
        if [ "$CURRENT_SQM_IFACE" != "$WAN_IFACE" ]; then
            uci set sqm.wan.interface="$WAN_IFACE"
            CHANGES_MADE=1
        fi
    fi

    # Save and restart traffic shaping engines if modifications were handed down
    if [ "$CHANGES_MADE" -eq 1 ]; then
        uci commit sqm
        /etc/init.d/sqm restart >/dev/null 2>&1
        logger -t qos_telemetry "Resilient QoS update applied successfully onto dynamic link: $WAN_IFACE ($IFACE_TYPE)"
    fi
else
    logger -t qos_telemetry "No instructions received or parsing system dependencies failed."
fi
