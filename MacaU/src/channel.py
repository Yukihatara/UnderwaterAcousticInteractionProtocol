import simpy

from common import Frame, Config
from topology import Topology

class AcousticChannel:
    "Общая акустическая среда. Умеет доставлять кадр от одного узла всем остальным"

    def __init__(self, env: simpy.Environment, config: Config, topology: Topology):
        self.env = env
        self.config = config
        self.topology = topology

        self.nodes = {}

    def register(self, node) -> None:
        self.nodes[node.node_id] = node

    def transmit(self, sender, frame: Frame):
        duration = self.config.tx_duration(frame.bits)

        sender.phy.start_transmission(frame, duration)

        for node in self.nodes.values():
            if node.node_id == sender.node_id:
                continue
            if not self.topology.can_hear(sender.node_id, node.node_id):
                continue
            propagation = self.topology.propagation_delay(
                sender.node_id, node.node_id
            )
            self.env.process(
                self._deliver(node, sender, frame, propagation, duration)
            )

        # Сам tramsin длится, пока передатчиик излучает.
        yield self.env.timeout(duration)

    def _deliver(self, receiver, sender, frame, propagation, duration):
        # Сигнал идет по воде propagation секунд.
        yield self.env.timeout(propagation)
        # Приемник "принимает" сигнал длительностью duration.
        yield from receiver.phy.receive_signal(sender, frame, duration)