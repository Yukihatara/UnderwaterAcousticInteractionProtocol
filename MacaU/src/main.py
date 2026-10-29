import simpy

from common import Config
from channel import AcousticChannel
from node import Node
from topology import Topology


def build_environment():
    env = simpy.Environment()
    config = Config()
    topology = Topology(config)

    # Топология «скрытый терминал»:
    #   A ── 1500 ── B ── 1500 ── C
    #   A ── 3000 ── C (вне max_range=2000, не слышат друг друга)
    topology.set_distance("A", "B", 1500.0)
    topology.set_distance("B", "C", 1500.0)
    topology.set_distance("A", "C", 3000.0)

    channel = AcousticChannel(env, config, topology)

    node_a = Node(env, "A", channel, topology, config)
    node_b = Node(env, "B", channel, topology, config)
    node_c = Node(env, "C", channel, topology, config)

    return env, channel, topology, node_a, node_b, node_c


def scenario_a_to_b_only():
    print("=" * 60)
    print("СЦЕНАРИЙ 1: только A -> B (C в стороне)")
    print("=" * 60)
    env, channel, topology, node_a, node_b, node_c = build_environment()

    def sender():
        ok = yield node_a.application.send("B", b"from A")
        node_a.log(f"APP: A доставлено={ok}")

    env.process(sender())
    env.run(until=20)

    print()
    print("=== Что получил B ===")
    for s, seq, p in node_b.application.received:
        print(f"  seq={seq} from={s}: {p.decode(errors='replace')}")
    print("=== Что получил C ===")
    for s, seq, p in node_c.application.received:
        print(f"  seq={seq} from={s}: {p.decode(errors='replace')}")
    print()


def scenario_hidden_terminal():
    print("=" * 60)
    print("СЦЕНАРИЙ 2: A -> B и C -> B одновременно (скрытый терминал)")
    print("=" * 60)
    env, channel, topology, node_a, node_b, node_c = build_environment()

    def sender_a():
        ok = yield node_a.application.send("B", b"from A")
        node_a.log(f"APP: A доставлено={ok}")

    def sender_c():
        ok = yield node_c.application.send("B", b"from C")
        node_c.log(f"APP: C доставлено={ok}")

    env.process(sender_a())
    env.process(sender_c())
    env.run(until=40)

    print()
    print("=== Что получил B ===")
    for s, seq, p in node_b.application.received:
        print(f"  seq={seq} from={s}: {p.decode(errors='replace')}")
    print()


if __name__ == "__main__":
    scenario_a_to_b_only()
    scenario_hidden_terminal()