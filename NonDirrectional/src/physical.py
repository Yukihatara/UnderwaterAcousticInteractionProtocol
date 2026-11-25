import simpy

from common import Config, Frame


class _RxState:
    """Состояние одного активного приёма."""
    __slots__ = ('sender', 'frame', 'angle', 'end_time', 'collided')

    def __init__(self, sender, frame, angle, end_time):
        self.sender = sender
        self.frame = frame
        self.angle = angle
        self.end_time = end_time
        self.collided = False


class PhysicalLayer:
    """Полудуплексный PHY с угловым разрешением приёма.

    Одновременный приём нескольких сигналов разрешён, если угол
    между направлениями на источники ≥ angular_resolution (22.5°).
    Иначе — коллизия: оба сигнала теряются.
    """

    def __init__(self, node, channel):
        self.node = node
        self.channel = channel
        self.tx_busy_until = 0.0
        self._active_rx = []          # список _RxState
        self._reserved = 0

        self._free_event = self.node.env.event()
        self._free_event.succeed()

    # ---------- свойства занятости ----------

    @property
    def config(self):
        return self.node.config

    @property
    def env(self):
        return self.node.env

    @property
    def transmitting(self):
        return self.node.env.now < self.tx_busy_until

    @property
    def receiving(self):
        return len(self._active_rx) > 0

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
        while self.busy:
            if self._free_event.triggered:
                self._free_event = self.node.env.event()
            yield self._free_event

    # ---------- передача ----------

    def start_transmission(self, frame: Frame, duration: float) -> None:
        if self.receiving:
            raise RuntimeError(
                f"{self.node.node_id}: попытка передать во время приёма, "
                f"t={self.node.env.now:.4f}"
            )
        self.tx_busy_until = self.node.env.now + duration + self.node.config.sifs
        self.node.env.process(self._tx_done(duration))

    def _tx_done(self, duration: float):
        yield self.node.env.timeout(duration + self.node.config.sifs)
        self.tx_busy_until = 0.0
        self._release()

    def transmit(self, frame: Frame):
        return self.channel.transmit(self.node, frame)

    # ---------- приём с угловым разрешением ----------

    def receive_signal(self, sender, frame: Frame, duration: float):
        if self.transmitting:
            if frame.destination == self.node.node_id:
                self.node.log(
                    f"PHY: drop {frame.kind.name} from {sender.node_id} (transmitting)"
                )
            return

        angle = self.node.known_neighbors.bearing_to(sender.node_id)
        new_rx = _RxState(sender, frame, angle, self.node.env.now + duration)

        # поиск коллизии
        collided_with = None
        sep = None
        for active in self._active_rx:
            sep = sep = self.node.known_neighbors.angular_separation(angle, active.angle)
            if sep < self.config.angular_resolution:
                collided_with = active
                break

        if collided_with is not None:
            collided_with.collided = True
            new_rx.collided = True
            self.node.log(
                f"PHY: COLLISION {frame.kind.name} from {sender.node_id} "
                f"with {collided_with.sender.node_id} "
                f"(Δangle={sep:.2f}° < {self.config.angular_resolution:.1f}°)"
            )
        else:
            self.node.log(
                f"PHY: receive {frame.kind.name} from {sender.node_id} "
                f"(angle={angle:.1f}°, active={len(self._active_rx)})"
            )

        self._active_rx.append(new_rx)
        self.reserve_rx()
        yield self.node.env.timeout(duration)
        self._active_rx.remove(new_rx)
        self._release()

        if new_rx.collided:
            self.node.log(
                f"PHY: DROP {frame.kind.name} from {sender.node_id} "
                f"(collision during reception)"
            )
            return
        self.node.on_frame_received(sender, frame)