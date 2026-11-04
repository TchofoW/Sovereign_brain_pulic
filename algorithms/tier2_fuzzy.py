import logging
import numpy as np
from config import settings
from core.telemetry_store import EnrichedContextMatrix

logger = logging.getLogger(__name__)


class Tier2FuzzyController:

    @staticmethod
    def _tri_membership(x: float, a: float, b: float, c: float) -> float:
        """Standard Triangular Membership Function."""
        if x <= a or x >= c:
            return 0.0
        if a < x <= b:
            return (x - a) / (b - a)
        if b < x < c:
            return (c - x) / (c - b)
        return 0.0

    @staticmethod
    def _trap_membership(x: float, a: float, b: float, c: float, d: float) -> float:
        """Standard Trapezoidal Membership Function."""
        if x <= a or x >= d:
            return 0.0
        if b <= x <= c:
            return 1.0
        if a < x < b:
            return (x - a) / (b - a)
        if c < x < d:
            return (d - x) / (d - c)
        return 0.0

    @classmethod
    def evaluate_link_scalar(cls, matrix: EnrichedContextMatrix) -> float:
        """
        Ingests the telemetry metrics and maps them through overlapping sets.
        Returns a link capacity scalar factor (alpha) between 0.1 and 1.0.
        """
        effective_delay = max(matrix.latency_ms, matrix.sojourn_ms)

        if not matrix.is_wireless:
            return cls._evaluate_wired_congestion(
                effective_delay, matrix.packet_loss, matrix.drops
            )

        # -----------------------------------------------------------------
        # FUZZIFICATION LAYER
        # -----------------------------------------------------------------
        sig = matrix.signal_dbm
        sig_poor = cls._trap_membership(sig, -110, -110, -85, -70)
        sig_fair = cls._tri_membership(sig, -85, -70, -55)
        sig_good = cls._trap_membership(sig, -70, -55, 10, 10)

        lat = matrix.latency_ms
        lat_low = cls._trap_membership(lat, 0, 0, 25, 50)
        lat_med = cls._tri_membership(lat, 25, 60, 100)
        lat_high = cls._trap_membership(lat, 75, 120, 5000, 5000)

        loss_high = cls._trap_membership(matrix.packet_loss, 2.0, 5.0, 100.0, 100.0)
        has_drops = 1.0 if matrix.drops > 0 else 0.0

        # -----------------------------------------------------------------
        # RULE INFERENCE LAYER (Mamdani-Style Matrix)
        # -----------------------------------------------------------------
        # Severe: any single critical condition, OR combinations of
        # moderate conditions, OR packet drops
        out_severe = max(
            sig_poor,
            lat_high,
            loss_high,
            min(sig_poor, lat_med),
            min(sig_fair, lat_high),
            has_drops * 0.8,
        )
        out_moderate = max(min(sig_fair, lat_med), min(sig_good, lat_med))
        out_optimal = min(sig_good, lat_low, 1.0 - has_drops)

        total_weight = out_severe + out_moderate + out_optimal
        if total_weight == 0:
            alpha = 1.0
            logger.debug("Fuzzy: no rule fired (default alpha=1.0)")
            return alpha

        # -----------------------------------------------------------------
        
        # -----------------------------------------------------------------
        # -----------------------------------------------------------------
        # DEFUZZIFICATION (Sugeno-style weighted average)
        # -----------------------------------------------------------------
        alpha = (
            (out_severe * 0.4) + (out_moderate * 0.75) + (out_optimal * 1.0)
        ) / total_weight

        if getattr(settings, "LOG_FUZZY_OUTPUTS", False):
            logger.debug(
                "Fuzzy: rssi=%.1f lat=%.1f loss=%.2f drops=%d → alpha=%.3f "
                "(severe=%.2f mod=%.2f opt=%.2f)",
                matrix.signal_dbm, matrix.latency_ms, matrix.packet_loss,
                matrix.drops, alpha, out_severe, out_moderate, out_optimal,
            )
        return round(float(alpha), 3)

    @classmethod
    def _evaluate_wired_congestion(cls, delay_ms: float, loss_percent: float, drops: int) -> float:
        """
        Fuzzy scaling for fixed-line connections.

        NOTE: Wired output floor is 0.5 (vs. 0.4 for wireless) because wired
        congestion is typically bufferbloat-related and recoverable;
        aggressive throttling risks under-utilizing a stable physical link.
        """
        bloat = cls._trap_membership(delay_ms, 30, 70, 120, 500)
        loss_factor = cls._trap_membership(loss_percent, 1.0, 3.0, 100.0, 100.0)
        drop_penalty = 0.1 if drops > 0 else 0.0

        combined_degradation = min(1.0, max(bloat, loss_factor) + drop_penalty)
        return round(1.0 - (combined_degradation * 0.5), 3)
