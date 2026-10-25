class ApplicationLayer:
    def __init__(self, node):
        self.node = node
        self.received = []

    def send(self, destination: str, payload: bytes):
        return self.node.network.send(destination, payload)

    def on_data(self, source: str, sequence: int, payload: bytes):
        self.received.append((source, sequence, payload))
        self.node.log(f"APP: received seq={sequence}, from={source} payload={payload!r}")



