import random

from common import Frame, FrameType

EPS = 1e-6


class SimpleMacLayer:
    IDLE = 'IDLE'
    WFCTS = 'WFCTS'
    WFDATA = 'WFDATA'
    WFACK = 'WFACK'
    WFACK_ANN = 'WFACK_ANN'                  # лидер ждёт ACK на ANN
    WFDATA_COLLECT = 'WFDATA_COLLECT'        # E ждёт DATA после REQ

    def __init__(self, node):
        self.node = node
        self.state = self.IDLE
        self.retry = 0
        self.max_retries = 3
        self._queue = []
        self._sender_running = False

        self._idle_event = self.env.event()
        self._idle_event.succeed()

        # MACA-U tracking
        self._cts_expected: set[str] = set()
        self._cts_received: set[str] = set()
        self._cts_event = None
        self._ack_expected: set[str] = set()
        self._ack_received: set[str] = set()
        self._ack_event = None
        self._expected_data_from: str | None = None

        # ANN tracking
        self._ann_ack_event = None

        # REQ tracking (у E, ждём DATA от группы)
        self._req_expected: set[str] = set()
        self._req_packets: dict[str, tuple[int, ...]] = {}
        self._req_data_event = None

    @property
    def env(self):
        return self.node.env

    @property
    def config(self):
        return self.node.config

    # ---------- idle ----------

    def _set_idle(self):
        self.state = self.IDLE
        self._expected_data_from = None
        if not self._idle_event.triggered:
            self._idle_event.succeed()

    def _wait_idle(self):
        if self.state != self.IDLE:
            self._idle_event = self.env.event()
            yield self._idle_event

    def _wait_until_can_transmit(self):
        while True:
            if self.state != self.IDLE:
                yield from self._wait_idle()
                continue
            if self.node.phy.busy:
                yield from self.node.phy.wait_free()
                continue
            return

    # ---------- public API ----------

    def send_packets(self, destination, packet_ids, local_recipients):
        """MACA-U (push): RTS→CTS→DATA→ACK. Используется источником."""
        done = self.env.event()
        self._queue.append((destination, tuple(packet_ids), tuple(local_recipients), done))
        if not self._sender_running:
            self._sender_running = True
            self.env.process(self._sender_loop())
        return done

    def send_ann(self, target, packet_ids, data_senders):
        """ANN + ждать ACK от target. Используется лидером группы (pull)."""
        done = self.env.event()
        self.env.process(self._do_send_ann(done, target, tuple(packet_ids), tuple(data_senders)))
        return done

    def send_req(self, recipients, packet_ids):
        """REQ + ждать DATA от всех recipients + один broadcast ACK."""
        done = self.env.event()
        self.env.process(self._do_send_req(done, tuple(recipients), tuple(packet_ids)))
        return done

    def send_data_unacked(self, target, packet_ids):
        """DATA без рукопожатия. B/C/D после REQ. ACK не ждём."""
        done = self.env.event()
        self.env.process(self._do_send_data_unacked(done, target, tuple(packet_ids)))
        return done

    # ---------- MACA-U sender loop ----------

    def _sender_loop(self):
        while self._queue:
            dest, packet_ids, local_recipients, done = self._queue.pop(0)
            ok = yield from self._exchange_maca(dest, packet_ids, local_recipients)
            done.succeed(value=ok)
        self._sender_running = False

    def _exchange_maca(self, destination, packet_ids, local_recipients):
        if not local_recipients:
            return False
        self.retry = 0
        while True:
            yield from self._wait_until_can_transmit()
            if not (yield from self._send_rts_wait_cts(local_recipients)):
                self._set_idle()
                self.retry += 1
                if self.retry > self.max_retries:
                    return False
                yield from self._backoff()
                continue
            yield from self._send_data_wait_ack(destination, packet_ids, local_recipients)
            self._set_idle()
            return True

    def _max_prop(self, recipients):
        if not recipients:
            return 0.0
        return max(self.node.known_neighbors.propagation_delay_to(r) for r in recipients)

    def _send_rts_wait_cts(self, local_recipients):
        max_prop = self._max_prop(local_recipients)
        rts = Frame(kind=FrameType.RTS, source=self.node.node_id,
                    bits=self.config.rts_bits, local_recipients=local_recipients)

        self.state = self.WFCTS
        self._cts_expected = set(local_recipients)
        self._cts_received = set()
        self._cts_event = self.env.event()

        self.node.phy.reserve_tx()
        self.node.log(f"MAC: send RTS -> {local_recipients}")
        yield from self.node.phy.transmit(rts)

        t_wait = 2 * max_prop + self.config.tx_duration(self.config.cts_bits) + EPS
        yield self._cts_event | self.env.timeout(t_wait)

        if self._cts_event.triggered:
            self.node.log(f"MAC: got CTS from {sorted(self._cts_received)}")
            return True
        self.node.log(f"MAC: CTS timeout, got {sorted(self._cts_received)}")
        return False

    def _send_data_wait_ack(self, destination, packet_ids, local_recipients):
        max_prop = self._max_prop(local_recipients)
        bits = self.config.frame_overhead_bits + len(packet_ids) * self.config.packet_bits
        data = Frame(kind=FrameType.DATA, source=self.node.node_id,
                     destination=destination, local_recipients=local_recipients,
                     bits=bits, packets=packet_ids)

        self.state = self.WFACK
        self._ack_expected = set(local_recipients)
        self._ack_received = set()
        self._ack_event = self.env.event()

        self.node.phy.reserve_tx()
        self.node.log(f"MAC: send DATA -> {destination} via {local_recipients} (pkts={packet_ids})")
        yield from self.node.phy.transmit(data)

        t_wait = 2 * max_prop + self.config.tx_duration(self.config.ack_bits) + EPS
        yield self._ack_event | self.env.timeout(t_wait)

        if self._ack_event.triggered:
            self.node.log(f"MAC: got ACK from {sorted(self._ack_received)}")
            return True
        self.node.log(f"MAC: ACK timeout")
        return False

    def _backoff(self):
        wait = random.uniform(0, self.config.backoff * (2 ** (self.retry - 1)))
        self.node.log(f"MAC: backoff {wait:.3f} s")
        yield self.env.timeout(wait)

    # ---------- ANN (pull) ----------

    def _do_send_ann(self, done, target, packet_ids, data_senders):
        yield from self._wait_until_can_transmit()

        bits = self.config.frame_overhead_bits + len(packet_ids) * self.config.packet_bits
        ann = Frame(kind=FrameType.ANN, source=self.node.node_id,
                    bits=bits, local_recipients=(target,),
                    packets=packet_ids, data_senders=data_senders)

        self.state = self.WFACK_ANN
        self._ann_ack_event = self.env.event()

        self.node.phy.reserve_tx()
        self.node.log(f"MAC: send ANN -> {target} (pkts={packet_ids}, senders={data_senders})")
        yield from self.node.phy.transmit(ann)

        prop = self.node.known_neighbors.propagation_delay_to(target)
        t_wait = 2 * prop + self.config.tx_duration(self.config.ack_bits) + EPS
        yield self._ann_ack_event | self.env.timeout(t_wait)

        if self._ann_ack_event.triggered:
            self.node.log(f"MAC: ANN ack from {target}")
            self._set_idle()
            done.succeed(value=True)
        else:
            self.node.log(f"MAC: ANN timeout")
            self._set_idle()
            done.succeed(value=False)

    def _do_send_req(self, done, recipients, packet_ids):
        yield from self._wait_until_can_transmit()

        req = Frame(kind=FrameType.REQ, source=self.node.node_id,
                    bits=self.config.req_bits if hasattr(self.config, 'req_bits') else self.config.rts_bits,
                    local_recipients=recipients, packets=packet_ids)

        self.state = self.WFDATA_COLLECT
        self._req_expected = set(recipients)
        self._req_packets = {}
        self._req_data_event = self.env.event()

        self.node.phy.reserve_tx()
        self.node.log(f"MAC: send REQ -> {recipients} (pkts={packet_ids})")
        yield from self.node.phy.transmit(req)

        # ждём DATA от всех, пока не таймаут
        max_prop = self._max_prop(recipients)
        max_data_bits = self.config.frame_overhead_bits + len(packet_ids) * self.config.packet_bits
        t_wait = (
            2 * max_prop
            + self.config.tx_duration(max_data_bits)
            + 2 * self.config.sifs
            + EPS
        )
        yield self._req_data_event | self.env.timeout(t_wait)

        # собираем объединение пакетов от всех ответивших
        all_pkts = set()
        for src_pkts in self._req_packets.values():
            all_pkts.update(src_pkts)

        # отдать пакеты приложению — по источникам
        for src, pkts in self._req_packets.items():
            self.node.application.on_packets(src, pkts)

        if all_pkts:
            ack = Frame(kind=FrameType.ACK, source=self.node.node_id,
                        bits=self.config.ack_bits,
                        local_recipients=tuple(self._req_packets.keys()),
                        packets=tuple(sorted(all_pkts)))
            self.node.phy.reserve_tx()
            self.node.log(f"MAC: send ACK -> {tuple(self._req_packets.keys())} (pkts={sorted(all_pkts)})")
            yield from self.node.phy.transmit(ack)

        self._set_idle()
        done.succeed(value=bool(all_pkts))

    def _do_send_data_unacked(self, done, target, packet_ids):
        yield from self._wait_until_can_transmit()
        bits = self.config.frame_overhead_bits + len(packet_ids) * self.config.packet_bits
        data = Frame(kind=FrameType.DATA, source=self.node.node_id,
                     destination=target, local_recipients=(target,),
                     bits=bits, packets=packet_ids)
        self.node.phy.reserve_tx()
        self.node.log(f"MAC: send DATA (unacked) -> {target} (pkts={packet_ids})")
        yield from self.node.phy.transmit(data)
        done.succeed(value=True)

    # ---------- receive ----------

    def on_frame_received(self, frame: Frame):
        if frame.local_recipients and self.node.node_id not in frame.local_recipients:
            self.node.log(f"MAC: discard {frame.kind.name} from {frame.source}")
            return

        if frame.kind is FrameType.RTS:      self._on_rts(frame)
        elif frame.kind is FrameType.CTS:    self._on_cts(frame)
        elif frame.kind is FrameType.DATA:   self._on_data(frame)
        elif frame.kind is FrameType.ACK:    self._on_ack(frame)
        elif frame.kind is FrameType.ANN:    self._on_ann(frame)
        elif frame.kind is FrameType.REQ:    self._on_req(frame)

    def _on_rts(self, frame: Frame):
        if self.state != self.IDLE:
            self.node.log(f"MAC: ignore RTS from {frame.source} (state={self.state})")
            return
        if self.node.phy.busy:
            self.node.log(f"MAC: ignore RTS from {frame.source} (PHY busy)")
            return
        self.state = self.WFDATA
        self._expected_data_from = frame.source
        cts = Frame(kind=FrameType.CTS, source=self.node.node_id,
                    bits=self.config.cts_bits, local_recipients=(frame.source,))
        self.node.phy.reserve_tx()
        self.node.log(f"MAC: recv RTS from {frame.source}, send CTS")
        self.env.process(self.node.phy.transmit(cts))
        self.env.process(self._data_watchdog(frame.source))

    def _data_watchdog(self, expected_source):
        prop = self.node.known_neighbors.propagation_delay_to(expected_source)
        max_data_bits = self.config.frame_overhead_bits + 20 * self.config.packet_bits
        t = (2 * prop + self.config.tx_duration(self.config.cts_bits)
             + self.config.tx_duration(max_data_bits)
             + self.config.tx_duration(self.config.ack_bits) + EPS)
        yield self.env.timeout(t)
        if self.state == self.WFDATA and self._expected_data_from == expected_source:
            self.node.log(f"MAC: DATA timeout from {expected_source}")
            self._set_idle()

    def _on_cts(self, frame: Frame):
        if self.state != self.WFCTS:
            return
        if frame.source not in self._cts_expected:
            return
        self._cts_received.add(frame.source)
        self.node.log(f"MAC: recv CTS from {frame.source}")
        if self._cts_expected <= self._cts_received and not self._cts_event.triggered:
            self._cts_event.succeed()

    def _on_data(self, frame: Frame):
        # E: DATA в рамках REQ-ожидания
        if self.state == self.WFDATA_COLLECT and frame.source in self._req_expected:
            self._req_packets[frame.source] = frame.packets
            self.node.log(f"MAC: DATA from {frame.source} (have {len(self._req_packets)}/{len(self._req_expected)})")
            if self._req_expected <= set(self._req_packets.keys()) and not self._req_data_event.triggered:
                self._req_data_event.succeed()
            return

        # получатель MACA-U
        if self.state != self.WFDATA:
            self.node.log(f"MAC: ignore DATA from {frame.source} (state={self.state})")
            return
        if self._expected_data_from != frame.source:
            return
        ack = Frame(kind=FrameType.ACK, source=self.node.node_id,
                    bits=self.config.ack_bits, local_recipients=(frame.source,))
        self.node.phy.reserve_tx()
        self.node.log(f"MAC: recv DATA from {frame.source}, send ACK")
        self.env.process(self.node.phy.transmit(ack))
        self._set_idle()
        self.node.network.on_data(frame)

    def _on_ack(self, frame: Frame):
        # ACK на ANN
        if self.state == self.WFACK_ANN:
            if self._ann_ack_event and not self._ann_ack_event.triggered:
                self._ann_ack_event.succeed()
            return
        # ACK на DATA (MACA-U)
        if self.state != self.WFACK:
            return
        if frame.source not in self._ack_expected:
            return
        self._ack_received.add(frame.source)
        self.node.log(f"MAC: recv ACK from {frame.source}")
        if self._ack_expected <= self._ack_received and not self._ack_event.triggered:
            self._ack_event.succeed()

    def _on_ann(self, frame: Frame):
        # Я — цель ANN. Шлю ACK и передаю наверх в NET (оно решит, слать ли REQ)
        if self.state != self.IDLE and self.state != self.WFDATA_COLLECT:
            # занят — не отвечаю, C уйдёт в таймаут/retry
            self.node.log(f"MAC: ignore ANN from {frame.source} (state={self.state})")
            return
        ack = Frame(kind=FrameType.ACK, source=self.node.node_id,
                    bits=self.config.ack_bits, local_recipients=(frame.source,))
        self.node.phy.reserve_tx()
        self.node.log(f"MAC: recv ANN from {frame.source}, send ACK")
        self.env.process(self.node.phy.transmit(ack))
        self.node.network.on_ann(frame)

    def _on_req(self, frame: Frame):
        # Я в local_recipients — надо послать свои пакеты source'у
        self.node.log(f"MAC: recv REQ from {frame.source} (pkts={frame.packets})")
        self.node.network.on_req(frame)