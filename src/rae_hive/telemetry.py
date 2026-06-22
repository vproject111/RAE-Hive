from rae_core.models.cost import CostVector
from rae_core.models.evidence import OutcomeRecord

class HiveTelemetry:
    """Handles resource consumption reporting for Hive executions."""
    
    @staticmethod
    def record_action_outcome(action_id: str, success: bool, duration_s: float, tokens: int) -> OutcomeRecord:
        return OutcomeRecord(
            action_id=action_id,
            result="success" if success else "failure",
            cost_vector=CostVector(
                wall_time_s=duration_s,
                output_tokens=tokens
            )
        )
