import os
from pydantic import Field
from pydantic_settings import BaseSettings

# =====================================================================
# OBSERVABILITY
# =====================================================================
LOG_LEVEL: str = "INFO"
LOG_FILE: str = "/var/log/router_optim_cloud.log"
LOG_GUARDRAIL_EVENTS: bool = True
LOG_FUZZY_OUTPUTS: bool = True       # ← the missing one
LOG_ML_DECISIONS: bool = True
TELEMETRY_RETENTION_HOURS: int = Field(24, gt=0)


class Settings(BaseSettings):
    # =====================================================================
    # 1. PHYSICAL INFRASTRUCTURE BOUNDARIES (Match to your true ISP plan)
    # =====================================================================
    # Hard capabilities of your physical connection line (values in Kbps)
    MAX_ISP_DOWNLOAD_KBPS: int = int(os.getenv("MAX_ISP_DOWNLOAD_KBPS", 100000))  # 100 Mbps
    MAX_ISP_UPLOAD_KBPS: int = int(os.getenv("MAX_ISP_UPLOAD_KBPS", 20000))      # 20 Mbps

    # Default fallback scheduling algorithm for OpenWrt SQM
    DEFAULT_QDISC_ALGO: str = "cake"

    # =====================================================================
    # 2. TIER 1: SAFETY REFLEX BOUNDARIES (Hard Thresholds)
    # =====================================================================
    CRITICAL_LATENCY_MS: float = 120.0   # Beyond this, bufferbloat mitigation triggers
    CRITICAL_PACKET_LOSS: float = 5.0   # Drop limit before emergency throttle triggers
    CRITICAL_SYSTEM_LOAD: float = 1.2    # Overload ceiling for a typical dual-core router
    CRITICAL_SOJOURN_MS: float = 200.0  # Kernel AQM queue delay threshold

    # Safe-mode emergency drop factor (e.g., clamp to 30% of max capacity)
    EMERGENCY_SCALAR: float = 0.30

    # =====================================================================
    # 3. TIER 3: REINFORCEMENT LEARNING HYPERPARAMETERS
    # =====================================================================

    # Wireless RSSI scaling brackets (dBm)
    RSSI_WEAK_THRESHOLD: int = -75
    RSSI_MODERATE_THRESHOLD: int = -65

    LEARNING_RATE: float = 0.1
    DISCOUNT_FACTOR: float = 0.9
    EXPLORATION_RATE: float = 0.15        # Epsilon-greedy exploration boundary

    class Config:
        env_file = ".env"

# Instantiate global settings object for structural imports across tiers
settings = Settings()
