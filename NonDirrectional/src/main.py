import simpy

from common import Config
from channel import AcousticChannel
from node import Node
from topology import Topology
from mac_simple import SimpleMacLayer


from mac_simple import SimpleMacLayer


def build_source_relay_environment():
    env = simpy.Environment()
    config = Config()
    topology = Topology(config)

    positions = {
        "F": (2400.0, 5845.0),
        "A": (3800.0, 5850.0),
        "B": (5000.0, 6500.0),
        "C": (5000.0, 5800.0),
        "D": (5000.0, 5000.0),
        "E": (6100.0, 5850.0),
    }
    for nid, (x, y) in positions.items():
        topology.set_position(nid, x, y)

    channel = AcousticChannel(env, config, topology)
    nodes = {
        nid: Node(env, nid, channel, topology, config, mac_class=SimpleMacLayer)
        for nid in positions
    }

    nodes["F"].application.add_packets(set(range(1, 11)))
    return env, topology, nodes


def scenario_source_relay():
    print("=" * 60)
    print("F -> A -> (B,C,D) -> E  (упрощённая цепочка)")
    print("=" * 60)
    env, topo, nodes = build_source_relay_environment()

    print("Расстояния от F:")
    for nid in ("A", "B", "C", "D", "E"):
        d = topo.get_distance("F", nid)
        mark = "OK" if d <= topo.config.max_range else " СЛЫШИТ"
        print(f"  F-{nid}: {d:7.1f} м [{mark}]")
    print()

    def sender_f():
        ok = yield nodes["F"].application.send_packets("E", tuple(range(1, 11)))
        nodes["F"].log(f"APP: broadcast done ok={ok}")

    env.process(sender_f())
    env.run(until=100)

    e = nodes["E"]
    got = set(e.application.received.keys())
    missing = set(range(1, 11)) - got
    print()
    print(f"=== E получил {len(got)}/10 пакетов ===")
    for pid in sorted(got):
        print(f"  pkt={pid:2d} from={e.application.received[pid]}")
    if missing:
        print(f"  ОТСУТСТВУЮТ: {sorted(missing)}")
    else:
        print("  Все 10 пакетов получены.")


if __name__ == "__main__":
    scenario_source_relay()






































# def build_environment():
#     env = simpy.Environment()
#     config = Config()
#     topology = Topology(config)

#     # Топология «скрытый терминал»:
#     #   A ── 1500 ── B ── 1500 ── C
#     #   A ── 3000 ── C (вне max_range=2000, не слышат друг друга)
#     topology.set_position("A",    0.0, 0.0)
#     topology.set_position("B", 1500.0, 0.0)
#     topology.set_position("C", 3000.0, 0.0)

#     channel = AcousticChannel(env, config, topology)

#     node_a = Node(env, "A", channel, topology, config)
#     node_b = Node(env, "B", channel, topology, config)
#     node_c = Node(env, "C", channel, topology, config)

#     return env, channel, topology, node_a, node_b, node_c


# def scenario_a_to_b_only():
#     print("=" * 60)
#     print("СЦЕНАРИЙ 1: только A -> B (C в стороне)")
#     print("=" * 60)
#     env, channel, topology, node_a, node_b, node_c = build_environment()

#     def sender():
#         ok = yield node_a.application.send("B", b"from A")
#         node_a.log(f"APP: A доставлено={ok}")

#     env.process(sender())
#     env.run(until=20)

#     print()
#     print("=== Что получил B ===")
#     for s, seq, p in node_b.application.received:
#         print(f"  seq={seq} from={s}: {p.decode(errors='replace')}")
#     print("=== Что получил C ===")
#     for s, seq, p in node_c.application.received:
#         print(f"  seq={seq} from={s}: {p.decode(errors='replace')}")
#     print()


# def scenario_hidden_terminal():НЕ
#     print("=" * 60)
#     print("СЦЕНАРИЙ 2: A -> B и C -> B одновременно (скрытый терминал)")
#     print("=" * 60)
#     env, channel, topology, node_a, node_b, node_c = build_environment()

#     def sender_a():
#         ok = yield node_a.application.send("B", b"from A")
#         node_a.log(f"APP: A доставлено={ok}")

#     def sender_c():
#         ok = yield node_c.application.send("B", b"from C")
#         node_c.log(f"APP: C доставлено={ok}")

#     env.process(sender_a())
#     env.process(sender_c())
#     env.run(until=40)

