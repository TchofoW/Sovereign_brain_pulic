import os
import json
import numpy as np
import psycopg2
from datetime import datetime
from typing import Tuple
from config import settings
from core.telemetry_store import EnrichedContextMatrix


class Tier3MLEngine:
    # PostgreSQL config
    _db_host = os.getenv("POSTGRES_HOST", "dpg-daul4pp42hec73et8rjg-a.ohio-postgres.render.com")
    _db_port = int(os.getenv("POSTGRES_PORT", "5432"))
    _db_name = os.getenv("POSTGRES_DB", "brain_db_81ky")
    _db_user = os.getenv("POSTGRES_USER", "william")
    _db_password = os.getenv("POSTGRES_PASSWORD", "QPXAaSDcKFFiEIuH9071hpGZ4DHBrc5O")

    @classmethod
    def get_db_connection(cls):
        return psycopg2.connect(
            host=cls._db_host,
            port=cls._db_port,
            dbname=cls._db_name,
            user=cls._db_user,
            password=cls._db_password,
            sslmode="require"
        )


    @staticmethod
    def get_environmental_state_index(matrix: EnrichedContextMatrix) -> int:
        """
        Maps continuous network telemetry into one of 24 discrete state buckets.
        3 (latency) * 2 (drops) * 4 (flows) = 24 states.
        """
        # 1. Latency tier (0 to 2)
        lat = matrix.latency_ms
        lat_idx = 0 if lat < 30 else (1 if lat < 60 else 2)
        
        # 2. Drop state (0 to 1)
        drop_idx = 0 if matrix.drops == 0 else 1
        
        # 3. Flow/Client load tier (0 to 3)
        flows = matrix.total_flows
        flow_idx = 0 if flows < 10 else (1 if flows < 50 else (2 if flows < 150 else 3))
        
        # Combine into a unique integer index from 0 to 23
        state_idx = (lat_idx * 8) + (drop_idx * 4) + flow_idx
        return min(state_idx, 23)  # Safety bounds check to stay within 0-23

    @classmethod
    def ensure_table(cls):
        conn = cls.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ml_state (
                router_id VARCHAR(255) PRIMARY KEY,
                q_table JSONB NOT NULL,
                last_state INTEGER,
                last_action_idx INTEGER,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        cursor.close()
        conn.close()

    STEERING_MULTIPLIERS = [0.80, 0.85, 0.90, 0.95, 1.00]

    @classmethod
    async def optimize_and_learn(cls, matrix: EnrichedContextMatrix, fuzzy_scalar: float) -> Tuple[float, str]:
        """
        Ingests EnrichedContextMatrix, updates the Q-matrix using PostgreSQL storage,
        and selects optimal link-shaping multipliers and Qdisc parameters.
        """
        cls.ensure_table()

        device_id = matrix.router_id
        active_time_bucket = cls.get_environmental_state_index(matrix)

        conn = cls.get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT q_table, last_state, last_action_idx
            FROM ml_state
            WHERE router_id = %s
        """, (device_id,))

        row = cursor.fetchone()

        if row:
            q_table = np.array(row[0], dtype=float)
            last_state = row[1]
            last_action_idx = row[2]
        else:
            q_table = np.zeros((24, len(cls.STEERING_MULTIPLIERS)))
            last_state = None
            last_action_idx = None

        if last_state is not None and last_action_idx is not None:
            effective_delay = max(matrix.latency_ms, matrix.sojourn_ms)
            reward_value = (
                -(effective_delay * 1.2)
                - (matrix.packet_loss * 15.0)
                - (float(matrix.drops) * 2.5)
                + (matrix.calc_download_mbps * 2.0)
            )

            current_q_val = q_table[last_state, last_action_idx]
            max_future_q = np.max(q_table[active_time_bucket])

            learning_rate = getattr(settings, "LEARNING_RATE", 0.1)
            discount_factor = getattr(settings, "DISCOUNT_FACTOR", 0.9)

            q_table[last_state, last_action_idx] = current_q_val + learning_rate * (
                reward_value + (discount_factor * max_future_q) - current_q_val
            )

        exploration_rate = getattr(settings, "EXPLORATION_RATE", 0.1)
        if np.random.rand() < exploration_rate:
            selected_action_index = int(np.random.choice(len(cls.STEERING_MULTIPLIERS)))
        else:
            selected_action_index = int(np.argmax(q_table[active_time_bucket]))

        selected_alpha_multiplier = cls.STEERING_MULTIPLIERS[selected_action_index]

        cursor.execute("""
            INSERT INTO ml_state (
                router_id,
                q_table,
                last_state,
                last_action_idx,
                updated_at
            )
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (router_id) DO UPDATE SET
                q_table = EXCLUDED.q_table,
                last_state = EXCLUDED.last_state,
                last_action_idx = EXCLUDED.last_action_idx,
                updated_at = CURRENT_TIMESTAMP
        """, (
            device_id,
            json.dumps(q_table.tolist()),
            active_time_bucket,
            selected_action_index
        ))

        conn.commit()
        cursor.close()
        conn.close()

        if matrix.total_flows > 300 or matrix.is_wireless or matrix.drops > 0:
            recommended_qdisc = "cake"
        else:
            recommended_qdisc = "fq_codel"

        return selected_alpha_multiplier, recommended_qdisc
