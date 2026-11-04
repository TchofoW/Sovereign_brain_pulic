# core/pipeline.py

from typing import Dict
from config import settings
from core.telemetry_store import EnrichedContextMatrix
from algorithms.tier1_guardrails import Tier1Guardrails
from algorithms.tier2_fuzzy import Tier2FuzzyController
from algorithms.tier3_ml import Tier3MLEngine

class ExecutionPipeline:
    @staticmethod
    async def process(matrix: EnrichedContextMatrix) -> Dict[str, str]:
        """
        Manages execution sequentially through all 3 tiers of intelligence.
        Combines deterministic reflexes, fuzzy sets, and RL predictions.
        """
        # =====================================================================
        # RUN TIER 1: CRITICAL GUARDRAILS (The Reflex Gateway)
        # =====================================================================
        # Checks for CPU overload, severe loss, AND true bufferbloat (latency + sojourn)
        triggered, override_commands = Tier1Guardrails.evaluate(matrix)
        if triggered and override_commands is not None:
            matrix.active_tier = "tier1_guardrail"
            return override_commands

        # =====================================================================
        # RUN TIER 2: FUZZY LOGIC CONTROLLER (Real-Time Adaption Engine)
        # =====================================================================
        # Evaluates RSSI signal degradation and delay trends to return a scalar (0.0 to 1.0)
        fuzzy_scalar = Tier2FuzzyController.evaluate_link_scalar(matrix)

        # =====================================================================
        # RUN TIER 3: REINFORCEMENT LEARNING ENGINE (Predictive Evolution)
        # =====================================================================
        # Evaluates multi-day optimal state policy
        ml_multiplier, dynamic_qdisc = await Tier3MLEngine.optimize_and_learn(matrix, fuzzy_scalar)

        # -----------------------------------------------------------------
        # FINAL MATHEMATICAL AGGREGATION & TIER TAGGING
        # -----------------------------------------------------------------
        # Set active tier tag for Redis Phase 1 tracking based on which engine dominated
        if matrix.is_wireless and matrix.signal_dbm < settings.RSSI_MODERATE_THRESHOLD:
            matrix.active_tier = "tier2_fuzzy"
        else:
            matrix.active_tier = "tier3_rl"

        # Blend the real-time link scalar with long-term predictive scalar factors
        final_scalar = fuzzy_scalar * ml_multiplier

        target_download = int(settings.MAX_ISP_DOWNLOAD_KBPS * final_scalar)
        target_upload = int(settings.MAX_ISP_UPLOAD_KBPS * final_scalar)

        # Enforce strict safety boundaries to prevent choking down to zero limits
        target_download = max(target_download, int(settings.MAX_ISP_DOWNLOAD_KBPS * 0.15))
        target_upload = max(target_upload, int(settings.MAX_ISP_UPLOAD_KBPS * 0.15))

        print(f"[PIPELINE OVERVIEW] Node: {matrix.router_id} | Active Tier: {matrix.active_tier} | "
              f"Fuzzy: {fuzzy_scalar} * ML: {ml_multiplier} -> Combined: {round(final_scalar, 3)} | "
              f"Selected QDisc: {dynamic_qdisc}")

        return {
            "qos_enabled": "1",
            "download_limit": str(target_download),
            "upload_limit": str(target_upload),
            "qdisc_algo": dynamic_qdisc
        }
