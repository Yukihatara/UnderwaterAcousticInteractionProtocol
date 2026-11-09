import simpy
import random

from common import Config, Frame, FrameType

EPS = 1e-6


class MacLayer:
    """Упрощённая MACA для двух узлов."""

    IDLE = 'IDLE'
    WFCTS = 'WFCTS'
    WFDATA = 'WFDATA'
    WFACK = 'WFACK'

    def __init__(self, node):
        self.node = node
        self.state = self.IDLE
        
        self.retry = 0
        self.max_retries = 3

        self._cts_event = None
        self._ack_event = None

        self._idle_event = self.env.event()
        self._idle_event.succeed()

        self._abort_event = self.env.event()

        self._queue = []
        self._sender_running = False

        self.nav_until = 0.0

    @property
    def env(self): return self.node.env

    @property
    def config(self): return self.node.config

    def _set_idle(self):
        self.state = self.IDLE
        if not self._idle_event.triggered:
            self._idle_event.succeed()

    def _wait_idle(self):
        """Дождаться, пока MAC освободится. Возвращает генератор."""
        while self.state != self.IDLE:
            self._idle_event = self.env.event()
            yield self._idle_event

    def send_data(self, destination, sequence, payload):
        """Поставить пакет в очередь. Возвращает Event, который
        сработает, когда этот пакет будет доставлен (или провалится)."""
        done = self.env.event()
        self._queue.append((destination, sequence, payload, done))
        if not self._sender_running:
            self._sender_running = True
            self.env.process(self._sender_process())
        return done

    # ----------- Отправитель -----------------

    def _sender_process(self):
        while self._queue:
            while True:
                yield from self.node.phy.wait_free()
                while self.nav_until > self.env.now:
                    yield self.env.timeout(self.nav_until - self.env.now)
                if self.state == self.IDLE:
                    break
                yield from self._wait_idle()
                

            destination, sequence, payload, done = self._queue.pop(0)
            success = yield from self._try_send(destination, sequence, payload)
            
            # Возвращаем сообщение обратно в очередь
            if success == None:
                self._queue.insert(0, (destination, sequence, payload, done))
            else: # Успех/провал
                done.succeed(value=success)

        self._sender_running = False

    def _try_send(self, destination, sequence, payload):
        """Попытаться доставить один пакет. Возвращает True при успехе,
        False при провале. Это генератор — вызывать через yield from."""

        self.retry = 0
        # propagation для пары (я, destination)
        prop = self.node.topology.propagation_delay(self.node.node_id, destination)
        nav_duration = ( # RTS -> CTS -> DATA -> ACK
            self.config.tx_duration(self.config.cts_bits)
            + self.config.tx_duration(self.config.data_bits)
            + self.config.tx_duration(self.config.ack_bits)
            + 3 * prop
            + EPS
        )
        while True:
            if self.nav_until > self.env.now:
                self._set_idle()
                return None
            # === RTS ===
            self.state = self.WFCTS
            self._cts_event = self.env.event()
            self._abort_event = self.env.event()
            self.node.phy.reserve_tx()          # синхронно, ДО transmit

            rts = Frame(
                kind=FrameType.RTS,
                source=self.node.node_id,
                destination=destination,
                bits=self.config.rts_bits,
                sequence=sequence,
                duration=nav_duration,
            )

            self.node.log(f"MAC: state=WFCTS, отправляю RTS -> {destination}")
            yield from self.node.phy.transmit(rts)

            # Ждем CTS или timeout.
            t_wait_cts = (
                2 * prop
                + self.config.tx_duration(self.config.cts_bits)
                + self.config.tx_duration(self.config.rts_bits)
                + EPS
            )
            result = yield self._cts_event | self.env.timeout(t_wait_cts) | self._abort_event

            if self._abort_event in result:
                # Нас прервали — не шлём DATA.
                self.node.log(f"MAC: обмен прерван по NAV (retry={self.retry})")
                self._abort_event = self.env.event() # снова инициализируем событие
                self._set_idle()
                return None

            if self._cts_event not in result:
                self.node.log(f"MAC: timeout CTS (retry={self.retry})")
                self.retry += 1
                if self.retry > self.max_retries:
                    self.node.log("MAC: сдаюсь после ретраев RTS (ждал CTS)")
                    self._set_idle()
                    return False
                yield from self._backoff()
                continue

            # === Шаг 2: DATA ===
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

            self.node.log(f"MAC: state=WFACK, отправляю DATA -> seq={sequence}")
            yield from self.node.phy.transmit(data)

            # Ждем ACK или timeout.
            t_wait_ack = (
                2 * prop
                + self.config.tx_duration(self.config.ack_bits)
                + self.config.tx_duration(self.config.data_bits)
                + EPS
            )
            result = yield self._ack_event | self.env.timeout(t_wait_ack)

            if self._ack_event not in result:
                self.node.log(f"MAC: таймаут ACK (retry={self.retry})")
                self.retry += 1
                if self.retry > self.max_retries:
                    self.node.log("MAC: сдаюсь после ретраев ACK")
                    self._set_idle()
                    return False
                yield from self._backoff()
                continue

            # Успех.
            self.node.log(f"MAC: доставка подтверждена seq={sequence}")
            self._set_idle()
            return True

    def _backoff(self):
        if self.retry == 0:
            return
        wait = random.uniform(0, self.config.backoff * (2 ** (self.retry - 1)))
        self.node.log(f"MAC: backoff {wait:.3f} с")
        yield self.env.timeout(wait)

    # ------------ Прием ------------------

    def on_frame_received(self, frame: Frame): 
        # (а) Чужой кадр — NAV, аборт, return.
        if frame.destination != self.node.node_id:
            if frame.kind in (FrameType.RTS, FrameType.CTS) and frame.duration > 0:
                new_nav = self.env.now + frame.duration
                if new_nav > self.nav_until:
                    old = self.nav_until
                    self.nav_until = new_nav
                    self.node.log(
                        f"MAC: NAV обновлён: {old:.4f} -> {self.nav_until:.4f} "
                        f"(по {frame.kind.name} от {frame.source})"
                    )
            self.node.log(f"MAC: кадр {frame.kind.name} не мне ({frame.destination}), игнорирую")
            return
        
        # (б) Кадр мне, но NAV активен — игнорируем.
        if self.env.now < self.nav_until:
            if frame.kind is FrameType.ACK: # (Исключение на ACK - не игнорируем)
                self._on_ack(frame)
                return
            if frame.kind is FrameType.CTS and frame.kind is FrameType.DATA:
                self._ack_event.succeed() # обрываем кадр
            self.node.log(
                f"MAC: кадр {frame.kind.name} мне ({frame.source}), "
                f"но NAV активен (до {self.nav_until:.4f}) — игнорирую"
            )
            return
        
        # (в) полноценная обработка.
        if frame.kind is FrameType.RTS:
            self._on_rts(frame)
        elif frame.kind is FrameType.CTS:
            self._on_cts(frame)
        elif frame.kind is FrameType.DATA:
            self._on_data(frame)
        elif frame.kind is FrameType.ACK:
            self._on_ack(frame)

    def _on_rts(self, frame: Frame):
        prop = self.node.topology.propagation_delay(self.node.node_id, frame.source)
        nav_duration = (
            self.config.tx_duration(self.config.data_bits)
            + self.config.tx_duration(self.config.ack_bits)
            + 3 * prop
            + EPS
        )
        if self.state != self.IDLE or self.node.phy.transmiting:
            self.node.log(f"MAC: RTS от {frame.source} проигнорирован, state={self.state}")
            return

        self.state = self.WFDATA
        self.node.phy.reserve_tx()              # синхронно, ДО env.process

        cts = Frame(
            kind=FrameType.CTS,
            source=self.node.node_id,
            destination=frame.source,
            bits=self.config.cts_bits,
            sequence=frame.sequence,
            duration=nav_duration
        )

        self.node.log(f"MAC: received RTS от {frame.source}, отправляю CTS")
        self.env.process(self.node.phy.transmit(cts))
        self.env.process(self._wait_data_timeout(frame.source))

    def _wait_data_timeout(self, source):
        prop = self.node.topology.propagation_delay(self.node.node_id, source)
        t = (
            self.config.tx_duration(self.config.cts_bits)
            + 2 * prop
            + self.config.tx_duration(self.config.data_bits)
            + EPS
        )
        yield self.env.timeout(t)
        if self.state == self.WFDATA:
            self.node.log("MAC: timeout ожидания DATA, возвращаюсь в IDLE")
            self._set_idle()

    def _on_cts(self, frame: Frame):
        if self.state != self.WFCTS:
            self.node.log(f"MAC: CTS от {frame.source} проигнорирован, state={self.state}")
            return

        if self._cts_event is None or self._cts_event.triggered:
            return
        self.node.log(f"MAC: received CTS от {frame.source}")
        self._cts_event.succeed()

    def _on_data(self, frame: Frame):
        if self.state != self.WFDATA:
            self.node.log(f"MAC: DATA от {frame.source}, state={self.state}")
            return

        # Уходим в подстейт WFACK_SEND: _sender_process не должен
        # взять новый пакет, пока ACK не отправлен.
        self._set_idle()
        self.node.phy.reserve_tx()              # синхронно, ДО env.process

        self.node.log(
            f"MAC: received DATA seq={frame.sequence}, payload={frame.payload!r}"
        )
        self.node.network.on_data(frame)

        ack = Frame(
            kind=FrameType.ACK,
            source=self.node.node_id,
            destination=frame.source,
            bits=self.config.ack_bits,
            sequence=frame.sequence,
        )
        self.node.log(f"MAC: Отправляю ACK -> {frame.source}, seq={frame.sequence}")
        # ОДИН ACK через _send_ack_and_idle, который вернёт IDLE.
        self.env.process(self.node.phy.transmit(ack))

    def _on_ack(self, frame: Frame):
        if self.state != self.WFACK:
            self.node.log(f"MAC: ACK от {frame.source} проигнорирован, state={self.state}")
            return
        if self._ack_event is None or self._ack_event.triggered:
            return
        self.node.log(f"MAC: received ACK seq={frame.sequence}")
        self._ack_event.succeed()