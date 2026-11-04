import os
import json
import psycopg2
from typing import Optional, Any
from pydantic import BaseModel
from config import settings

class EnrichedContextMatrix(BaseModel):
    """Calculated metrics handed down to the optimization Tiers."""
    router_id: str
    run_id: str
    timestamp: int
    active_tier: str = "tier3_rl"  # Tagged dynamically by execution pipeline
    is_wireless: bool
    calc_download_mbps: float
    calc_upload_mbps: float
    latency_ms: float
    sojourn_ms: float              # Kernel AQM Queue Delay
    packet_loss: float
    drops: int                     # Packet drop counter
    backlog_bytes: int             # Queue backlog in bytes
    backlog_pkts: int              # Queue backlog in packets
    signal_dbm: int
    noise_dbm: int
    system_load: float
    total_flows: int

class PostgresTelemetryStore:
    def __init__(self):
        # PostgreSQL configuration
        self.db_host = os.getenv("POSTGRES_HOST", "dpg-daul4pp42hec73et8rjg-a.ohio-postgres.render.com")
        self.db_port = int(os.getenv("POSTGRES_PORT", "5432"))
        self.db_name = os.getenv("POSTGRES_DB", "brain_db_81ky")
        self.db_user = os.getenv("POSTGRES_USER", "william")
        self.db_password = os.getenv("POSTGRES_PASSWORD", "QPXAaSDcKFFiEIuH9071hpGZ4DHBrc5O")

    def get_connection(self):
        """Create and return a PostgreSQL connection."""
        return psycopg2.connect(
            host=self.db_host,
            port=self.db_port,
            dbname=self.db_name,
            user=self.db_user,
            password=self.db_password,
            sslmode="require"
        )

    def ensure_table(self):
        """Ensure router_state table exists."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS router_state (
                router_id VARCHAR(255) PRIMARY KEY,
                timestamp BIGINT,
                rx_bytes BIGINT,
                tx_bytes BIGINT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        cursor.close()
        conn.close()

    async def update_and_calculate_deltas(self, raw_telemetry: Any) -> EnrichedContextMatrix:
        """
        Ingests raw telemetry, evaluates delta variations against persistent records 
        inside PostgreSQL, and compiles the multi-tenant context matrix.
        """
        self.ensure_table()

        rid = raw_telemetry.router_id
        current_time = raw_telemetry.timestamp
        current_rx = raw_telemetry.interface.rx_bytes
        current_tx = raw_telemetry.interface.tx_bytes

        calc_down_mbps = 0.0
        calc_up_mbps = 0.0

        conn = self.get_connection()
        cursor = conn.cursor()

        # Fetch the previous historical state from PostgreSQL
        cursor.execute("""
            SELECT timestamp, rx_bytes, tx_bytes
            FROM router_state
            WHERE router_id = %s
        """, (rid,))

        result = cursor.fetchone()

        if result:
            prev_timestamp, prev_rx_bytes, prev_tx_bytes = result

            # Compute time window variance delta (Δt)
            delta_time = float(current_time - prev_timestamp)

            if delta_time > 0.01:
                delta_rx_bytes = max(0, current_rx - prev_rx_bytes)
                delta_tx_bytes = max(0, current_tx - prev_tx_bytes)

                # Mathematical translation: (Bytes -> Bits -> Megabits) / time delta
                calc_down_mbps = round(((delta_rx_bytes * 8) / 1_000_000.0) / delta_time, 3)
                calc_up_mbps = round(((delta_tx_bytes * 8) / 1_000_000.0) / delta_time, 3)

        # Upsert the new state snapshot
        cursor.execute("""
            INSERT INTO router_state (router_id, timestamp, rx_bytes, tx_bytes, updated_at)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (router_id) DO UPDATE SET
                timestamp = EXCLUDED.timestamp,
                rx_bytes = EXCLUDED.rx_bytes,
                tx_bytes = EXCLUDED.tx_bytes,
                updated_at = CURRENT_TIMESTAMP
        """, (rid, current_time, current_rx, current_tx))

        conn.commit()
        cursor.close()
        conn.close()

        # Safely parse system load string or float
        try:
            raw_load = str(raw_telemetry.system_load).strip().split()[0]
            parsed_load = float(raw_load)
        except (ValueError, IndexError):
            parsed_load = 0.0

        return EnrichedContextMatrix(
            router_id=rid,
            run_id=getattr(raw_telemetry, "run_id", "legacy_run"),
            timestamp=raw_telemetry.timestamp,
            is_wireless=True if raw_telemetry.interface.type == "wireless" else False,
            calc_download_mbps=calc_down_mbps,
            calc_upload_mbps=calc_up_mbps,
            latency_ms=float(raw_telemetry.latency_profile.avg_latency_ms),
            sojourn_ms=float(getattr(raw_telemetry.latency_profile, "sojourn_ms", 0.0)),
            packet_loss=float(raw_telemetry.latency_profile.packet_loss_percent),
            drops=int(getattr(raw_telemetry.latency_profile, "drops", 0)),
            backlog_bytes=int(getattr(raw_telemetry.latency_profile, "backlog_bytes", 0)),
            backlog_pkts=int(getattr(raw_telemetry.latency_profile, "backlog_pkts", 0)),
            signal_dbm=int(raw_telemetry.wireless_profile.signal_strength_dbm),
            noise_dbm=int(raw_telemetry.wireless_profile.noise_floor_dbm),
            system_load=parsed_load,
            total_flows=int(raw_telemetry.active_flows.total_tracked)
        )

# Global tracking instance for ingestion layer dependency injection
global_telemetry_store = PostgresTelemetryStore()
