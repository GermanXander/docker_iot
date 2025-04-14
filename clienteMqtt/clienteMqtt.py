import asyncio
import ssl
import certifi
import logging
import os
import aiomqtt

# Configuración del logger
logging.basicConfig(
    format='%(asctime)s %(funcName)s - %(message)s',
    level=logging.INFO,
    datefmt='%d/%m/%Y %H:%M:%S ',
)

class Contador:
    def __init__(self):
        self._valor = 0
        self._lock = asyncio.Lock()

    async def incrementar(self):
        async with self._lock:
            self._valor += 1

    async def obtener(self):
        async with self._lock:
            return self._valor

async def read_messages(nombre, queue):
    logger = logging.getLogger(nombre)
    while True:
        mensaje = await queue.get()
        logger.info(f"[{mensaje.topic}] : {mensaje.payload.decode('utf-8')}")

async def distributor(client, topico1, topico2, queue1, queue2):
    async for mensaje in client.messages:
        if mensaje.topic.matches(topico1):
            queue1.put_nowait(mensaje)
        elif mensaje.topic.matches(topico2):
            queue2.put_nowait(mensaje)

async def incremento(contador):
    while True:
        await contador.incrementar()
        await asyncio.sleep(3)

async def publicacion(client, publish_topic, contador):
    logger = logging.getLogger("publisher")
    while True:
        valor = await contador.obtener()
        await client.publish(publish_topic, str(valor))
        logger.info(f"Publicado: {valor}")
        await asyncio.sleep(5)

async def main():
    servidor = os.environ["SERVIDOR"]
    topico1 = os.environ["TOPICO1"]
    topico2 = os.environ["TOPICO2"]
    publish_topic = os.environ["TOPICO_PUB"]

    tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    tls_context.verify_mode = ssl.CERT_REQUIRED
    tls_context.check_hostname = True
    tls_context.load_default_certs()

    queue1 = asyncio.Queue()
    queue2 = asyncio.Queue()
    contador = Contador()

    async with aiomqtt.Client(servidor, port=8883, tls_context=tls_context) as client:
        await client.subscribe(topico1)
        await client.subscribe(topico2)

        async with asyncio.TaskGroup() as tg:
            tg.create_task(distributor(client, topico1, topico2, queue1, queue2))
            tg.create_task(read_messages("topico1", queue1))
            tg.create_task(read_messages("topico2", queue2))
            tg.create_task(incremento(contador))
            tg.create_task(publicacion(client, publish_topic, contador))

if __name__ == "__main__":
    asyncio.run(main())
