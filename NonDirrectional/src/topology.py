import math

from common import Config


class Topology:
    """Координаты узлов на плоскости, расстояния и слышимость."""

    def __init__(self, config: Config):
        self.config = config
        self.positions = {}   # node_id -> (x, y)

    # ---------- инициализация ----------

    def set_position(self, node_id: str, x: float, y: float) -> None:
        self.positions[node_id] = (float(x), float(y))

    def get_position(self, node_id: str) -> tuple[float, float]:
        return self.positions[node_id]

    # ---------- геометрия ----------

    def get_distance(self, a: str, b: str) -> float:
        if a == b:
            return 0.0
        xa, ya = self.positions[a]
        xb, yb = self.positions[b]
        return math.hypot(xb - xa, yb - ya)

    def can_hear(self, a: str, b: str) -> bool:
        """Слышит ли b передачу a. Симметрично."""
        if a == b:
            return False
        return self.get_distance(a, b) <= self.config.max_range

    def propagation_delay(self, a: str, b: str) -> float:
        return self.get_distance(a, b) / self.config.sound_speed