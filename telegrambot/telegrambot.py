from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, ConversationHandler, CallbackQueryHandler
import logging, os, traceback, locale
import aiomqtt, asyncio, ssl
import json

# States for conversation handlers
SETPOINT, PERIODO = range(2)

ID = os.environ["ID"]
topico_setpoint = f"{ID}/setpoint"
topico_periodo = f"{ID}/periodo"
topico_modo = f"{ID}/modo"
topico_rele = f"{ID}/rele"
topico_destello = f"{ID}/destello"
topico_mediciones = ID  # Topic where Raspberry Pi publishes measurements
token=os.environ["TB_TOKEN"]
autorizados=[int(x) for x in os.environ["TB_AUTORIZADOS"].split(',')]

# Dictionary to store the latest measurements
ultimas_mediciones = {}

logging.basicConfig(format='%(asctime)s - TelegramBot - %(levelname)s - %(message)s', level=logging.INFO)

async def setpoint_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the setpoint setting conversation"""
    await update.message.reply_text(
        "Por favor, ingrese el valor de temperatura deseado (en °C):\n"
        "O escriba /cancelar para cancelar"
    )
    return SETPOINT

async def setpoint_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the setpoint value input"""
    try:
        valor = int(update.message.text)
        mqtt_client = context.bot_data["mqtt_client"]
        await mqtt_client.publish(topico_setpoint, str(valor).encode(), qos=1)
        await update.message.reply_text(f"✅ Setpoint actualizado a {valor}°C 🌡️")
        logging.info(f"Setpoint enviado: {valor}°C")
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text(
            "❌ El valor debe ser un número entero. Por favor, intente nuevamente:\n"
            "O escriba /cancelar para cancelar"
        )
        return SETPOINT

async def periodo_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the periodo setting conversation"""
    await update.message.reply_text(
        "Por favor, ingrese el valor del periodo en segundos:\n"
        "O escriba /cancelar para cancelar"
    )
    return PERIODO

async def periodo_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the periodo value input"""
    try:
        valor = int(update.message.text)
        mqtt_client = context.bot_data["mqtt_client"]
        await mqtt_client.publish(topico_periodo, str(valor).encode(), qos=1)
        await update.message.reply_text(f"✅ Periodo actualizado a {valor} segundos 🕒")
        logging.info(f"Periodo enviado: {valor} segundos")
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text(
            "❌ El valor debe ser un número entero. Por favor, intente nuevamente:\n"
            "O escriba /cancelar para cancelar"
        )
        return PERIODO

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the conversation"""
    await update.message.reply_text("❌ Operación cancelada")
    return ConversationHandler.END

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
        ["🌡️ Setpoint", "⏱️ Periodo"],
        ["/modo automatico", "/modo manual"],
        ["/rele encendido", "/rele apagado"],
        ["/destello", "📊 Mediciones"]
    ]
    reply_markup = ReplyKeyboardMarkup(kb, resize_keyboard=True)
    await context.bot.send_message(
        update.message.chat.id, 
        text="Hola "+ nombre + " " + apellido +"! Bienvenido al Jotabot 🤖\n"
        "Usá los botones del teclado para controlar el sistema 😉", 
        reply_markup=reply_markup
    )

async def mediciones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display current measurements"""
    if not ultimas_mediciones:
        await update.message.reply_text("No hay mediciones disponibles en este momento 📊")
        return
    
    mensaje = (
        f"📊 *Mediciones actuales:*\n\n"
        f"Temperatura: {ultimas_mediciones.get('temperatura', 'N/A')}°C\n"
        f"Humedad: {ultimas_mediciones.get('humedad', 'N/A')}%\n"
        f"Setpoint: {ultimas_mediciones.get('setpoint', 'N/A')}°C\n"
        f"Periodo: {ultimas_mediciones.get('periodo', 'N/A')} segundos\n"
        f"Modo: {'Automático' if ultimas_mediciones.get('modo') == 1 else 'Manual' if ultimas_mediciones.get('modo') == 0 else 'N/A'}"
    )
    
    await update.message.reply_text(mensaje, parse_mode='Markdown')

async def async_main():
    # Configure TLS context for certificate verification
    tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    tls_context.verify_mode = ssl.CERT_REQUIRED
    tls_context.check_hostname = True
    tls_context.load_default_certs()

    #Inicializar bot
    application = Application.builder().token(token).build()

    # Create conversation handlers
    setpoint_handler = ConversationHandler(
        entry_points=[CommandHandler('setpoint', setpoint_start), 
                      MessageHandler(filters.Regex('^🌡️ Setpoint$'), setpoint_start)
        ],
        states={
            SETPOINT: [MessageHandler(filters.TEXT & ~filters.COMMAND, setpoint_value)]
        },
        fallbacks=[CommandHandler('cancelar', cancel)]
    )
    periodo_handler = ConversationHandler(
        entry_points=[CommandHandler('periodo', periodo_start),
                      MessageHandler(filters.Regex('^⏱️ Periodo$'), periodo_start)
        ],
        states={
            PERIODO: [MessageHandler(filters.TEXT & ~filters.COMMAND, periodo_value)]
        },
        fallbacks=[CommandHandler('cancelar', cancel)]
    )

    # Add handlers
    application.add_handler(MessageHandler((~filters.User(autorizados)), sin_autorizacion))
    application.add_handler(CommandHandler('start', start))
    application.add_handler(setpoint_handler)
    application.add_handler(periodo_handler)
    application.add_handler(CommandHandler('modo', modo))
    application.add_handler(CommandHandler('rele', rele))
    application.add_handler(CommandHandler('destello', destello))
    application.add_handler(CommandHandler('mediciones', mediciones))
    application.add_handler(MessageHandler(filters.Regex('^📊 Mediciones$'), mediciones))

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

    # Subscribe to measurements topic
    await client.subscribe(topico_mediciones)
    logging.info(f"Suscrito al tópico: {topico_mediciones}")

    async def message_handler():
        async for msg in client.messages:
            try:
                data = json.loads(msg.payload.decode())
                ultimas_mediciones["temperatura"] = data.get("temperatura", "N/A")
                ultimas_mediciones["humedad"] = data.get("humedad", "N/A")
                ultimas_mediciones["setpoint"] = data.get("setpoint", "N/A")
                ultimas_mediciones["periodo"] = data.get("periodo", "N/A")
                ultimas_mediciones["modo"] = data.get("modo", "N/A")
            except json.JSONDecodeError:
                logging.error(f"Error al decodificar el mensaje: {msg.payload.decode()}")
            except Exception as e:
                logging.error(f"Error inesperado: {e}")

    asyncio.create_task(message_handler())
                
    # Start the bot
    try: 
        await application.run_polling()
    finally:
        await client.__aexit__(None, None, None)

if __name__ == '__main__':
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(async_main())


