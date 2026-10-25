import simpy

from common import Frame, Config


class AcousticChannel:
    "Общая акустическая среда. Умеет доставлять кадр от одного узла всем остальным"

    def __init__(self, env: simpy.Environment, config: Config):
        self.env = env
        self.config = config
        self.nodes = {}

    def register(self, node) -> None:
        self.nodes[node.node_id] = node

    def transmit(self, sender, frame: Frame):
        duration = self.config.tx_duration(frame.bits)
        propagation = self.config.propagation_delay

        sender.phy.start_transmission(frame, duration)

        for node in self.nodes.values():
            if node.node_id == sender.node_id:
                continue
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