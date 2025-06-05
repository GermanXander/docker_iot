from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_mysqldb import MySQL
import os, logging
from functools import wraps
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

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
        sensor_id = request.form.get('sensor_id')
        nombre = request.form.get('nombre')
        broker_id = request.form.get('broker_id')
        
        if not all([sensor_id, nombre, broker_id]):
            flash('Todos los campos son obligatorios')
            return redirect(url_for('registrar_nodo'))

        cur = mysql.connection.cursor()
        try:
            # Insertar el nodo
            cur.execute('''
                INSERT INTO nodos (sensor_id, nombre, broker_id) 
                VALUES (%s, %s, %s)
            ''', (sensor_id, nombre, broker_id))
            
            # Obtener el ID del nodo insertado
            nodo_id = cur.lastrowid
            
            # Asignar el nodo al usuario actual
            cur.execute('''
                INSERT INTO usuarios_nodos (usuario_id, nodo_id)
                SELECT id, %s FROM usuarios WHERE usuario = %s
            ''', (nodo_id, session.get("user_id")))
            
            mysql.connection.commit()
            flash('Nodo registrado exitosamente')
            logging.info(f"se agregó un nodo: {sensor_id}")
            return redirect(url_for('control'))
        except Exception as e:
            mysql.connection.rollback()
            flash('Error al registrar el nodo')
            logging.error(f"Error al registrar nodo: {str(e)}")
            return redirect(url_for('registrar_nodo'))
        finally:
            cur.close()

    # Obtener lista de brokers disponibles
    cur = mysql.connection.cursor()
    cur.execute('SELECT id, nombre, host FROM brokers_mqtt WHERE is_active = TRUE')
    brokers = cur.fetchall()
    cur.close()
    
    return render_template('registrar_nodo.html', brokers=brokers)

@app.route('/')
@require_login
def index():
    return redirect(url_for('control'))

@app.route('/control', methods=['GET', 'POST'])
@require_login
def control():
    if request.method == 'POST':
        node_id = request.form.get('nodo')
        setpoint = request.form.get('setpoint')
        destello = 'destello' in request.form
        cur = mysql.connection.cursor()
        cur.execute('UPDATE nodos SET setpoint = %s, destello = %s WHERE id = %s', (setpoint, destello, node_id))
        mysql.connection.commit()
        cur.close()

        flash(f"Comando enviado al nodo {node_id} - Setpoint: {setpoint} - Destello: {'Sí' if destello else 'No'}")
        return redirect(url_for('control'))
    
    # Obtener los nodos a los que el usuario tiene acceso
    cur = mysql.connection.cursor()
    cur.execute('''
        SELECT n.id, n.sensor_id, n.nombre, n.setpoint, n.destello, b.nombre as broker_nombre
        FROM nodos n
        JOIN usuarios_nodos un ON n.id = un.nodo_id
        JOIN usuarios u ON un.usuario_id = u.id
        JOIN brokers_mqtt b ON n.broker_id = b.id
        WHERE u.usuario = %s AND n.is_active = TRUE
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





