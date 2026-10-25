class NetworkLayer:
    def __init__(self, node):
        self.node = node
        self.next_sequence = 0

    def send(self, destination: str, payload: bytes):
        sequence = self.next_sequence
        self.next_sequence += 1
        return self.node.mac.send_data(destination, sequence, payload)

    def on_data(self, frame):
        self.node.application.on_data(
            source = frame.source,
            sequence = frame.sequence,
            payload = frame.payload,
        )
        