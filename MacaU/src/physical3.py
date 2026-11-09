import simpy

from common import Config, Frame


class PhysicalLayer:
    """Физический уровень узла: полудуплексный передатчик/приёмник.

    Атрибуты занятости:
      tx_busy_until — до какого момента узел излучает;
      rx_busy_until — до какого момента узел принимает;
      _reserved     — счётчик зарезервированных операций (tx или rx),
                      включая окно между reserve_tx() и start_transmission().
    """

    def __init__(self, node, channel):
        self.node = node
        self.channel = channel
        self.tx_busy_until = 0.0
        self.rx_busy_until = 0.0
        self._reserved = 0

        self._free_event = self.node.env.event()
        self._free_event.succeed()

    # ---------- свойства занятости ----------

    @property
    def transmitting(self):
        return self.node.env.now < self.tx_busy_until

    @property
    def receiving(self):
        return self.node.env.now < self.rx_busy_until

    @property
    def busy(self):
        return self._reserved > 0 or self.transmitting or self.receiving

    # ---------- резервирование ----------

    def _reserve(self):
        self._reserved += 1
        if self._free_event.triggered:
            self._free_event = self.node.env.event()

    def _release(self):
        if self._reserved > 0:
            self._reserved -= 1
        if (self._reserved == 0
                and not self.transmitting
                and not self.receiving
                and not self._free_event.triggered):
            self._free_event.succeed()

    def reserve_tx(self):
        self._reserve()

    def reserve_rx(self):
        self._reserve()

    def wait_free(self):
        """Дождаться, пока PHY освободится (генератор)."""
        while self.busy:
            if self._free_event.triggered:
                self._free_event = self.node.env.event()
            yield self._free_event

    # ---------- передача / приём ----------

    def start_transmission(self, frame: Frame, duration: float) -> None:
        if self.receiving:
            raise RuntimeError(
                f"{self.node.node_id}: попытка передать во время приёма, "
                f"t={self.node.env.now:.4f}"
            )
        self.tx_busy_until = self.node.env.now + duration
        self.node.env.process(self._tx_done(duration))

    def _tx_done(self, duration: float):
        yield self.node.env.timeout(duration)
        self.tx_busy_until = 0.0
        self._release()

    def transmit(self, frame: Frame):
        """Инициировать передачу в канал. Возвращает генератор."""
        return self.channel.transmit(self.node, frame)

    def receive_signal(self, sender, frame: Frame, duration: float):
        """Принять сигнал. Генератор: длится duration секунд."""
        if self.transmitting:
            self.node.log(f"PHY: drop {frame.kind.name} from {sender.node_id} (transmitting)")
            return
        if self.receiving:
            self.node.log(f"PHY: collision {frame.kind.name} from {sender.node_id}")
            return

        self.reserve_rx()
        self.rx_busy_until = self.node.env.now + duration
        yield self.node.env.timeout(duration)
        self.rx_busy_until = 0.0
        self._release()
        self.node.on_frame_received(sender, frame)