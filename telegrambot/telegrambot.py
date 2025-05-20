from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import logging, os, traceback, locale
import aiomqtt, asyncio, ssl


ID = os.environ["ID"]
topico_setpoint = f"{ID}/setpoint"
topico_periodo = f"{ID}/periodo"
topico_modo = f"{ID}/modo"
topico_rele = f"{ID}/rele"
topico_destello = f"{ID}/destello"
token=os.environ["TB_TOKEN"]
autorizados=[int(x) for x in os.environ["TB_AUTORIZADOS"].split(',')]

logging.basicConfig(format='%(asctime)s - TelegramBot - %(levelname)s - %(message)s', level=logging.INFO)



async def setpoint (update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Se debe indicar un valor 🌡️")
        return
    try: 
        valor = int(context.args[0])
    except ValueError:
        await update.message.reply_text("El valor debe ser un número entero 🌡️")
        return
    mqtt_client = context.bot_data["mqtt_client"]

    await mqtt_client.publish(topico_setpoint, str(valor).encode(), qos=1)
    await update.message.reply_text(f"Setpoint actualizado a {valor}°C 🌡️")
    logging.info(f"Setpoint enviado: {valor}°C")

async def periodo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not context.args:
        await update.message.reply_text("Se debe indicar un valor de periodo 🕒")
        return
    try: 
        valor = int(context.args[0])
    except ValueError:
        await update.message.reply_text("El periodo debe ser un numero entero 🕒")
        return
    
    mqtt_client = context.bot_data["mqtt_client"]

    await mqtt_client.publish(topico_periodo, str(valor).encode(), qos=1)
    await update.message.reply_text(f"Periodo actualizado a {valor} segundos 🕒")
    logging.info(f"Periodo enviado: {valor} segundos")


async def modo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1 or context.args[0] not in ["automatico", "manual"]:
        await update.message.reply_text("Usá: /modo automatico o /modo manual")
        return
    nuevo_modo = 1 if context.args[0] == "automatico" else 0
    context.application.bot_data["modo"] = nuevo_modo
    mqtt_client = context.application.bot_data["mqtt_client"]
    await mqtt_client.publish("modo", str(nuevo_modo))
    if nuevo_modo == 1:
        await update.message.reply_text("Modo automatico activado! 🔄")
    else:
        await update.message.reply_text("Modo manual activado! 🛠")



async def rele(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1 or context.args[0] not in ["encendido", "apagado"]:
        await update.message.reply_text("Usá: /rele encendido o /rele apagado")
        return

    modo_actual = context.application.bot_data.get("modo", 1)
    if modo_actual != 0:
        await update.message.reply_text("Solo podés activar el relé en modo manual 🫤")
        return

    estado = 1 if context.args[0] == "encendido" else 0
    mqtt_client = context.application.bot_data["mqtt_client"]
    await mqtt_client.publish("rele", str(estado))
    if estado == 1:
        await update.message.reply_text("Relé encendido 💡")
    else:
        await update.message.reply_text("Relé apagado 💤")


async def destello(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mqtt_client = context.bot_data["mqtt_client"]
    await mqtt_client.publish(topico_destello, "1".encode(), qos=1)
    await update.message.reply_text("Destello activado 💡")
    logging.info("Destello enviado")


async def sin_autorizacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("intento de conexión de: " + str(update.message.from_user.id))
    await context.bot.send_message(chat_id=update.effective_chat.id, text="No autorizado 🚫")



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

    kb = [
        ["/modo automatico", "/modo manual"],
        ["/rele encendido", "/rele apagado"],
        ["/destello"]
        ]
    reply_markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
    await context.bot.send_message(update.message.chat.id, text="Hola "+ nombre + " " + apellido +"! Bienvenido al Jotabot 🤖\nEn el teclado tenés comandos de acceso rápido 😉", reply_markup=reply_markup)


async def temperatura(update: Update, context: ContextTypes.DEFAULT_TYPE):
    


async def async_main():
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
    application.add_handler(CommandHandler('setpoint', setpoint))
    application.add_handler(CommandHandler('periodo', periodo))
    application.add_handler(CommandHandler('modo', modo))
    application.add_handler(CommandHandler('rele', rele))
    application.add_handler(CommandHandler('destello', destello))



    logging.info("iniciando bot...")

    #Creacion y conexion del cliente MQTT con TLS
    client = aiomqtt.Client(
        hostname=os.environ["DOMINIO"],
        port=int(os.environ["PUERTO_MQTTS"]),
        username=os.environ["MQTT_USR"],
        password=os.environ["MQTT_PASS"],
        tls_context=tls_context,
        tls_insecure=False
    )


    await client.__aenter__()
    application.bot_data["mqtt_client"] = client
    application.bot_data["modo"] = 1 #modo automatico por defecto
    logging.info(f"Conectado al broker MQTT:{os.environ['DOMINIO']}")

    try: 
        await application.run_polling()
    finally:
        await client.__aexit__(None, None, None)



if __name__ == '__main__':
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(async_main())


