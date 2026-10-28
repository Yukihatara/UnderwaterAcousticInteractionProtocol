import simpy

from common import Config
from channel import AcousticChannel
from node import Node


def main():
    env = simpy.Environment()
    config = Config()

    channel = AcousticChannel(env, config)
    node_a = Node(env, "A", channel, config)
    node_b = Node(env, "B", channel, config)

    def s1():
        # A стартует позже, чем B, чтобы B успел прислать RTS
        # и A оказался в WFDATA, когда придёт send_data сверху.
        # yield env.timeout(1.2)
        ok = yield node_a.application.send("B", b"Hello World! From node A")
        node_a.log(f"APP: s1 доставлено={ok}")

    def s2():
        ok = yield node_b.application.send("A", b"From process B")
        node_b.log(f"APP: s2 доставлено={ok}")

    env.process(s1())
    env.process(s2())

    env.run(until=20)


if __name__ == "__main__":
    main()