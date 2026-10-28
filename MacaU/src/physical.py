import simpy

from common import Config, Frame
from application import ApplicationLayer
from network import NetworkLayer
from mac import MacLayer


class PhysicalLayer:
    """Физический уровень узла: передатчик и приемник."""

    def __init__(self, node, channel):
        self.node = node
        self.channel = channel
        self.tx_busy_until = 0.0
        self.rx_busy_until = 0.0

        # Счётчик "зарезервированных" операций (tx и rx).
        # >0 значит: либо идёт tx/rx, либо MAC решил начать передачу,
        # но transmit ещё не стартовал (окно между reserve_tx и start_transmission).
        self._reserved = 0

        # Событие "phy свободна". Взведено, когда _reserved == 0 и нет tx/rx.
        self._free_event = self.node.env.event()
        self._free_event.succeed()

    # ---------- свойства занятости ----------

    @property
    def transmiting(self):
        return self.node.env.now < self.tx_busy_until

    @property
    def receiving(self):
        return self.node.env.now < self.rx_busy_until

    @property
    def busy(self):
        return self._reserved > 0 or self.transmiting or self.receiving

    # ---------- управление _free_event ----------

    def _reserve(self):
        """Синхронно пометить phy занятой. Гасит _free_event немедленно."""
        self._reserved += 1
        if self._free_event.triggered:
            self._free_event = self.node.env.event()

    def _release(self):
        """Вызывается, когда одна из операций (tx/rx) завершилась."""
        if self._reserved > 0:
            self._reserved -= 1
        if (self._reserved == 0
                and not self.transmiting
                and not self.receiving
                and not self._free_event.triggered):
            self._free_event.succeed()

    def reserve_tx(self):
        """MAC вызывает синхронно перед transmit(...), чтобы закрыть окно
        между 'решили передать' и фактическим стартом передачи."""
        self._reserve()

    def reserve_rx(self):
        self._reserve()

    def wait_free(self):
        """Генератор: дождаться, пока phy станет свободной.

        Если уже свободна — не блокируемся.
        """
        while self.busy:
            if self._free_event.triggered:
                # Событие взвели, но busy успел стать True — пересоздаём.
                self._free_event = self.node.env.event()
            yield self._free_event

    # ---------- передача / приём ----------

    def start_transmission(self, frame: Frame, duration: float) -> None:
        if self.receiving:
            raise RuntimeError(
                f"{self.node.node_id} попытка передать, пока принимаю, "
                f"t={self.node.env.now:.4f}"
            )
        self.tx_busy_until = self.node.env.now + duration
        # _reserved уже увеличен вызовом reserve_tx().
        self.node.env.process(self._tx_done(duration))

    def _tx_done(self, duration: float):
        yield self.node.env.timeout(duration)
        self.tx_busy_until = 0.0
        self._release()

    def transmit(self, frame: Frame):
        """Инициировать передачу кадра в канал. Возвращает генератор."""
        return self.channel.transmit(self.node, frame)

    def receive_signal(self, sender, frame: Frame, duration: float):
        """Принять сигнал. Генератор: длится duration секунд."""
        if self.transmiting:
            self.node.log(f"PHY: drop {frame.kind.name}, from={sender.node_id} (transmiting)")
            return

        # Простейшая детекция коллизий: при коллизии кадр теряется.
        if self.receiving:
            self.node.log(f"PHY: collision/drop {frame.kind.name} from={sender.node_id}")
            return

        self.reserve_rx()
        self.rx_busy_until = self.node.env.now + duration
        yield self.node.env.timeout(duration)
        self.rx_busy_until = 0.0
        self._release()
        self.node.on_frame_received(sender, frame)