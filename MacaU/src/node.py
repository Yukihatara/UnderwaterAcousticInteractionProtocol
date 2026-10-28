import simpy

from common import Config, Frame
from application import ApplicationLayer
from network import NetworkLayer
from mac import MacLayer
from physical import PhysicalLayer

class Node:
    def __init__(self, env: simpy.Environment, node_id: str, channel, config: Config):
        self.env = env
        self.node_id = node_id
        self.config = config

        # Уровни (слои)
        self.channel = channel
        self.phy = PhysicalLayer(self, channel)
        self.mac = MacLayer(self)
        self.network = NetworkLayer(self)
        self.application = ApplicationLayer(self)

        channel.register(self)

    def log(self, message: str) -> None:
        print(f'[{self.env.now:8.4f} s] [{self.node_id}] {message}')

    def on_frame_received(self, sender, frame: Frame) -> None:
        self.mac.on_frame_received(frame)