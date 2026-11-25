import simpy
from termcolor import colored

from common import Config, Frame
from application import ApplicationLayer
from network import NetworkLayer
from mac import MacLayer
from physical import PhysicalLayer
from knowledge import NodeKnowledge


class Node:
    def __init__(self, env: simpy.Environment, node_id: str, channel,
                 topology, config: Config, mac_class=None):
        self.env = env
        self.node_id = node_id
        self.config = config

        # «Физический мир» — используется channel.py. Логике узла сюда нельзя.
        self.topology = topology

        # «Знание узла о мире» — всё, что нужно MAC/PHY/app.
        self.known_neighbors = NodeKnowledge(self, topology)

        self.color_print = self.set_color_print()

        self.channel = channel
        self.phy = PhysicalLayer(self, channel)
        mac_cls = mac_class or MacLayer
        self.mac = mac_cls(self)
        self.network = NetworkLayer(self)
        self.application = ApplicationLayer(self)

        channel.register(self)

    def log(self, message: str) -> None:
        print(colored(f'[{self.env.now:8.4f} s] [{self.node_id}] {message}',
                      self.color_print))

    def on_frame_received(self, sender, frame: Frame) -> None:
        self.mac.on_frame_received(frame)


    def set_color_print(self):
        if self.node_id == 'A': return 'green'
        if self.node_id == 'B': return 'green'
        if self.node_id == 'C': return 'green'
        if self.node_id == 'D': return 'green'
        if self.node_id == 'E': return 'red'