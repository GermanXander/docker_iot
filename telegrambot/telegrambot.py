from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import logging, os
import aiomqtt, asyncio, ssl


ID = os.environ["ID"]

topico_setpoint = f"{ID}/setpoint"
token=os.environ["TB_TOKEN"]
autorizados=[int(x) for x in os.environ["TB_AUTORIZADOS"].split(',')]

logging.basicConfig(format='%(asctime)s - TelegramBot - %(levelname)s - %(message)s', level=logging.INFO)

async def setpoint (update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Se debe indicar un valor")
        return
    try: 
        valor = int(context.args[0])
    except ValueError:
        await update.message.reply_text("El valor debe ser un número entero")
        return
    
    mqtt_client = context.bot_data["mqtt_client"]

    await mqtt_client.publish(topico_setpoint, str(valor).encode(), qos=1)
    await update.message.reply_text(f"Setpoint actualizado a {valor}°C")
    logging.info(f"Setpoint enviado: {valor}°C")


async def sin_autorizacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("intento de conexión de: " + str(update.message.from_user.id))
    await context.bot.send_message(chat_id=update.effective_chat.id, text="no autorizado")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(update)
    logging.info("se conectó: " + str(update.message.from_user.id))
    if update.message.from_user.first_name:
        nombre=update.message.from_user.first_name
    else:
        nombre=""
    if update.message.from_user.last_name:
        apellido=update.message.from_user.last_name
    else:
        apellido=""
    await context.bot.send_message(update.message.chat.id, text="Hola"+ nombre + " " + apellido +" soy Jotabot")
    # await update.message.reply_text("Bienvenido al Bot "+ nombre + " " + apellido) # también funciona

async def acercade(update: Update, context):
    await context.bot.send_message(update.message.chat.id, text="Este es el bot del Jota")

async def main():
    # Configure TLS context for certificate verification
    tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    tls_context.verify_mode = ssl.CERT_REQUIRED
    tls_context.check_hostname = True
    tls_context.load_default_certs()

    #Inicializar bot
    application = Application.builder().token(token).build()

    #Manejadores de comandos
    application.add_handler(MessageHandler((~filters.User(autorizados)), sin_autorizacion))
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('acercade', acercade))
    application.add_handler(CommandHandler('setpoint', setpoint))

    logging.info("iniciando bot...")

    #Creacion y conexion del cliente MQTT con TLS
    async with aiomqtt.Client(
        hostname=os.environ["DOMINIO"],
        port=int(os.environ["PUERTO_MQTTS"]),
        username=os.environ["MQTT_USR"],
        password=os.environ["MQTT_PASS"],
        tls_context=tls_context,
        tls_insecure=False
    ) as mqtt_client:

        application.bot_data["mqtt_client"] = mqtt_client
        logging.info(f"Conectado al broker MQTT:{os.environ['DOMINIO']}")
        
        polling_task = asyncio.create_task(application.run_polling())


        await polling_task

    

if __name__ == '__main__':
    try:
        asyncio.get_event_loop().run_until_complete(main())
    except KeyboardInterrupt:
        print("Apagando bot...")z

