class NetworkLayer:
    def __init__(self, node):
        self.node = node
        self.relayed: set[int] = set()
        self.relay_buffer: set[int] = set()

    def send_packets(self, destination, packet_ids):
        """Источник инициирует передачу — MACA-U (push)."""
        local_recipients = self.pick_local_recipients(destination)
        self.node.log(f"NET: send pkts={sorted(packet_ids)} -> {destination} via {local_recipients}")
        return self.node.mac.send_packets(destination, tuple(packet_ids), local_recipients)

    def pick_local_recipients(self, target):
        kn = self.node.known_neighbors
        if not kn.knows(target):
            return ()
        if kn.can_hear(target):
            return (target,)
        my_d = kn.distance_to(target)
        return tuple(nid for nid in kn.neighbors()
                     if nid != target and kn.can_hear(nid)
                     and kn.distance_from(nid, target) < my_d)

    # ---------- приём ----------

    def on_data(self, frame):
        if frame.destination == self.node.node_id:
            self.node.application.on_packets(frame.source, frame.packets)
            return
        if not self.progress_vs(frame.source, frame.destination):
            self.node.log("NET: no progress -> discard")
            return

        to_relay = set(frame.packets) - self.relayed
        if not to_relay:
            return

        self.relay_buffer.update(to_relay)     # NEW
        self.relayed.update(to_relay)          # теперь у всех, не только у лидера

        group = tuple(frame.local_recipients)
        if len(group) > 1:
            # группа → pull: только лидер шлёт ANN
            leader = self._pick_leader(group, frame.destination)
            if self.node.node_id == leader:
                self.relayed.update(to_relay)
                self.node.log(f"NET: LEADER send ANN -> {frame.destination} (pkts={sorted(to_relay)}, group={group})")
                self.node.mac.send_ann(frame.destination, tuple(sorted(to_relay)), group)
            else:
                self.node.log(f"NET: not leader (leader={leader}), idle, wait REQ")
        else:
            # unicast → MACA-U
            self.relayed.update(to_relay)
            self.node.log(f"NET: RELAY pkts={sorted(to_relay)} -> {frame.destination}")
            self.send_packets(frame.destination, tuple(sorted(to_relay)))

    def on_ann(self, frame):
        """Я получил ANN — надо запросить пакеты у группы."""
        self.node.log(f"NET: got ANN from {frame.source}, send REQ -> {frame.data_senders}")
        self.node.mac.send_req(frame.data_senders, frame.packets)

    def on_req(self, frame):
        """Меня запросили — шлю свои пакеты source'у (без ACK)."""
        to_send = self.relay_buffer & set(frame.packets)
        if not to_send:
            self.node.log("NET: no pkts to send for REQ")
            return
        self.node.log(f"NET: REQ from {frame.source}, send DATA (pkts={sorted(to_send)})")
        self.node.mac.send_data_unacked(frame.source, tuple(sorted(to_send)))

    def _pick_leader(self, group, target):
        kn = self.node.known_neighbors
        known = [g for g in group if kn.knows(g)]
        return min(known, key=lambda g: kn.distance_from(g, target))

    def progress_vs(self, sender_id, target_id):
        kn = self.node.known_neighbors
        if not kn.knows(target_id) or not kn.knows(sender_id):
            return False
        return kn.distance_to(target_id) < kn.distance_from(sender_id, target_id)