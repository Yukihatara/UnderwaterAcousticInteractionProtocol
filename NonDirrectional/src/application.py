class ApplicationLayer:
    def __init__(self, node):
        self.node = node
        self.packets: set[int] = set()          # что у меня есть
        self.received: dict[int, str] = {}      # pid -> source (для E)

    def add_packets(self, ids):
        self.packets.update(ids)
        self.node.log(f"APP: holds pkts={sorted(self.packets)}")

    def send_packets(self, destination, packet_ids):
        return self.node.network.send_packets(destination, tuple(packet_ids))

    def on_packets(self, source, packet_ids):
        for pid in packet_ids:
            self.received.setdefault(pid, source)
            self.packets.add(pid)
        self.node.log(f"APP: got pkts={sorted(packet_ids)} from={source}")