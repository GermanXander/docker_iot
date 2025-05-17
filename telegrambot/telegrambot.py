from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import logging, os
from lib.mqtt_as import MQTTClient
from lib.mqtt_local import config
import aiomqtt, asyncio, ssl


mqtt_server = os.environ["SERVIDOR"]
topico_setpoint = "8D6056F2D249B40F/setpoint"
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
    
    client: aiomqtt.Client = context.application.bot_data["mqtt_client"]
    await client.publish(topico_setpoint, valor.encode())
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
    tls_context = ssl.create_default_context()
    tls_context.check_hostname = True
    tls_context.verify_mode = ssl.CERT_REQUIRED
    tls_context.load_default_certs()

    mqtt_client = aiomqtt.Client(
        os.environ["SERVIDOR"],
        port = 8883,
        tls_context = tls_context,
    )
    await mqtt_client.connect()

    application = Application.builder().token(token).build()
    application.bot_data['mqtt_client'] = mqtt_client

    logging.info(autorizados)
    application = Application.builder().token(token).build()
    application.add_handler(MessageHandler((~filters.User(autorizados)), sin_autorizacion))
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('acercade', acercade))
    application.add_handler(CommandHandler('setpoint', setpoint))

    logging.info("iniciando bot...")


    await application.run_polling()




if __name__ == '__main__':
    main()
