import numpy as np
from datetime import datetime
from typing import Dict, Tuple
from sovereign_brain.config import settings
from sovereign_brain.core.telemetry_store import EnrichedContextMatrix

class RouterQLearningModel:
    """An isolated Reinforcement Learning instance unique to a specific physical router."""
    def __init__(self):
        # State space: 24 Hours of the day
        # Action space: 5 discrete scaling multipliers -> [0.8, 0.85, 0.9, 0.95, 1.0]
        self.actions = [0.80, 0.85, 0.90, 0.95, 1.00]
        self.q_table = np.zeros((24, len(self.actions)))
        self.last_state: Optional[int] = None
        self.last_action_idx: Optional[int] = None

    def get_state(self, timestamp: int) -> int:
        """Translates the epoch timestamp into a discrete hour state (0-23)."""
        return datetime.fromtimestamp(timestamp).hour

class Tier3MLEngine:
    # Memory cache holding isolated ML models for each unique MAC address
    _fleet_models: Dict[str, RouterQLearningModel] = {}

    @classmethod
    def _get_or_create_model(cls, router_id: str) -> RouterQLearningModel:
        if router_id not in cls._fleet_models:
            cls._fleet_models[router_id] = RouterQLearningModel()
        return cls._fleet_models[router_id]

    @classmethod
    def optimize_and_learn(cls, matrix: EnrichedContextMatrix, fuzzy_scalar: float) -> Tuple[float, str]:
        """
        Executes the RL learning loop based on previous performance results,
        then returns an optimized modifier scalar and the ideal qdisc flavor.
        """
        model = cls._get_or_create_model(matrix.router_id)
        current_state = model.get_state(matrix.timestamp)

        # -----------------------------------------------------------------
        # STEP 1: EXECUTE THE LEARNING REWARD UPDATE LOOP
        # -----------------------------------------------------------------
        if model.last_state is not None and model.last_action_idx is not None:
            # Mathematical Reward Function: Reward throughput, heavily penalize bloat/loss
            reward = -(matrix.latency_ms) - (matrix.packet_loss * 15.0) + (matrix.calc_download_mbps * 2.0)

            # Temporal Difference Q-Learning formula update
            old_value = model.q_table[model.last_state, model.last_action_idx]
            next_max = np.max(model.q_table[current_state])
            
            # Learn and adjust weights for this hour slot
            model.q_table[model.last_state, model.last_action_idx] = old_value + settings.LEARNING_RATE * (
                reward + settings.DISCOUNT_FACTOR * next_max - old_value
            )

        # -----------------------------------------------------------------
        # STEP 2: ACTION SELECTION (Epsilon-Greedy Policy)
        # -----------------------------------------------------------------
        if np.random.rand() < settings.EXPLORATION_RATE:
            # Explore: pick a random scaling factor to test network limits
            action_idx = np.random.choice(len(model.actions))
        else:
            # Exploit: pick the best proven mathematical choice for this hour
            action_idx = np.argmax(model.q_table[current_state])

        chosen_ml_multiplier = model.actions[action_idx]

        # Save historical coordinates for evaluation on the next check-in interval
        model.last_state = current_state
        model.last_action_idx = action_idx

        # -----------------------------------------------------------------
        # STEP 3: CLASSIFY IDEAL QUEUE DISCIPLINE (qdisc) FLAVOR
        # -----------------------------------------------------------------
        # If the network handles heavily active, parallel traffic streams, mandate CAKE.
        # If it is a quiet, low-flow link, use standard fq_codel to minimize minor overhead.
        chosen_qdisc = "cake" if matrix.total_flows > 300 or matrix.is_wireless else "fq_codel"

        return chosen_ml_multiplier, chosen_qdisc
