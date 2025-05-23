from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, ConversationHandler, CallbackQueryHandler
import logging, os, traceback, locale
import aiomqtt, asyncio, ssl
import json

# Estados para los handlers de conversacion
SETPOINT, PERIODO = range(2)

ID = os.environ["ID"] #ID de la raspberry pi
topico_setpoint = f"{ID}/setpoint"
topico_periodo = f"{ID}/periodo"
topico_modo = f"{ID}/modo"
topico_rele = f"{ID}/rele"
topico_destello = f"{ID}/destello"
topico_mediciones = ID  #ID de la raspberry pi donde se publican las mediciones
token=os.environ["TB_TOKEN"] #Token del bot
autorizados=[int(x) for x in os.environ["TB_AUTORIZADOS"].split(',')] #IDs de los usuarios autorizados


ultimas_mediciones = {} #Diccionario para almacenar las mediciones mas recientes

logging.basicConfig(format='%(asctime)s - TelegramBot - %(levelname)s - %(message)s', level=logging.INFO)

async def setpoint_start(update: Update, context: ContextTypes.DEFAULT_TYPE): 
    # Inicia el messagehandler para establecer el setpoint
    await update.message.reply_text(
        "Por favor, ingrese el valor de temperatura deseado (en °C):\n"
        "O escriba /cancelar para cancelar"
    )
    return SETPOINT

async def setpoint_value(update: Update, context: ContextTypes.DEFAULT_TYPE): 
    # Maneja el valor del setpoint ingresado por el usuario
    try:
        valor = int(update.message.text)
        mqtt_client = context.bot_data["mqtt_client"]
        await mqtt_client.publish(topico_setpoint, str(valor).encode(), qos=1)
        await update.message.reply_text(f"✅ Setpoint actualizado a {valor}°C 🌡️")
        logging.info(f"Setpoint enviado: {valor}°C")
        return ConversationHandler.END
    except ValueError: #comprobacion 
        await update.message.reply_text(
            "❌ El valor debe ser un número entero. Por favor, intente nuevamente:\n"
            "O escriba /cancelar para cancelar"
        )
        return SETPOINT

async def periodo_start(update: Update, context: ContextTypes.DEFAULT_TYPE): 
    # Inicia el messagehandler para establecer el periodo
    await update.message.reply_text(
        "Por favor, ingrese el valor del periodo en segundos:\n"
        "O escriba /cancelar para cancelar"
    )
    return PERIODO

async def periodo_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Maneja el valor del periodo ingresado por el usuario
    try:
        valor = int(update.message.text)
        mqtt_client = context.bot_data["mqtt_client"]
        await mqtt_client.publish(topico_periodo, str(valor).encode(), qos=1)
        await update.message.reply_text(f"✅ Periodo actualizado a {valor} segundos 🕒")
        logging.info(f"Periodo enviado: {valor} segundos")
        return ConversationHandler.END
    except ValueError: #comprobacion 
        await update.message.reply_text(
            "❌ El valor debe ser un número entero. Por favor, intente nuevamente:\n"
            "O escriba /cancelar para cancelar"
        )
        return PERIODO

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Cancela la conversacion
    await update.message.reply_text("❌ Operación cancelada")
    return ConversationHandler.END

async def modo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1 or context.args[0] not in ["automatico", "manual"]: #comprobacion de los argumentos
        await update.message.reply_text("Usá: /modo automatico o /modo manual")
        return
    nuevo_modo = 1 if context.args[0] == "automatico" else 0 #1 para automatico, 0 para manual
    context.application.bot_data["modo"] = nuevo_modo #actualiza el modo en el bot_data
    mqtt_client = context.application.bot_data["mqtt_client"] #obtiene el cliente MQTT
    await mqtt_client.publish("modo", str(nuevo_modo)) #envia el nuevo modo al broker
    if nuevo_modo == 1:
        await update.message.reply_text("Modo automatico activado! 🔄")
    else:
        await update.message.reply_text("Modo manual activado! 🛠")

async def rele(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1 or context.args[0] not in ["encendido", "apagado"]: #comprobacion de los argumentos
        await update.message.reply_text("Usá: /rele encendido o /rele apagado")
        return

    modo_actual = context.application.bot_data.get("modo", 1) #obtiene el modo actual
    if modo_actual != 0:
        await update.message.reply_text("Solo podés activar el relé en modo manual 🫤") 
        return

    estado = 1 if context.args[0] == "encendido" else 0 #1 para encendido, 0 para apagado
    mqtt_client = context.application.bot_data["mqtt_client"] #obtiene el cliente MQTT
    await mqtt_client.publish("rele", str(estado)) #envia el estado al broker
    if estado == 1: 
        await update.message.reply_text("Relé encendido ⬆️")
    else:
        await update.message.reply_text("Relé apagado ⬇️")

async def destello(update: Update, context: ContextTypes.DEFAULT_TYPE): #activa el destello
    mqtt_client = context.bot_data["mqtt_client"] 
    await mqtt_client.publish(topico_destello, "1".encode(), qos=1)
    await update.message.reply_text("Destello activado 🔦")
    logging.info("Destello enviado") 

async def sin_autorizacion(update: Update, context: ContextTypes.DEFAULT_TYPE): #si el usuario no esta autorizado
    logging.info("intento de conexión de: " + str(update.message.from_user.id))
    await context.bot.send_message(chat_id=update.effective_chat.id, text="No autorizado 🚫")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE): #inicia el bot
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

    kb = [ #botones del teclado
        ["🌡️ Setpoint", "⏱️ Periodo"],
        ["/modo automatico", "/modo manual"],
        ["/rele encendido", "/rele apagado"],
        ["/destello", "📊 Mediciones"]
    ]
    reply_markup = ReplyKeyboardMarkup(kb, resize_keyboard=True) #crea el teclado
    await context.bot.send_message( #envia el mensaje
        update.message.chat.id, 
        text="Hola "+ nombre + " " + apellido +"! Bienvenido al Jotabot 🤖\n"
        "Usá los botones del teclado para controlar el sistema 😉", 
        reply_markup=reply_markup
    )