#     print()
#     print("=== Что получил B ===")
#     for s, seq, p in node_b.application.received:
#         print(f"  seq={seq} from={s}: {p.decode(errors='replace')}")
#     print()

# def scenario_force():
#     """Проверка NAV"""
#     print("=" * 60)
#     print("СЦЕНАРИЙ FORCE")
#     print("=" * 60)
#     env, channel, topology, a, b, c = build_environment()
#     # Искусственно поднимем NAV у C
#     c.mac.nav_until = 100.0

#     def sender():
#         ok = yield b.application.send("C", b"to C during NAV")
#         b.log(f"A доставлено={ok}")

#     env.process(sender())
#     env.run(until=20)

# def scenario_abort():
#     """Проверка abort"""
#     print("=" * 60)
#     print("СЦЕНАРИЙ Abort:\n" \
#     "A -> B\n" \
#     "C -> B, delay t")
#     print("=" * 60)
#     env, channel, topology, a, b, c = build_environment()
    
#     def sender_a():
#         ok = yield a.application.send("B", b"from A")
#         a.log(f"A доставлено={ok}")

#     def sender_c():
#         yield env.timeout(0.5)
#         ok = yield c.application.send("B", b"from C")
#         c.log(f"A доставлено={ok}")

#     env.process(sender_a())
#     env.process(sender_c())
#     env.run(until=20)



# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 

# def build_environment_with_positions(positions, mac_class=None):
#     env = simpy.Environment()
#     config = Config()
#     topology = Topology(config)
#     for nid, (x, y) in positions.items():
#         topology.set_position(nid, x, y)
#     channel = AcousticChannel(env, config, topology)
#     nodes = {
#         nid: Node(env, nid, channel, topology, config, mac_class=mac_class)
#         for nid in positions
#     }
#     return env, channel, topology, nodes


# def scenario_simultaneous_ok():
#     print("=" * 60)
#     print("ДЕМО 1: одновременный приём (угол ≥ 22.5°)")
#     print("  C=(0,0), A=(-1000,1000), B=(1000,1000)")
#     print("  ∠ACB = 90° — оба пакета принимаются")
#     print("=" * 60)

#     env, ch, topo, nodes = build_environment_with_positions(
#         {"A": (-1000.0, 1000.0), "B": (1000.0, 1000.0), "C": (0.0, 0.0)},
#         mac_class=SimpleMacLayer,
#     )
#     a, b, c = nodes["A"], nodes["B"], nodes["C"]

#     def sender_a():
#         ok = yield a.application.send("C", b"from A")
#         a.log(f"APP: A delivered={ok}")

#     def sender_b():
#         ok = yield b.application.send("C", b"from B")
#         b.log(f"APP: B delivered={ok}")

#     env.process(sender_a())
#     env.process(sender_b())
#     env.run(until=10)

#     print()
#     print("=== Что получил C ===")
#     for s, seq, p in c.application.received:
#         print(f"  seq={seq} from={s}: {p.decode(errors='replace')}")
#     if not c.application.received:
#         print("  (ничего)")


# def scenario_simultaneous_collision():
#     print("=" * 60)
#     print("ДЕМО 2: коллизия (угол < 22.5°)")
#     print("  C=(0,0), A=(1000,1000), B=(900,1000)")
#     print("  ∠ACB ≈ 3° — оба пакета теряются")
#     print("=" * 60)

#     env, ch, topo, nodes = build_environment_with_positions(
#         {"A": (1000.0, 1000.0), "B": (900.0, 1000.0), "C": (0.0, 0.0)},
#         mac_class=SimpleMacLayer,
#     )
#     a, b, c = nodes["A"], nodes["B"], nodes["C"]

#     def sender_a():
#         ok = yield a.application.send("C", b"from A")
#         a.log(f"APP: A delivered={ok}")

#     def sender_b():
#         ok = yield b.application.send("C", b"from B")
#         b.log(f"APP: B delivered={ok}")

#     env.process(sender_a())
#     env.process(sender_b())
#     env.run(until=10)

#     print()
#     print("=== Что получил C ===")
#     for s, seq, p in c.application.received:
#         print(f"  seq={seq} from={s}: {p.decode(errors='replace')}")
#     if not c.application.received:
#         print("  (ничего — коллизия)")


# if __name__ == "__main__":
#     # scenario_a_to_b_only()
#     # scenario_hidden_terminal()
#     # scenario_force()
#     # scenario_abort()

#     scenario_simultaneous_ok()
#     scenario_simultaneous_collision()

