import asyncio, ssl, certifi, logging
import aiomqtt
from environs import Env

env = Env()
env.read_env()

logging.basicConfig(format='%(asctime)s - %(taskName)s - %(levelname)s:%(message)s', level=logging.INFO, datefmt='%d/%m/%Y %H:%M:%S')

class Estado:
    def __init__(self):
        self.contador = 0

async def incrementar(estado): #Aumento el contador cada 3 segundos
    asyncio.current_task().set_name("Incremento")
    while True:
        await asyncio.sleep(3)
        estado.contador = estado.contador + 1

async def publicar(client, topico_pub, estado): #
    asyncio.current_task().set_name("Publicar")
    while True:
        await asyncio.sleep(5)
        await client.publish(topico_pub, str(estado.contador))
        logging.info(f"Contador ({estado.contador}) publicado en {topico_pub}")

async def atender(queue, nombre_tarea):
    asyncio.current_task().set_name(nombre_tarea)
    while True:
        mensaje = await queue.get()
        logging.info(f"Recibido en {mensaje.topic}: {mensaje.payload.decode('utf-8')}")

async def escuchar(client, sub1, sub2, queue1, queue2):
    asyncio.current_task().set_name("enviar")
    async for message in client.messages:
        if message.topic.matches(sub1):
            await queue1.put(message)
        elif message.topic.matches(sub2):
            await queue2.put(message)

async def main():
    tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    tls_context.verify_mode = ssl.CERT_REQUIRED
    tls_context.check_hostname = True
    tls_context.load_default_certs()

    topico0 = env('TOPICO0')
    topico1 = env('TOPICO1')
    topico_publicar = env('TOPICO_PUB')

    estado = Estado()
    cola_topico0 = asyncio.Queue()
    cola_topico1 = asyncio.Queue()

    async with aiomqtt.Client(
        env("SERVIDOR"),
        port=8883,
        tls_context=tls_context,
    ) as client:

        await client.subscribe(topico0)
        await client.subscribe(topico1)
        logging.info("Conectado.")

        async with asyncio.TaskGroup() as tg:
            tg.create_task(incrementar(estado))
            tg.create_task(publicar(client, topico_publicar, estado))
            tg.create_task(atender(cola_topico0, "AtencionTopic0"))
            tg.create_task(atender(cola_topico1, "AtencionTopico1"))
            tg.create_task(escuchar(client, topico0, topico1, cola_topico0, cola_topico1))

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass