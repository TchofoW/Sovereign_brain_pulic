#!/bin/sh

# =====================================================================
# Configuration - Match this to your Sovereign Brain API
# =====================================================================
SERVER_URL="https://sovereign-brain-owrv.onrender.com/api/telemetry"
CONFIRM_URL="https://sovereign-brain-owrv.onrender.com/api/telemetry/confirm"

# =====================================================================
# STEP 1: Dynamic Interface Detection (Wired WAN vs Wireless STA)
# =====================================================================
WAN_IFACE=$(ip route | grep default | awk '{print $5}' | head -n 1)

if [ -z "$WAN_IFACE" ]; then
    if ip link show wlan0-1 >/dev/null 2>&1; then
        WAN_IFACE="wlan0-1"
    elif ip link show wlan0 >/dev/null 2>&1; then
        WAN_IFACE="wlan0"
    else
        WAN_IFACE="eth0"
    fi
fi

IS_WIRELESS=0
if [ -d "/sys/class/net/$WAN_IFACE/wireless" ] || iw dev "$WAN_IFACE" info >/dev/null 2>&1; then
    IS_WIRELESS=1
fi

# =====================================================================
# STEP 2: Gather Universal & Kernel Telemetry Metrics
# =====================================================================
RX_BYTES=$(cat /sys/class/net/$WAN_IFACE/statistics/rx_bytes 2>/dev/null || echo 0)
TX_BYTES=$(cat /sys/class/net/$WAN_IFACE/statistics/tx_bytes 2>/dev/null || echo 0)
RX_PACKETS=$(cat /sys/class/net/$WAN_IFACE/statistics/rx_packets 2>/dev/null || echo 0)
TX_PACKETS=$(cat /sys/class/net/$WAN_IFACE/statistics/tx_packets 2>/dev/null || echo 0)
RX_ERRORS=$(cat /sys/class/net/$WAN_IFACE/statistics/rx_errors 2>/dev/null || echo 0)
TX_ERRORS=$(cat /sys/class/net/$WAN_IFACE/statistics/tx_errors 2>/dev/null || echo 0)

# Latency & Packet Loss
PING_RES=$(ping -c 3 -W 2 8.8.8.8 2>&1)
if [ $? -eq 0 ]; then
    LATENCY_AVG=$(echo "$PING_RES" | awk -F '/' 'END {print $5}' | tr -cd '0-9.-')
    PACKET_LOSS=$(echo "$PING_RES" | grep -oE '[0-9]+% packet loss' | awk '{print $1}' | sed 's/%//')
else
    LATENCY_AVG=0.0
    PACKET_LOSS=100
fi

# Extract Active tc Queue Metrics (CAKE / FQ-CoDel)
TC_SHOW=$(tc -s qdisc show dev $WAN_IFACE 2>/dev/null)
DROPS=$(echo "$TC_SHOW" | grep "dropped" | awk '{print $7}' | tr -d ',' | head -n1)
BACKLOG_BYTES=$(echo "$TC_SHOW" | grep "backlog" | awk '{print $2}' | tr -d 'b' | head -n1)
BACKLOG_PKTS=$(echo "$TC_SHOW" | grep "backlog" | awk '{print $4}' | tr -d 'p' | head -n1)
SOJOURN_MS=$(echo "$TC_SHOW" | grep "sojourn" | awk '{print $2}' | tr -d 'ms' | head -n1)

DROPS=${DROPS:-0}
BACKLOG_BYTES=${BACKLOG_BYTES:-0}
BACKLOG_PKTS=${BACKLOG_PKTS:-0}
SOJOURN_MS=${SOJOURN_MS:-0.0}

