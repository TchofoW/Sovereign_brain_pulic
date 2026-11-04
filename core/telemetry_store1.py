import time
from typing import Dict, Optional, Any
from pydantic import BaseModel

class RouterStateHistorical(BaseModel):
    """Data structure representing the last known state metrics of an active node."""
    timestamp: int
    rx_bytes: int
    tx_bytes: int

class EnrichedContextMatrix(BaseModel):
    """Calculated metrics handed down to the optimization Tiers."""
    router_id: str
    is_wireless: bool
    calc_download_mbps: float
    calc_upload_mbps: float
    latency_ms: float
    packet_loss: float
    signal_dbm: int
    noise_dbm: int
    system_load: float
    total_flows: int

class TelemetryStore:
    def __init__(self):
        # Local in-memory high-speed storage engine indexed by unique hardware MACs
        self._memory: Dict[str, RouterStateHistorical] = {}

    async def update_and_calculate_deltas(self, raw_telemetry: Any) -> EnrichedContextMatrix:
        """
        Ingests raw Pydantic JSON structures, evaluates delta variations against
        the node's historical records, and compiles the dynamic context matrix.
        """
        rid = raw_telemetry.router_id
        current_time = raw_telemetry.timestamp
        current_rx = raw_telemetry.interface.rx_bytes
        current_tx = raw_telemetry.interface.tx_bytes

        # Establish fallbacks for baseline initialization loops
        calc_down_mbps = 0.0
        calc_up_mbps = 0.0

        if rid in self._memory:
            prev_state = self._memory[rid]
            
            # Compute time window variance delta (Δt)
            delta_time = float(current_time - prev_state.timestamp)

            # Defensive handling for unexpected concurrent payloads or clock drift
            if delta_time > 0.01:
                # Delta computations for raw counter differences
                delta_rx_bytes = max(0, current_rx - prev_state.rx_bytes)
                delta_tx_bytes = max(0, current_tx - prev_state.tx_bytes)

                # Mathematical translation: (Bytes -> Bits -> Megabits) / time delta
                calc_down_mbps = round(((delta_rx_bytes * 8) / 1_000_000.0) / delta_time, 3)
                calc_up_mbps = round(((delta_tx_bytes * 8) / 1_000_000.0) / delta_time, 3)

        # Update persistent tracking engine coordinates for the next cycle
        self._memory[rid] = RouterStateHistorical(
            timestamp=current_time,
            rx_bytes=current_rx,
            tx_bytes=current_tx
        )

        # Build and output the fully unified metric payload matrix
        return EnrichedContextMatrix(
            router_id=rid,
            is_wireless=True if raw_telemetry.interface.type == "wireless" else False,
            calc_download_mbps=calc_down_mbps,
            calc_upload_mbps=calc_up_mbps,
            latency_ms=float(raw_telemetry.latency_profile.avg_latency_ms),
            packet_loss=float(raw_telemetry.latency_profile.packet_loss_percent),
            signal_dbm=int(raw_telemetry.wireless_profile.signal_strength_dbm),
            noise_dbm=int(raw_telemetry.wireless_profile.noise_floor_dbm),
            system_load=float(raw_telemetry.system_load),
            total_flows=int(raw_telemetry.active_flows.total_tracked)
        )

# Initialize global tracking instance for ingestion layer dependency injection
global_telemetry_store = TelemetryStore()
