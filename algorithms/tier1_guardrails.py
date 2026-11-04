import os
from typing import Tuple, Optional, Dict
from config import settings
from core.telemetry_store import EnrichedContextMatrix

class Tier1Guardrails:
    @staticmethod
    def evaluate(matrix: EnrichedContextMatrix) -> Tuple[bool, Optional[Dict[str, str]]]:
        """
        Evaluates the current network matrix against strict survival criteria.
        Returns:
            (True, override_commands) -> If a safety intervention is triggered.
            (False, None)            -> If the link status is green and clear.
        """
        # --- RULE CATASTROPHE 1: TOTAL OUTAGE DETECTION ---
        if matrix.packet_loss >= 100.0:
            print(f"[GUARDRAIL TRIGGERED] Outage detected on Node {matrix.router_id}. Forcing emergency safe-mode.")
            return True, {
                "qos_enabled": "1",
                "download_limit": str(int(settings.MAX_ISP_DOWNLOAD_KBPS * settings.EMERGENCY_SCALAR)),
                "upload_limit": str(int(settings.MAX_ISP_UPLOAD_KBPS * settings.EMERGENCY_SCALAR)),
                "qdisc_algo": "cake"  # Force robust AQM scheduling to handle link degradation
            }

        # --- RULE CATASTROPHE 2: CRITICAL CONGESTION / BUFFERBLOAT SPIKE ---
        # Checks both end-to-end ping delay AND active kernel queue delay (sojourn_ms)
        # to ensure wireless RF noise doesn't trigger a false positive emergency clamp.
        is_true_bufferbloat = (
            matrix.latency_ms >= settings.CRITICAL_LATENCY_MS and 
            matrix.sojourn_ms >= settings.CRITICAL_SOJOURN_MS
        )

        if is_true_bufferbloat:
            print(
                f"[GUARDRAIL TRIGGERED] Severe bufferbloat on Node {matrix.router_id} "
                f"(RTT: {matrix.latency_ms}ms, Sojourn: {matrix.sojourn_ms}ms). Clamping pipes."
            )
            return True, {
                "qos_enabled": "1",
                # Aggressively choke traffic by the emergency factor to force the queue to drain instantly
                "download_limit": str(int(settings.MAX_ISP_DOWNLOAD_KBPS * settings.EMERGENCY_SCALAR)),
                "upload_limit": str(int(settings.MAX_ISP_UPLOAD_KBPS * settings.EMERGENCY_SCALAR)),
                "qdisc_algo": "cake"
            }

        # --- RULE CATASTROPHE 3: LOCAL PROCESSOR OVERLOAD ---
        if matrix.system_load >= settings.CRITICAL_SYSTEM_LOAD:
            print(f"[GUARDRAIL TRIGGERED] Node {matrix.router_id} CPU is buckling under load ({matrix.system_load}). Disabling complex SQM processing.")
            return True, {
                "qos_enabled": "0",  # Shutting off SQM entirely reduces router CPU consumption instantly
                "download_limit": "0",
                "upload_limit": "0",
                "qdisc_algo": settings.DEFAULT_QDISC_ALGO
            }

        # No critical rules broken. Pass control down safely to Tier 2.
        return False, None