async def mediciones(update: Update, context: ContextTypes.DEFAULT_TYPE): 
    # Muestra las mediciones actuales
    if not ultimas_mediciones: #si no hay mediciones
        await update.message.reply_text("No hay mediciones disponibles en este momento 📊")
        return
    
    mensaje = ( #mensaje a enviar
        f"📊 *Mediciones actuales:*\n\n"
        f"Temperatura: {ultimas_mediciones.get('temperatura', 'N/A')}°C\n"
        f"Humedad: {ultimas_mediciones.get('humedad', 'N/A')}%\n"
        f"Setpoint: {ultimas_mediciones.get('setpoint', 'N/A')}°C\n"
        f"Periodo: {ultimas_mediciones.get('periodo', 'N/A')} segundos\n"
        f"Modo: {'Automático' if ultimas_mediciones.get('modo') == 1 else 'Manual' if ultimas_mediciones.get('modo') == 0 else 'N/A'}"
    )
    
    await update.message.reply_text(mensaje, parse_mode='Markdown')

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE): 
    # Cancela la conversacion
    await update.message.reply_text("❌ Operación cancelada")
    return ConversationHandler.END

async def async_main():
    # Configura el contexto TLS para la verificacion de certificados
    tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    tls_context.verify_mode = ssl.CERT_REQUIRED
    tls_context.check_hostname = True
    tls_context.load_default_certs()

    #Inicializa el bot
    application = Application.builder().token(token).build()

    # Crea los handlers de conversacion
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

    # Agrega los handlers
    application.add_handler(MessageHandler((~filters.User(autorizados)), sin_autorizacion))
    application.add_handler(CommandHandler('start', start))
    application.add_handler(setpoint_handler)
    application.add_handler(periodo_handler)
    application.add_handler(CommandHandler('modo', modo))
    application.add_handler(CommandHandler('rele', rele))
    application.add_handler(CommandHandler('destello', destello))
    application.add_handler(CommandHandler('mediciones', mediciones))
    application.add_handler(MessageHandler(filters.Regex('^📊 Mediciones$'), mediciones))
    application.add_handler(CommandHandler('cancelar', cancel))

    logging.info("Iniciando el bot...")

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
    application.bot_data["mqtt_client"] = client #agrega el cliente MQTT al bot_data para pasarlo a los handlers
    application.bot_data["modo"] = 1 #modo automatico por defecto
    logging.info(f"Conectado al broker MQTT:{os.environ['DOMINIO']}") #log de la conexion

    # Suscribe al topico de mediciones
    await client.subscribe(topico_mediciones)
    logging.info(f"Suscrito al tópico: {topico_mediciones}") #log de la suscripcion

    async def message_handler(): #maneja los mensajes del broker
        async for msg in client.messages:
            try:
                data = json.loads(msg.payload.decode()) #decodifica el mensaje
                ultimas_mediciones["temperatura"] = data.get("temperatura", "N/A") #obtiene la temperatura
                ultimas_mediciones["humedad"] = data.get("humedad", "N/A") #obtiene la humedad
                ultimas_mediciones["setpoint"] = data.get("setpoint", "N/A") #obtiene el setpoint
                ultimas_mediciones["periodo"] = data.get("periodo", "N/A") #obtiene el periodo
                ultimas_mediciones["modo"] = data.get("modo", "N/A") #obtiene el modo
            except json.JSONDecodeError:
                logging.error(f"Error al decodificar el mensaje: {msg.payload.decode()}") #log de error
            except Exception as e:
                logging.error(f"Error inesperado: {e}") 

    asyncio.create_task(message_handler())
                
    # Inicia el bot
    try: 
        await application.run_polling() #inicia el bot
    finally:
        await client.__aexit__(None, None, None) #cierra la conexion con el broker

if __name__ == '__main__':
    import nest_asyncio #importa nest_asyncio para poder usar asyncio en el bot
    nest_asyncio.apply() #aplica nest_asyncio
    asyncio.run(async_main()) #inicia el bot


