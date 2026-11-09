import simpy

def sender(env, response):
    print(f'S: send RTS in {env.now} c')

    result = yield response | env.timeout(4)

    if response in result:
        print(f'S: Get CTS in {env.now} c')
    else:
        print(f'Timeout, CTS not get , in {env.now} c')

def receiver(env, response):
    yield env.timeout(2)
    
    print(f'R: left 2 seconds in {env.now} c')

    yield env.timeout(1)

    print(f'R: Send  CTS {env.now} c')

    response.succeed()

env = simpy.Environment()
response = env.event()

env.process(sender(env, response))
env.process(receiver(env, response))

env.run()

# -------------------------------------------------------------------------------- #
# import simpy

# def sender(env, transmitter, name, duration):
#     print(f'{env.now}: {name} хочет передавать')


#     with transmitter.request() as request:
#         yield request

#         print(f'{env.now}: {name} начал передачу')
#         yield env.timeout(duration)
#         print(f'{env.now}: {name} начал передачу')
        
# env = simpy.Environment()
# transmitter = simpy.Resource(env, capacity=1)

# env.process(sender(env, transmitter, 'RTS', 10))
# env.process(sender(env, transmitter, 'DATA', 3))

# env.run()