# Connection Flows & System Load
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
# STEP 3: Gather Wireless Profiles
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
        SIGNAL_DBM=$(echo "$IW_INFO" | grep "signal:" | awk '{print $2}' | tr -cd '0-9.-')
        NOISE_DBM=$(echo "$IW_INFO" | grep "signal avg:" | awk '{print $3}' | tr -cd '0-9.-')
        TX_BITRATE=$(echo "$IW_INFO" | grep "tx bitrate:" | awk '{print $3}' | tr -cd '0-9.-')
        RX_BITRATE=$(echo "$IW_INFO" | grep "rx bitrate:" | awk '{print $3}' | tr -cd '0-9.-')
        EXPECTED_THROUGHPUT=$(echo "$IW_INFO" | grep "expected throughput:" | awk '{print $3}' | tr -cd '0-9.-')
    fi
fi

# =====================================================================
# STEP 4: Construct and Transmit Phase 1 JSON Payload
# =====================================================================
ROUTER_ID=$(cat /sys/class/net/$WAN_IFACE/address 2>/dev/null | tr -d ':')
if [ -z "$ROUTER_ID" ]; then
    ROUTER_ID=$(uci get system.@system[0].hostname 2>/dev/null || echo "unknown-router")
fi

RUN_ID="run_$(date +%s)_$$"

cat <<EOF > /tmp/payload.json
{
  "run_id": "$RUN_ID",
  "router_id": "$ROUTER_ID",
  "timestamp": $(date +%s),
  "uptime_seconds": ${UPTIME_SEC:-0},
  "system_load": "${LOAD_AVG:-0.00}",
  "interface": {
    "name": "$WAN_IFACE",
    "type": "${IFACE_TYPE:-wan}",
    "rx_bytes": ${RX_BYTES:-0},
    "tx_bytes": ${TX_BYTES:-0},
    "rx_packets": ${RX_PACKETS:-0},
    "tx_packets": ${TX_PACKETS:-0},
    "rx_errors": ${RX_ERRORS:-0},
    "tx_errors": ${TX_ERRORS:-0}
  },
  "wireless_profile": {
    "signal_strength_dbm": ${SIGNAL_DBM:-0},
    "noise_floor_dbm": ${NOISE_DBM:-0},
    "tx_bitrate_mbps": ${TX_BITRATE:-0.0},
    "rx_bitrate_mbps": ${RX_BITRATE:-0.0},
    "expected_throughput_mbps": ${EXPECTED_THROUGHPUT:-0.0}
  },
  "latency_profile": {
    "ping_target": "8.8.8.8",
    "avg_latency_ms": ${LATENCY_AVG:-0.0},
    "packet_loss_percent": ${PACKET_LOSS:-0},
    "sojourn_ms": ${SOJOURN_MS:-0.0},
    "drops": ${DROPS:-0},
    "backlog_bytes":${BACKLOG_BYTES:-0},
    "backlog_pkts":${BACKLOG_PKTS:-0}
  },
  "active_flows": {
    "total_tracked":${TOTAL_FLOWS:-0},
    "tcp_established":${TCP_ESTABLISHED:-0}
  }
}
EOF
FILE_PATH="/tmp/payload.json"
echo "$(cat "$FILE_PATH")"

RESPONSE=$(curl -X POST -H 'Content-Type:application/json' -d @/tmp/payload.json  "$SERVER_URL")

echo "$RESPONSE"
echo "$SERVER_URL"

