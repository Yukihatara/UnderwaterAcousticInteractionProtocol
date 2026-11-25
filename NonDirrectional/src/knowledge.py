import math

from topology import Topology


class NodeKnowledge:
    """Представление узла о соседях и геометрии вокруг себя.

    Сейчас — тонкая обёртка над глобальной Topology (полная связность,
    все узлы «знают» друг о друге с самого начала). В будущем здесь
    будет накапливаться информация, полученная из служебных кадров.
    """

    def __init__(self, node, topology: Topology):
        self.node = node
        self.topology = topology

    # -------- кто вообще известен --------

    def knows(self, other_id: str) -> bool:
        return other_id in self.topology.positions

    def neighbors(self) -> list[str]:
        return [nid for nid in self.topology.positions
                if nid != self.node.node_id]

    # -------- геометрия «от меня» --------

    def distance_from(self, a_id: str, b_id: str) -> float:
        return self.topology.get_distance(a_id, b_id)

    def distance_to(self, other_id: str) -> float:
        return self.topology.get_distance(self.node.node_id, other_id)

    def bearing_to(self, other_id: str) -> float:
        """Направление (в градусах) от меня на other_id."""
        return self.topology.bearing(self.node.node_id, other_id)

    def propagation_delay_to(self, other_id: str) -> float:
        return self.topology.propagation_delay(self.node.node_id, other_id)

    def can_hear(self, other_id: str) -> bool:
        return self.topology.can_hear(self.node.node_id, other_id)

    def can_hear_between(self, a_id: str, b_id: str) -> bool:
        """Может ли a_id слышать b_id (по текущему знанию)."""
        return self.topology.can_hear(a_id, b_id)
    # -------- утилиты --------

    @staticmethod
    def angular_separation(a1: float, a2: float) -> float:
        return Topology.angular_separation(a1, a2)