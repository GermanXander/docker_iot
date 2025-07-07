from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_mysqldb import MySQL
from flask_mqtt import Mqtt
import os, logging
from functools import wraps
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

import ssl
import time

logging.basicConfig(format='%(asctime)s - CRUD - %(levelname)s - %(message)s', level=logging.INFO)

app = Flask(__name__)

app.wsgi_app = ProxyFix(
    app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
)

# Configuración de la base de datos MariaDB
app.config["MYSQL_USER"] = os.environ["MARIADB_USER"]
app.config["MYSQL_PASSWORD"] = os.environ["MARIADB_USER_PASS"]
app.config["MYSQL_DB"] = os.environ["MARIADB_DB"]
app.config["MYSQL_HOST"] = os.environ["MARIADB_SERVER"]
app.secret_key = os.environ["FLASK_SECRET_KEY"]
app.config['PERMANENT_SESSION_LIFETIME']=360

#configuración para MQTTS con Flask MQTT

app.config['MQTT_BROKER_URL'] = os.environ["SERVIDOR"]  # use the free broker from HIVEMQ
app.config['MQTT_BROKER_PORT'] = int(os.environ["PUERTO_MQTTS"])  # default port for non-tls connection
app.config['MQTT_USERNAME'] = os.environ["MQTT_USR"]  # set the username here if you need authentication for the broker
app.config['MQTT_PASSWORD'] = os.environ["MQTT_PASS"] # set the password here if the broker demands authentication
app.config['MQTT_TLS_ENABLED'] = True 
app.config['MQTT_TLS_INSECURE'] = True 
app.config['MQTT_TLS_VERSION'] = ssl.PROTOCOL_TLSv1_2  

try:
    mqtt = Mqtt(app)
    time.sleep(2) #espera para asegurar una conexión estable al broker 
    logging.info("Conexión MQTT inicializada correctamente")
except Exception as e:
    logging.error(f"Error al inicializar MQTT: {str(e)}")
    mqtt = None
mysql = MySQL(app)

# rutas

def require_login(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/registrar", methods=["GET", "POST"])
def registrar():
    if request.method == "POST":
        if not request.form.get("usuario"):
            return "El campo usuario es obligatorio"
        elif not request.form.get("password"):
            return "El campo contraseña es obligatorio"

        passhash = generate_password_hash(request.form.get("password"), method='scrypt', salt_length=16)
        cur = mysql.connection.cursor()
        try:
            cur.execute("INSERT INTO usuarios (usuario, hash) VALUES (%s,%s)", 
                       (request.form.get("usuario"), passhash[17:]))
            mysql.connection.commit()
            flash('Usuario registrado exitosamente')
            logging.info("se agregó un usuario")
            return redirect(url_for('login'))
        except Exception as e:
            flash('Error al registrar usuario')
            logging.error(f"Error al registrar usuario: {str(e)}")
            return redirect(url_for('registrar'))
        finally:
            cur.close()

    return render_template('registrar.html')

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if not request.form.get("usuario"):
            return "El campo usuario es obligatorio"
        elif not request.form.get("password"):
            return "El campo contraseña es obligatorio"

        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM usuarios WHERE usuario LIKE %s", (request.form.get("usuario"),))
        rows = cur.fetchone()
        cur.close()

        if rows and check_password_hash('scrypt:32768:8:1$' + rows[2], request.form.get("password")):
            session.permanent = True
            session["user_id"] = request.form.get("usuario")
            logging.info("se autenticó correctamente")
            return redirect(url_for('index'))
        else:
            flash('usuario o contraseña incorrecto')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/registrar_nodo', methods=['GET', 'POST'])
@require_login
def registrar_nodo():
    if request.method == 'POST':
        nodo_id = request.form.get('nodo_id')
        nombre = request.form.get('nombre')
        
        if not all([nodo_id, nombre]): #verificación de campos 
            flash('Todos los campos son obligatorios')
            return redirect(url_for('registrar_nodo'))
        
        cur = mysql.connection.cursor()
        try:
            # Obtener ID del usuario actual
            cur.execute("SELECT id FROM usuarios WHERE usuario = %s", (session.get("user_id"),))
            usuario = cur.fetchone()
            if not usuario:
                flash("Usuario no encontrado")
                return redirect(url_for('logout'))
            usuario_id = usuario[0]

            # Insertar el nodo asociado al usuario
            cur.execute('''
                INSERT INTO nodos (nodo_id, nombre, usuario_id) 
                VALUES (%s, %s, %s)
            ''', (nodo_id, nombre, usuario_id))

            mysql.connection.commit()
            flash('Nodo registrado exitosamente')
            logging.info(f"se agregó un nodo: {nodo_id}")
            return redirect(url_for('control'))
        except Exception as e:
            mysql.connection.rollback()
            flash('Error al registrar el nodo')
            logging.error(f"Error al registrar nodo: {str(e)}")
            return redirect(url_for('registrar_nodo'))
        finally:
            cur.close()
    
    return render_template('registrar_nodo.html')

@app.route('/')
@require_login
def index():
    return redirect(url_for('control'))

@app.route('/control', methods=['GET', 'POST'])
@require_login
def control(): #Control de nodos
    if request.method == 'POST':
        nodo_id = request.form.get('nodo')
        setpoint = request.form.get('setpoint')
        destello = 'destello' in request.form

        cur = mysql.connection.cursor()
        try:
            cur.execute('SELECT id FROM nodos WHERE nodo_id = %s AND usuario_id = (SELECT id FROM usuarios WHERE usuario = %s)', (nodo_id, session.get("user_id"))) #se asegura que el nodo pertenece al usuario
            result = cur.fetchone()

            if not result:
                flash('Nodo no encontrado o no autorizado')
                return redirect(url_for('control'))

            cur.execute('UPDATE nodos SET setpoint = %s WHERE id = %s', (setpoint, nodo_id)) #se actualiza el setpoint del nodo
            mysql.connection.commit()


            try:  #publicacion de setpoint y destello por MQTT
                mqtt.publish(f"{nodo_id}/setpoint", str(setpoint))
                logging.info(f"{nodo_id}")
                logging.info(f"Setpoint enviado a {nodo_id}/setpoint: {setpoint}")
                if destello:
                    mqtt.publish(f"{nodo_id}/destello","1")
                    logging.info(F"Destello enviado a {nodo_id}/destello")
            except Exception as e:
                logging.error(f"Error al publicar por MQTT: {str(e)}")
            flash(f"Comando enviado al nodo {nodo_id} - Setpoint: {setpoint} - Destello: {'Sí' if destello else 'No'}")

        except Exception as e:
            mysql.connection.rollback()
            flash('Error al actualizar el nodo')
            logging.error(f"Error al actualizar nodo: {str(e)}")
        finally:
            cur.close()

        return redirect(url_for('control'))

    # Obtener nodos del usuario actual
    cur = mysql.connection.cursor()
    cur.execute('''
        SELECT nodo_id, nombre, setpoint FROM nodos
        WHERE usuario_id = (SELECT id FROM usuarios WHERE usuario = %s)
    ''', (session.get("user_id"),))
    nodos = cur.fetchall()
    cur.close()

    return render_template('control.html', nodos=nodos)

@app.route("/logout")
@require_login
def logout():
    session.clear()
    logging.info("el usuario {} cerró su sesión".format(session.get("user_id")))
    return redirect(url_for('index'))

@app.route('/toggle_theme')
@require_login
def toggle_theme():
    current_theme = session.get('light', 'dark')
    new_theme = 'light' if current_theme == 'dark' else 'dark'
    session['light'] = new_theme
    return redirect(url_for('index'))





