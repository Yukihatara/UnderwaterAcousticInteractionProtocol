import simpy

from common import Config, FrameType
from channel import AcousticChannel
from node import Node

def main():
    env = simpy.Environment()
    config = Config()

    channel = AcousticChannel(env, config)
    node_a = Node(env, "A", channel, config)
    node_b = Node(env, "B", channel, config)
    # node_c = Node(env, "C", channel, config)


    # # ==== SCENARIO 1 ==== #
    # def scenario():
    #     node_a.log("APP: отправляю первое")
    #     ok1 = yield node_a.application.send("B", b"first")
    #     node_a.log(f"APP: первое доставлено? {ok1}")

    #     node_a.log("APP: отправляю второе")
    #     ok2 = yield node_a.application.send("B", b"second")
    #     node_a.log(f"APP: второе доставлено? {ok2}")


    # # ==== SCENARIO 2 ==== #
    # def scenario():
    #     node_a.log("APP: хочу передать")
    #     yield node_a.application.send(
    #         destination="B",
    #         payload=b"Hello underwater",
    #     )

    #     print()
    #     print("=== Что получил B ===")
    #     for source, sequence, payload in node_b.application.received:
    #         print(f" seq={sequence} от {source}: {payload.decode(errors='replace')}")

    #     node_a.log("APP: передача завершена")


    # # ==== Test 1 ==== #
    # def scenario():
    #     for i in range(3):
    #         ok = yield node_a.application.send("B", f"msg-{i}".encode())
    #         node_a.log(f"APP: msg-{i} доставлено={ok}")


    # # ==== Test 2 ==== #
    # def s1():
    #     ok = yield node_a.application.send("B", b"from process 1")
    #     node_a.log(f"APP: s1 доставлено={ok}")

    # def s2():
    #     ok = yield node_a.application.send("B", b"from process 2")
    #     node_a.log(f"APP: s2 доставлено={ok}")

    # env.process(s1())
    # env.process(s2())

    # ==== Test 2 ==== #
    def s1():
        # yield env.timeout(1.067)
        yield env.timeout(1.3)
        ok = yield node_a.application.send("B", b"Hello World! From node A")
        node_a.log(f"APP: s1 доставлено={ok}")

    def s2():
        ok = yield node_b.application.send("A", b"From process B")
        node_a.log(f"APP: s2 доставлено={ok}")

    env.process(s1())
    env.process(s2())


    # env.process(scenario())
    env.run(until=20)

if __name__ == "__main__":
    main()