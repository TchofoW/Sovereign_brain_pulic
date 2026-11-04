import json
import os
import time
import psycopg2
from fastapi import FastAPI, HTTPException,status
from pydantic import BaseModel, Field

from config import settings
from core.telemetry_store import global_telemetry_store, EnrichedContextMatrix
from core.pipeline import ExecutionPipeline

# Initialize FastAPI app
app = FastAPI(
    title="Sovereign Brain API Core",
    description="High-Performance Tiered Control Plane & Closed-Loop Telemetry Ingestion",
    version="2.0.0"
)

# PostgreSQL configuration
_DB_HOST = os.getenv("POSTGRES_HOST", "dpg-daul4pp42hec73et8rjg-a.ohio-postgres.render.com")
_DB_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
_DB_NAME = os.getenv("POSTGRES_DB", "brain_db_81ky")
_DB_USER = os.getenv("POSTGRES_USER", "william")
_DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "QPXAaSDcKFFiEIuH9071hpGZ4DHBrc5O")

def get_db_connection():
    """Create and return a PostgreSQL database connection."""
    return psycopg2.connect(
        host=_DB_HOST,
        port=_DB_PORT,
        dbname=_DB_NAME,
        user=_DB_USER,
        password=_DB_PASSWORD,
        sslmode="require"
    )

def init_db():
    """Initialize database schema for telemetry storage."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            run_id VARCHAR(255) PRIMARY KEY,
            router_id VARCHAR(255) NOT NULL,
            timestamp_phase1 BIGINT,
            timestamp_phase3 BIGINT,
            tier VARCHAR(50),
            state_before JSONB,
            state_after JSONB,
            command_sent JSONB,
            recovery_time_ms BIGINT,
            reward_score FLOAT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_runs_router_id ON runs(router_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_runs_timestamp_phase1 ON runs(timestamp_phase1)
    """)

    conn.commit()
    cursor.close()
    conn.close()
    print("[INIT] PostgreSQL schema initialized successfully")

# Initialize database on startup
init_db()

# =====================================================================
# PYDANTIC INBOUND SCHEMAS (Phase 1 & Phase 3)
# =====================================================================

@app.head("/", status_code=status.HTTP_200_OK)
@app.get("/")
async def root():
    """Root endpoint for Render health checks."""
    return {
        "service": "Sovereign Brain API Core",
        "status": "online",
        "version": "2.0.0"
    }

class InterfaceMetrics(BaseModel):
    name: str
    type: str
    rx_bytes: int
    tx_bytes: int
    rx_packets: int
    tx_packets: int
    rx_errors: int
    tx_errors: int

class WirelessProfile(BaseModel):
    signal_strength_dbm: int
    noise_floor_dbm: int
    tx_bitrate_mbps: float
    rx_bitrate_mbps: float
    expected_throughput_mbps: float

class LatencyProfile(BaseModel):
    ping_target: str
    avg_latency_ms: float
    packet_loss_percent: float
    sojourn_ms: float = 0.0
    drops: int = 0
    backlog_bytes: int = 0
    backlog_pkts: int = 0

class ActiveFlows(BaseModel):
    total_tracked: int
    tcp_established: int

class RouterTelemetryPayload(BaseModel):
    """Phase 1 Payload: Initial state BEFORE QoS parameter adjustments."""
    run_id: str = Field(..., description="Unique transaction ID for this iteration")
    router_id: str = Field(..., description="The unique MAC or hostname of the router")
    timestamp: int
    uptime_seconds: int
    system_load: str
    interface: InterfaceMetrics
    wireless_profile: WirelessProfile
    latency_profile: LatencyProfile
    active_flows: ActiveFlows

class StateAfterMetrics(BaseModel):
    avg_latency_ms: float
    sojourn_ms: float
    drops: int
    connected_users: int = 0

class ConfirmationPayload(BaseModel):
    """Phase 3 Payload: Post-execution state AFTER QoS parameter adjustments."""
    run_id: str
    router_id: str
    timestamp: int
    state_after: StateAfterMetrics

class QoSCommandPacket(BaseModel):
    """Outbound command packet returned synchronously to the router client."""
    qos_enabled: str
    download_limit: str
    upload_limit: str
    qdisc_algo: str

# =====================================================================
# API ENDPOINT DEFINITIONS
# =====================================================================

@app.head("/", status_code=status.HTTP_200_OK)
@app.get("/health")
async def health_check():
    """Verify server and PostgreSQL connection status."""
    db_status = "offline"
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        db_status = "online"
    except Exception:
        db_status = "offline"

    monitored_nodes = 0
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(DISTINCT router_id) FROM runs")
        result = cursor.fetchone()
        if result:
            monitored_nodes = result[0] or 0
        cursor.close()
        conn.close()
    except Exception:
        monitored_nodes = 0

    return {
        "status": "online",
        "database_status": db_status,
        "monitored_nodes_active": monitored_nodes
    }

