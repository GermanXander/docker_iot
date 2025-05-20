from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import logging, os, asyncio, aiomysql, traceback, locale
import matplotlib.pyplot as plt
from io import BytesIO

token=os.environ["TB_TOKEN"]

logging.basicConfig(format='%(asctime)s - TelegramBot - %(levelname)s - %(message)s', level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("se conectó: " + str(update.message.from_user.id))
    if update.message.from_user.first_name:
        nombre=update.message.from_user.first_name
    else:
        nombre=""
    if update.message.from_user.last_name:
        apellido=update.message.from_user.last_name
    else:
        apellido=""
    kb = [["Destello"],["Modo"],["Relé"]]
    await context.bot.send_message(update.message.chat.id, text="Bienvenido al Bot "+ nombre + " " + apellido,reply_markup=ReplyKeyboardMarkup(kb))

async def acercade(update: Update, context):
    await context.bot.send_message(update.message.chat.id, text="Este bot fue creado para el curso de IoT FIO")

async def kill(update: Update, context):
    logging.info(context.args)
    if context.args and context.args[0] == '@e':
        await context.bot.send_animation(update.message.chat.id, "CgACAgEAAxkBAAOPZkuctzsWZVlDSNoP9PavSZmH5poAAmUCAALrx0lEVKaX7K-68Ns1BA")
        await asyncio.sleep(6)
        await context.bot.send_message(update.message.chat.id, text="¡¡¡Ahora estan todos muertos!!!")
    else:
        await context.bot.send_message(update.message.chat.id, text="☠️ ¡¡¡Esto es muy peligroso!!! ☠️")

async def setpoint(update: Update, context):
    logging.info(context.args)

    if not context.args:
        await context.bot.send_message(chat_id=update.message.chat.id, text="Por favor ingresa un valor numérico.")
        return
    try:
        setpoint=float(context.args[0])
        await context.bot.send_message(chat_id=update.message.chat.id, text=f"Cambiando el setpoint a: {setpoint}")
    except ValueError:
        await context.bot.send_message(chat_id=update.message.chat.id, text="El valor ingresado no es un número válido.")


async def periodo(update: Update, context):
    logging.info(context.args)

    if not context.args:
        await context.bot.send_message(chat_id=update.message.chat.id, text="Por favor ingresa un valor numérico.")
        return
    try:
        await context.bot.send_message(chat_id=update.message.chat.id, text=f"Cambiando el periodo a: {float(context.args[0])}")
    except ValueError:
        await context.bot.send_message(chat_id=update.message.chat.id, text="El valor ingresado no es un número válido.")
    

async def publicacion(client, publish_topic, valor):
    logger = logging.getLogger("publisher")
    while True:
        await client.publish(publish_topic, str(valor))
        logger.info(f"Publicado: {valor}")
        await asyncio.sleep(5)


        async with asyncio.TaskGroup() as tg:
            tg.create_task(publicacion(client, publish_topic))

async def DMR(update: Update, context):
    if update.message.text == 'Destello':
        await context.bot.send_message(chat_id=update.message.chat.id, text=f"Brilla como el sol cuando amanece")
    elif update.message.text == 'Modo':
        await context.bot.send_message(chat_id=update.message.chat.id, text=f"Flaco cambiaste el modo")
    elif update.message.text == 'Relé':
        await context.bot.send_message(chat_id=update.message.chat.id, text=f"Se activo el rele (creo)")
    else:
        await context.bot.send_message(chat_id=update.message.chat.id, text=f"Que tocaste flaco?")

async def medicion(update: Update, context):
    logging.info(update.message.text)
    sql = f"SELECT timestamp, {update.message.text} FROM mediciones ORDER BY timestamp DESC LIMIT 1"
    conn = await aiomysql.connect(host=os.environ["MARIADB_SERVER"], port=3306,
                                    user=os.environ["MARIADB_USER"],
                                    password=os.environ["MARIADB_USER_PASS"],
                                    db=os.environ["MARIADB_DB"])
    async with conn.cursor() as cur:
        await cur.execute(sql)
        r = await cur.fetchone()
        if update.message.text == 'temperatura':
            unidad = 'ºC'
        else:
            unidad = '%'
        await context.bot.send_message(update.message.chat.id,
                                    text="La última {} es de {} {},\nregistrada a las {:%H:%M:%S %d/%m/%Y}"
                                    .format(update.message.text, str(r[1]).replace('.',','), unidad, r[0]))
        logging.info("La última {} es de {} {}, medida a las {:%H:%M:%S %d/%m/%Y}".format(update.message.text, r[1], unidad, r[0]))
    conn.close()

async def graficos(update: Update, context):
    logging.info(update.message.text)
    sql = f"SELECT timestamp, {update.message.text.split()[1]} FROM mediciones where id mod 2 = 0 AND timestamp >= NOW() - INTERVAL 1 DAY AND sensor_id LIKE 'sensor_1' ORDER BY timestamp"
    conn = await aiomysql.connect(host=os.environ["MARIADB_SERVER"], port=3306,
                                    user=os.environ["MARIADB_USER"],
                                    password=os.environ["MARIADB_USER_PASS"],
                                    db=os.environ["MARIADB_DB"])
    async with conn.cursor() as cur:
        await cur.execute(sql)
        filas = await cur.fetchall()

        fig, ax = plt.subplots(figsize=(7, 4))
        fecha,var=zip(*filas)
        ax.plot(fecha,var)
        ax.grid(True, which='both')
        ax.set_title(update.message.text, fontsize=14, verticalalignment='bottom')
        ax.set_xlabel('fecha')
        ax.set_ylabel('unidad')

        buffer = BytesIO()
        fig.tight_layout()
        fig.savefig(buffer, format='png')
        plt.close()
        buffer.seek(0)
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=buffer)
        buffer.close()
    conn.close()

def main():
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('acercade', acercade))
    application.add_handler(CommandHandler('kill', kill))
    application.add_handler(CommandHandler('setpoint', setpoint))
    application.add_handler(CommandHandler('periodo', periodo))
    application.add_handler(MessageHandler(filters.Regex("^(Destello|Modo|Relé)$"), DMR))
    application.run_polling()

if __name__ == '__main__':
    main()
