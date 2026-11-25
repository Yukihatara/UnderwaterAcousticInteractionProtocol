import math

from common import Config


class Topology:
    def __init__(self, config: Config):
        self.config = config
        self.positions = {}

    def set_position(self, node_id: str, x: float, y: float) -> None:
        self.positions[node_id] = (float(x), float(y))

    def get_position(self, node_id: str) -> tuple[float, float]:
        return self.positions[node_id]

    def get_distance(self, a: str, b: str) -> float:
        if a == b:
            return 0.0
        xa, ya = self.positions[a]
        xb, yb = self.positions[b]
        return math.hypot(xb - xa, yb - ya)

    def bearing(self, from_node: str, to_node: str) -> float:
        """Абсолютное направление (в градусах) из from_node на to_node."""
        if from_node == to_node:
            return 0.0
        x1, y1 = self.positions[from_node]
        x2, y2 = self.positions[to_node]
        return math.degrees(math.atan2(y2 - y1, x2 - x1))

    @staticmethod
    def angular_separation(a1: float, a2: float) -> float:
        """Минимальный угол между двумя направлениями, [0, 180]."""
        d = abs(a1 - a2) % 360.0
        return min(d, 360.0 - d)

    def can_hear(self, a: str, b: str) -> bool:
        if a == b:
            return False
        return self.get_distance(a, b) <= self.config.max_range

    def propagation_delay(self, a: str, b: str) -> float:
        return self.get_distance(a, b) / self.config.sound_speed