from common import Config


class Topology:
    """Таблица расстояний между узлами и проверка слышимости."""

    def __init__(self, config: Config):
        self.config = config
        self.distances = {}   # (a, b) -> distance (симметрично)

    def set_distance(self, a: str, b: str, distance: float) -> None:
        self.distances[(a, b)] = distance
        self.distances[(b, a)] = distance

    def get_distance(self, a: str, b: str) -> float:
        if a == b:
            return 0.0
        return self.distances[(a, b)]

    def can_hear(self, a: str, b: str) -> bool:
        """Слышит ли b передачу a. Симметрично."""
        if a == b:
            return False
        return self.get_distance(a, b) <= self.config.max_range

    def propagation_delay(self, a: str, b: str) -> float:
        return self.get_distance(a, b) / self.config.sound_speed