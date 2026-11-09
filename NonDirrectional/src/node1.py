import simpy

from common import Config, Frame
from application import ApplicationLayer
from network import NetworkLayer
from mac import MacLayer


class PhysicalLayer:
    """Физический уровень узла: передатчик и приемник"""

    def __init__(self, node, channel):
        self.node = node
        self.channel = channel
        self.tx_busy_until = 0.0
        self.rx_busy_until = 0.0

    @property
    def transmiting(self):
        return self.node.env.now < self.tx_busy_until

    @property
    def receiving(self):
        return self.node.env.now < self.rx_busy_until

    def start_transmission(self, frame: Frame, duration: float) -> None:
        if self.receiving:
            raise RuntimeError(
                f"{self.node.node_id} попытка передать, пока принимаю, "
                f"t={self.node.env.now:.4f}"
            )        
        self.tx_busy_until = self.node.env.now + duration

    def transmit(self, frame: Frame):
        """Инициировать передачу кадра в канал. Возвращает генератор."""
        return self.channel.transmit(self.node, frame)

    def receive_signal(self, sender, frame: Frame, duration: float):
        """Принять сигнал. Генератор: длится duration секунд."""
        if self.transmiting:
            self.node.log(f"PHY: drop {frame.kind.name}, from={sender.node_id} (transmiting)")
            return

        # Простейшая детекция коллизий
        if self.receiving:
            self.node.log(f"PHY: collision/drop {frame.kind.name} from={sender.node_id}")
            return
        
        self.rx_busy_until = self.node.env.now + duration
        yield self.node.env.timeout(duration)
        self.rx_busy_until = 0.0 # обнуляем
        self.node.on_frame_received(sender, frame)


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
        print(f'[{self.env.now: 8.4f} s] [{self.node_id}] {message}')

    def on_frame_received(self, sender, frame: Frame) -> None:
        self.mac.on_frame_received(frame)