@app.post("/api/telemetry", response_model=QoSCommandPacket)
async def ingest_router_telemetry(payload: RouterTelemetryPayload):
    """
    PHASE 1 INGESTION:
    Accepts State BEFORE metrics, calculates deltas, evaluates Tiers 1-3,
    writes State BEFORE + Commands to PostgreSQL, and returns parameters to router.
    """
    try:
        context_matrix: EnrichedContextMatrix = await global_telemetry_store.update_and_calculate_deltas(payload)
        target_commands = await ExecutionPipeline.process(context_matrix)

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO runs (
                run_id,
                router_id,
                timestamp_phase1,
                tier,
                state_before,
                command_sent
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_id) DO UPDATE SET
                timestamp_phase1 = EXCLUDED.timestamp_phase1,
                tier = EXCLUDED.tier,
                state_before = EXCLUDED.state_before,
                command_sent = EXCLUDED.command_sent,
                updated_at = CURRENT_TIMESTAMP
        """, (
            payload.run_id,
            payload.router_id,
            payload.timestamp,
            getattr(context_matrix, "active_tier", "tier2_fuzzy"),
            json.dumps(payload.dict()),
            json.dumps(target_commands)
        ))

        conn.commit()
        cursor.close()
        conn.close()

        print(f"[{payload.router_id}] Phase 1 Logged -> Run: {payload.run_id} | RTT: {payload.latency_profile.avg_latency_ms}ms")

        return QoSCommandPacket(
            qos_enabled=str(target_commands["qos_enabled"]),
            download_limit=str(target_commands["download_limit"]),
            upload_limit=str(target_commands["upload_limit"]),
            qdisc_algo=str(target_commands["qdisc_algo"])
        )

    except Exception as e:
        import traceback
        print("----CRITICAL SERVER ERROR (PHASE 1)----")
        traceback.print_exc()
        print("--------------------------------------")
        raise HTTPException(status_code=500, detail=f"Phase 1 Ingestion Error: {str(e)}")

@app.post("/api/telemetry/confirm")
async def ingest_confirmation_telemetry(payload: ConfirmationPayload):
    """
    PHASE 3 INGESTION:
    Accepts State AFTER execution metrics, updates PostgreSQL run record, and
    calculates derived metrics (Recovery Time and RL Reward Score).
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT timestamp_phase1, state_before
            FROM runs
            WHERE run_id = %s
        """, (payload.run_id,))

        result = cursor.fetchone()

        if not result:
            print(f"Warning: Phase 3 received without Phase 1 record for Run: {payload.run_id}")
            rec_time_ms = 0
            reward_score = 0.0
        else:
            ts_phase1, state_before_raw = result
            rec_time_ms = 0
            if ts_phase1:
                rec_time_ms = (payload.timestamp - int(ts_phase1)) * 1000

            reward_score = 0.0
            if state_before_raw:
                if isinstance(state_before_raw, dict):
                    state_before = state_before_raw
                else:
                    state_before = json.loads(state_before_raw)
                
                rtt_before = state_before.get("latency_profile", {}).get("avg_latency_ms", 0.0)
                rtt_after = payload.state_after.avg_latency_ms
                rtt_delta = rtt_before - rtt_after
                reward_score = round((rtt_delta * 2.0) - (payload.state_after.drops * 1.5), 2)

        cursor.execute("""
            UPDATE runs SET
                timestamp_phase3 = %s,
                state_after = %s,
                recovery_time_ms = %s,
                reward_score = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE run_id = %s
        """, (
            payload.timestamp,
            json.dumps(payload.state_after.dict()),
            rec_time_ms,
            reward_score,
            payload.run_id
        ))

        conn.commit()
        cursor.close()
        conn.close()

        print(f"[{payload.router_id}] Phase 3 Logged -> Run: {payload.run_id} | RTT After: {payload.state_after.avg_latency_ms}ms | RecTime: {rec_time_ms}ms")

        return {
            "status": "SUCCESS",
            "run_id": payload.run_id,
            "recovery_time_ms": rec_time_ms,
            "reward_score": reward_score
        }

    except Exception as e:
        import traceback
        print("----CRITICAL SERVER ERROR (PHASE 3)----")
        traceback.print_exc()
        print("--------------------------------------")
        raise HTTPException(status_code=500, detail=f"Phase 3 Confirmation Error: {str(e)}")
