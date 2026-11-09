import simpy
from termcolor import colored

from common import Config, Frame
from application import ApplicationLayer
from network import NetworkLayer
from mac3 import MacLayer
from physical3 import PhysicalLayer

class Node:
    def __init__(self, env: simpy.Environment, node_id: str, channel, topology, config: Config):
        self.env = env
        self.node_id = node_id
        self.config = config
        self.topology = topology

        self.color_print = self.set_color_print()

        # Уровни (слои)
        self.channel = channel
        self.phy = PhysicalLayer(self, channel)
        self.mac = MacLayer(self)
        self.network = NetworkLayer(self)
        self.application = ApplicationLayer(self)
        
        channel.register(self)

    def log(self, message: str) -> None:
        print(colored(f'[{self.env.now:8.4f} s] [{self.node_id}] {message}', self.color_print))

    def on_frame_received(self, sender, frame: Frame) -> None:
        self.mac.on_frame_received(frame)

    def set_color_print(self):
        if self.node_id == 'A': return 'red'
        if self.node_id == 'B': return 'blue'
        if self.node_id == 'C': return 'green'
        if self.node_id == 'D': return 'brown'
        if self.node_id == 'E': return 'yellow'