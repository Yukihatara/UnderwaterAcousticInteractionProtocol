import random

from common import Frame, FrameType

EPS = 1e-6


class MacLayer:
    """Упрощённая MACA для подводной сети.

    Полный цикл обмена (RTS → CTS → DATA → ACK) начинается в двух случаях:

      (а) из очереди — как отправитель;
      (б) по приходу RTS — как получатель.

    Условия старта (одинаковые для обоих случаев):
      1) state == IDLE,
      2) PHY свободна (не передаю, не принимаю, ничего не зарезервировано),
      3) now >= nav_until (NAV истёк).

    Состояния:
      IDLE    — свободен;
      WFCTS   — отправил RTS, жду CTS;
      WFDATA  — получил RTS, ответил CTS, жду DATA;
      WFACK   — отправил DATA, жду ACK.
    """

    IDLE = 'IDLE'
    WFCTS = 'WFCTS'
    WFDATA = 'WFDATA'
    WFACK = 'WFACK'

    def __init__(self, node):
        self.node = node
        self.state = self.IDLE
        self.nav_until = 0.0

        self.retry = 0
        self.max_retries = 3

        self._queue = []
        self._sender_running = False

        # События текущего обмена
        self._idle_event = self.env.event()
        self._idle_event.succeed()
        self._cts_event = None
        self._ack_event = None
        self._abort_event = None

    @property
    def env(self):
        return self.node.env

    @property
    def config(self):
        return self.node.config

    # ==================== Состояние и условия старта ====================

    def _set_idle(self):
        self.state = self.IDLE
        if not self._idle_event.triggered:
            self._idle_event.succeed()

    def _wait_idle(self):
        if self.state != self.IDLE:
            self._idle_event = self.env.event()
            yield self._idle_event

    def _abort_current(self):
        """Прервать текущий обмен (используется, когда в WFCTS слышим чужой кадр)."""
        if self._abort_event is not None and not self._abort_event.triggered: 
            self._abort_event.succeed()

    def _wait_until_can_transmit(self):
        """Дождаться выполнения ВСЕХ условий старта обмена."""
        while True:
            if self.state != self.IDLE:
                yield from self._wait_idle()
                continue
            if self.node.phy.busy:
                yield from self.node.phy.wait_free()
                continue
            if self.env.now < self.nav_until:
                wait = self.nav_until - self.env.now
                self.node.log(f"MAC: wait NAV {wait:.3f} s")
                yield self.env.timeout(wait)
                continue
            return

    # ==================== Публичный API ====================

    def send_data(self, destination, sequence, payload):
        """Поставить пакет в очередь. Возвращает Event доставки."""
        done = self.env.event()
        self._queue.append((destination, sequence, payload, done))
        if not self._sender_running:
            self._sender_running = True
            self.env.process(self._sender_loop())
        return done

    # ==================== Send ====================

    def _sender_loop(self):
        """Берёт пакеты из очереди и гоняет их через полный обмен."""
        while self._queue:
            destination, sequence, payload, done = self._queue.pop(0)
            result = yield from self._do_exchange(destination, sequence, payload)

            if result is None:
                # Обмен прерван (NAV) — вернуть пакет в начало очереди.
                self._queue.insert(0, (destination, sequence, payload, done))
            else:
                done.succeed(value=result)

        self._sender_running = False

    def _do_exchange(self, destination, sequence, payload):
        """Полный обмен с ретраями. Возвращает True / False / None (аборт)."""
        self.retry = 0

        while True:
            yield from self._wait_until_can_transmit()

            phase = yield from self._send_rts(destination, sequence)

            if phase == 'abort':
                self._set_idle()
                return None

            if phase == 'cts':
                phase = yield from self._send_data(destination, sequence, payload)
                if phase == 'ack':
                    self.node.log(f"MAC: delivered seq={sequence} -> {destination}")
                    self._set_idle()
                    return True

            # Таймаут CTS или ACK — ретрай либо сдаться
            self._set_idle()
            self.retry += 1
            if self.retry > self.max_retries:
                self.node.log(f"MAC: gave up after {self.retry} attempts")
                return False
            yield from self._backoff()

    def _send_rts(self, destination, sequence):
        """Отправить RTS и дождаться CTS. Возвращает 'cts' | 'timeout' | 'abort'."""
        prop = self.node.topology.propagation_delay(self.node.node_id, destination)
        nav_duration = (
            self.config.tx_duration(self.config.cts_bits)
            + self.config.tx_duration(self.config.data_bits)
            + self.config.tx_duration(self.config.ack_bits)
            + 3 * prop
            + EPS
        )

        self.state = self.WFCTS
        self._cts_event = self.env.event()
        self._abort_event = self.env.event()
        self.node.phy.reserve_tx()

        rts = Frame(
            kind=FrameType.RTS,
            source=self.node.node_id,
            destination=destination,
            bits=self.config.rts_bits,
            sequence=sequence,
            duration=nav_duration,
        )
        self.node.log(f"MAC: send RTS -> {destination} (seq={sequence})")
        yield from self.node.phy.transmit(rts)

        t_wait = (
            self.config.tx_duration(self.config.rts_bits)
            + 2 * prop
            + self.config.tx_duration(self.config.cts_bits)
            + EPS
        )
        result = yield self._cts_event | self._abort_event | self.env.timeout(t_wait)

        if self._abort_event in result:
            self.node.log(f"MAC: aborted waiting CTS from {destination}")
            return 'abort'
        if self._cts_event in result:
            self.node.log(f"MAC: recv CTS from {destination}")
            return 'cts'
        self.node.log(f"MAC: timeout CTS (retry={self.retry})")
        return 'timeout'

    def _send_data(self, destination, sequence, payload):
        """Отправить DATA и дождаться ACK. Возвращает 'ack' | 'timeout'."""
        prop = self.node.topology.propagation_delay(self.node.node_id, destination)

        self.state = self.WFACK
        self._ack_event = self.env.event()
        self.node.phy.reserve_tx()

        data = Frame(
            kind=FrameType.DATA,
            source=self.node.node_id,
            destination=destination,
            bits=self.config.data_bits,
            sequence=sequence,
            payload=payload,
        )
        self.node.log(f"MAC: send DATA -> {destination} (seq={sequence})")
        yield from self.node.phy.transmit(data)

        t_wait = (
            self.config.tx_duration(self.config.data_bits)
            + 2 * prop
            + self.config.tx_duration(self.config.ack_bits)
            + EPS
        )
        result = yield self._ack_event | self.env.timeout(t_wait)

        if self._ack_event in result:
            self.node.log(f"MAC: recv ACK from {destination} (seq={sequence})")
            return 'ack'
        self.node.log(f"MAC: timeout ACK (retry={self.retry})")
        return 'timeout'

    def _backoff(self):
        wait = random.uniform(0, self.config.backoff * (2 ** (self.retry - 1)))
        self.node.log(f"MAC: backoff {wait:.3f} s")
        yield self.env.timeout(wait)

    # ==================== Receive ====================

    def on_frame_received(self, frame: Frame):
        # (1) Чужой кадр — NAV и, возможно, аборт.
        if frame.destination != self.node.node_id:
            # NAV обновляем только в IDLE и WFCTS.
            # В WFDATA/WFACK мы уже в активном обмене — NAV для нас бесполезен,
            # он влияет только на СЛЕДУЮЩУЮ передачу, а мы сейчас не свободны.
            if (frame.kind in (FrameType.RTS, FrameType.CTS)
                    and frame.duration > 0
                    and self.state in (self.IDLE, self.WFCTS)):
                new_nav = self.env.now + frame.duration
                if new_nav > self.nav_until:
                    self.node.log(
                        f"MAC: NAV {self.nav_until:.4f} -> {new_nav:.4f} "
                        f"(by {frame.kind.name} from {frame.source})"
                    )
                    self.nav_until = new_nav

            # Аборт: только в WFCTS, только по чужому RTS/CTS.
            if (self.state == self.WFCTS
                    and frame.kind in (FrameType.RTS, FrameType.CTS)):
                self.node.log(
                    f"MAC: heard foreign {frame.kind.name} from {frame.source}, aborting"
                )
                self._abort_current()
            return

        # (2) Кадр мне, но NAV активен — игнорируем (кроме ACK).
        # ACK не вмешивается в эфир — можно принять, даже если NAV активен.
        if self.env.now < self.nav_until:
            if frame.kind is FrameType.ACK:
                self._on_ack(frame)
            else:
                self.node.log(
                    f"MAC: ignore {frame.kind.name} from {frame.source} "
                    f"(NAV until {self.nav_until:.4f})"
                )
            return

        # (3) Нормальная диспетчеризация по состоянию.
        # Здесь уже _on_rts/_on_cts/_on_data/_on_ack проверяют соответствие
        # текущего state и типа кадра и игнорируют несоответствия.
        if frame.kind is FrameType.RTS:
            self._on_rts(frame)
        elif frame.kind is FrameType.CTS:
            self._on_cts(frame)
        elif frame.kind is FrameType.DATA:
            self._on_data(frame)
        elif frame.kind is FrameType.ACK:
            self._on_ack(frame)

    def _on_rts(self, frame: Frame):
        # Проверяем условия старта (state=IDLE, PHY свободна, NAV=0).
        if self.state != self.IDLE:
            self.node.log(f"MAC: ignore RTS from {frame.source} (state={self.state})")
            return
        if self.node.phy.busy:
            self.node.log(f"MAC: ignore RTS from {frame.source} (PHY busy)")
            return

        # Переходим в WFDATA и шлём CTS.
        self.state = self.WFDATA

        prop = self.node.topology.propagation_delay(self.node.node_id, frame.source)
        nav_duration = (
            self.config.tx_duration(self.config.data_bits)
            + self.config.tx_duration(self.config.ack_bits)
            + 3 * prop
            + EPS
        )

        self.node.phy.reserve_tx()
        cts = Frame(
            kind=FrameType.CTS,
            source=self.node.node_id,
            destination=frame.source,
            bits=self.config.cts_bits,
            sequence=frame.sequence,
            duration=nav_duration,
        )
        self.node.log(f"MAC: recv RTS from {frame.source}, send CTS")
        self.env.process(self.node.phy.transmit(cts))
        self.env.process(self._wait_data_timeout(frame.source))

    def _wait_data_timeout(self, source):
        """Сторожевой таймер: если DATA не пришла — вернуться в IDLE."""
        prop = self.node.topology.propagation_delay(self.node.node_id, source)
        t = (
            self.config.tx_duration(self.config.ack_bits)
            + 2 * prop
            + self.config.tx_duration(self.config.data_bits)
            + EPS
        )
        yield self.env.timeout(t)
        if self.state == self.WFDATA:
            self.node.log(f"MAC: timeout waiting DATA from {source}")
            self._set_idle()

    def _on_cts(self, frame: Frame):
        if self.state != self.WFCTS:
            self.node.log(f"MAC: ignore CTS from {frame.source} (state={self.state})")
            return
        if self._cts_event is None or self._cts_event.triggered:
            return
        self._cts_event.succeed()

    def _on_data(self, frame: Frame):
        if self.state != self.WFDATA:
            self.node.log(f"MAC: ignore DATA from {frame.source} (state={self.state})")
            return

        self.node.log(f"MAC: recv DATA seq={frame.sequence} from {frame.source}")
        self.node.network.on_data(frame)

        # Шлём ACK и переходим в IDLE.
        self.node.phy.reserve_tx()
        ack = Frame(
            kind=FrameType.ACK,
            source=self.node.node_id,
            destination=frame.source,
            bits=self.config.ack_bits,
            sequence=frame.sequence,
        )
        self.node.log(f"MAC: send ACK -> {frame.source} (seq={frame.sequence})")
        self._set_idle()
        self.env.process(self.node.phy.transmit(ack))

    def _on_ack(self, frame: Frame):
        if self.state != self.WFACK:
            self.node.log(f"MAC: ignore ACK from {frame.source} (state={self.state})")
            return
        if self._ack_event is None or self._ack_event.triggered:
            return
        self._ack_event.succeed()