# =====================================================================
# STEP 5: Parse & Execute QoS Directives
# =====================================================================
# if [ -n "$RESPONSE" ]; then
    # QOS_ENABLED=$(echo "$RESPONSE" | jsonfilter -e '@.qos_enabled' 2>/dev/null)
    # DOWN_LIMIT=$(echo "$RESPONSE" | jsonfilter -e '@.download_limit' 2>/dev/null)
    # UP_LIMIT=$(echo "$RESPONSE" | jsonfilter -e '@.upload_limit' 2>/dev/null)
    # QDISC_ALGO=$(echo "$RESPONSE" | jsonfilter -e '@.qdisc_algo' 2>/dev/null)
    # CHANGES_MADE=0
    # [ -f /etc/config/sqm ] || touch /etc/config/sqm

    # # Ensure base configuration section exists
    # uci get sqm.wan >/dev/null 2>&1 || uci set sqm.wan=queue

    # if [ -n "$QOS_ENABLED" ]; then
        # uci set sqm.wan.enabled="$QOS_ENABLED"
        # CHANGES_MADE=1
    # fi

    # if [ -n "$DOWN_LIMIT" ]; then
        # uci set sqm.wan.download="$DOWN_LIMIT"
        # CHANGES_MADE=1
    # fi

    # if [ -n "$UP_LIMIT" ]; then
        # uci set sqm.wan.upload="$UP_LIMIT"
        # CHANGES_MADE=1
    # fi

    # if [ -n "$QDISC_ALGO" ]; then
        # uci set sqm.wan.qdisc="$QDISC_ALGO"
        # CHANGES_MADE=1
    # fi

    # CURRENT_SQM_IFACE=$(uci get sqm.wan.interface 2>/dev/null)
    # if [ "$CURRENT_SQM_IFACE" != "$WAN_IFACE" ]; then
        # uci set sqm.wan.interface="$WAN_IFACE"
        # CHANGES_MADE=1
    # fi

    # if [ "$CHANGES_MADE" -eq 1 ]; then
        # uci commit sqm
        # /etc/init.d/sqm restart >/dev/null 2>&1
        # logger -t qos_telemetry "Updated SQM settings on $WAN_IFACE"
    # fi
# fi
# sleep 15
# =====================================================================
# STEP 6: Phase 3 Confirmation (State AFTER Execution)
# =====================================================================
# Sleep 3 seconds to allow queue state stabilization under new parameters
sleep 3

PING_CONFIRM=$(ping -c 1 -W 1 8.8.8.8 2>&1)
if [ $? -eq 0 ]; then
    LATENCY_AFTER=$(echo "$PING_CONFIRM" | awk -F 'time=' '{print $2}' | awk '{print $1}')
else
    LATENCY_AFTER=0.0
fi

TC_CONFIRM=$(tc -s qdisc show dev $WAN_IFACE 2>/dev/null)
SOJOURN_AFTER=$(echo "$TC_CONFIRM" | grep "sojourn" | awk '{print $2}' | tr -d 'ms' | head -n1)
DROPS_AFTER=$(echo "$TC_CONFIRM" | grep "dropped" | awk '{print $7}' | tr -d ',' | head -n1)

#cat <<EOF > /tmp/confirm_payload.json
#{
#  "run_id": "$RUN_ID",
#  "router_id": "$ROUTER_ID",
#  "timestamp": $(date +%s),
#  "state_after": {
#    "avg_latency_ms": ${LATENCY_AFTER:-0.0},
#    "sojourn_ms": ${SOJOURN_AFTER:-0.0},
#    "drops": ${DROPS_AFTER:-0}
#  }
#}
#EOF

#curl -X POST -H 'Content-Type:application/json' -d @/tmp/confirm_payload.json "$CONFIRM_URL" >/dev/null 2>&1 &

# 1. Gather Connected Clients Count
CONNECTED_CLIENTS=$(hostapd_cli all_sta 2>/dev/null | grep -c "^[0-9a-fA-F]\{2\}:")
CONNECTED_CLIENTS=${CONNECTED_CLIENTS:-0}

# 2. Build Clean JSON Payload
cat <<EOF > /tmp/confirm_payload.json
{
  "run_id": "$RUN_ID",
  "router_id": "$ROUTER_ID",
  "timestamp": $(date +%s),
  "state_after": {
    "avg_latency_ms":${LATENCY_AFTER:-0.0},
    "sojourn_ms": ${SOJOURN_AFTER:-0.0},
    "drops": ${DROPS_AFTER:-0},
    "connected_users": ${CONNECTED_CLIENTS}
  }
}
EOF

# 3. Post Confirmation & Output Response
CONFIRM_URL="https://sovereign-brain-owrv.onrender.com/api/telemetry/confirm"
RESPONSE=$(curl -s -X POST -H 'Content-Type: application/json' -d @/tmp/confirm_payload.json "$CONFIRM_URL")

echo "Phase 3 Response: $RESPONSE"
