from flask import Flask, render_template, request, redirect, url_for, session, flash
import pyodbc
import base64
from functools import wraps
import os
from datetime import datetime
from werkzeug.utils import secure_filename

from dotenv import load_dotenv
load_dotenv()


app = Flask(__name__)
app.secret_key = 'clave_super_secreta_1234'

# Carpeta para subir imágenes
UPLOAD_FOLDER = os.path.join('static', 'Paquetes')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


def archivo_permitido(nombre_archivo):
    return '.' in nombre_archivo and nombre_archivo.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_db_connection():
    server = os.environ.get("AZURE_SQL_SERVER")
    database = os.environ.get("AZURE_SQL_DB")
    username = os.environ.get("AZURE_SQL_USER")
    password = os.environ.get("AZURE_SQL_PASS")

    conn_str = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={username};"
        f"PWD={password};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
        "Connection Timeout=30;"
    )

    return pyodbc.connect(conn_str)

def login_requerido(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def calcular_edad(fecha_nacimiento): 
    if not fecha_nacimiento:
        return ''
    if isinstance(fecha_nacimiento, str):
        fecha_nacimiento = fecha_nacimiento.split(' ')[0]  # Por si viene con hora
        fecha_nacimiento = datetime.strptime(fecha_nacimiento, '%Y-%m-%d')
    hoy = datetime.today()
    edad = hoy.year - fecha_nacimiento.year - ((hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day))
    return edad

#Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nusuario = request.form['nusuario']
        contrasena = request.form['contrasena']
        contrasena_codificada = base64.b64encode(contrasena.encode('utf-16le')).decode()

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM Usuario WHERE NUsuario = ? AND Contraseña = ?', (nusuario, contrasena_codificada))
        print(f"Usuario: {nusuario}, Contraseña: {contrasena_codificada}")
        user = cursor.fetchone()
        conn.close()

        if user:
            session['usuario'] = user[1]
            session['tipo'] = user[4]
            return redirect(url_for('index'))
        else:
            flash('Nombre de usuario o contraseña incorrectos')
    return render_template('login.html')

# Ruta: Logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Ruta: Página principal con bienvenida
@app.route('/')
@login_requerido
def index():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Obtener productos con inventario bajo (ejemplo: menos de 10 unidades)
    cursor.execute('''
        SELECT Descripcion, Inventario
        FROM Paquete
        WHERE Inventario < 30
        ORDER BY Inventario ASC
    ''')
    alertas_stock = cursor.fetchall()

    conn.close()
    return render_template('bienvenida.html', alertas_stock=alertas_stock)



# Paquetes
@app.route('/paquetes', methods=['GET', 'POST'])
@login_requerido
def ver_paquetes():
    busqueda = request.args.get('busqueda', '').strip()
    conn = get_db_connection()
    cursor = conn.cursor()

    # Buscar paquetes
    if busqueda:
        cursor.execute('''
            SELECT *
            FROM Paquete
            WHERE Descripcion LIKE ? 
            ORDER BY Id_Paquete ASC
        ''', (f'%{busqueda}%',))
    else:
        cursor.execute('''
            SELECT *
            FROM Paquete
            ORDER BY Id_Paquete ASC
        ''')

    paquetes = cursor.fetchall()

    # Crear paquete (si POST)
    if request.method == 'POST':
        descripcion = request.form['Descripcion']
        tipo = request.form['TipoPaquete']
        inventario = request.form['Inventario']
        unidadessobrantes = request.form['UnidadesSobrantes']
        paquetescompletos = request.form['PaquetesCompletos']
        precio_venta = request.form['PrecioVenta_Paq']
        precio_compra = request.form['PrecioCompra_Paq']

        # Manejo de imagen
        imagen = request.files.get('imagen')
        if imagen and archivo_permitido(imagen.filename):
            # Limpia el nombre del archivo (quita /, \ y espacios)
            nombre_archivo = f"{descripcion.replace('/', '_')}.png"
            ruta_imagen = os.path.join(app.config['UPLOAD_FOLDER'], nombre_archivo)
            imagen.save(ruta_imagen)


        # Inserción en la BD (NO incluye imagen, como pediste)
        cursor.execute('''
            INSERT INTO Paquete (Descripcion, TipoPaquete, Inventario, UnidadesSobrantes, PaquetesCompletos, PrecioVenta_Paq, PrecioCompra_Paq)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (descripcion, tipo, inventario, unidadessobrantes, paquetescompletos, precio_venta, precio_compra))

        conn.commit()
        conn.close()
        return redirect(url_for('ver_paquetes'))

    archivos_disponibles = set(os.listdir(app.config['UPLOAD_FOLDER']))
    conn.close()
    return render_template(
        'paquetes.html',
        paquetes=paquetes,
        busqueda=busqueda,
        lookup_files=archivos_disponibles
    )

#Edicion de paquetes
@app.route('/editar_paquete/<int:id>', methods=['GET', 'POST'])
@login_requerido
def editar_paquete(id):
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        descripcion = request.form['Descripcion']
        tipo = request.form['TipoPaquete']
        inventario = request.form['Inventario']
        unidadessobrantes = request.form['UnidadesSobrantes']
        paquetescompletos = request.form['PaquetesCompletos']
        precio_venta = request.form['PrecioVenta_Paq']
        precio_compra = request.form['PrecioCompra_Paq']
        imagen = request.files.get('imagen')

        if imagen and imagen.filename != '':
            if not archivo_permitido(imagen.filename):
                flash('❌ Formato de imagen no permitido. Usa: .png, .jpg, .jpeg o .gif', 'danger')
                return redirect(url_for('editar_paquete', id=id))
    
            nombre_archivo = f"{descripcion.replace('/', '_')}.png"
            ruta_imagen = os.path.join(app.config['UPLOAD_FOLDER'], nombre_archivo)
            imagen.save(ruta_imagen)
        
        cursor.execute('''
            UPDATE Paquete
            SET Descripcion = ?, TipoPaquete = ?, Inventario = ?, UnidadesSobrantes = ?, PaquetesCompletos = ?, PrecioVenta_Paq = ?, PrecioCompra_Paq = ?
            WHERE Id_Paquete = ?
        ''', (descripcion, tipo, inventario, unidadessobrantes, paquetescompletos, precio_venta, precio_compra, id))
        conn.commit()
        conn.close()
        return redirect(url_for('ver_paquetes'))

    # Obtener paquetes para el combo
    cursor.execute('SELECT * FROM Paquete WHERE Id_Paquete = ?', (id,))
    paquete = cursor.fetchone() 

    conn.close()
    return render_template('editar_paquetes.html', paquete=paquete)



#Detalle Venta
@app.route('/detalles_ventas', methods=['GET', 'POST'])
@login_requerido
def ver_detalles_ventas():
    producto = request.args.get('producto', '').strip()
    id_venta = request.args.get('id_compra', '').strip()
    conn = get_db_connection()
    cursor = conn.cursor()

    error = None

    # Buscar detalles de ventas (por nombre de paquete si hay búsqueda)
    if producto:
        cursor.execute('''
            SELECT 
                dv.Id_DetalleVenta,
                dv.Id_Venta,
                p.Descripcion AS DescripcionPaquete,
                dv.CantidadPaquetes,
                dv.CantidadUnidades,
                dv.CantidadVendidaTotal,
                dv.PrecioUnitario,
                dv.Subtotal
            FROM DetalleVenta dv
            JOIN Paquete p ON dv.Id_Paquete = p.Id_Paquete
            WHERE p.Descripcion LIKE ?
            ORDER BY dv.Id_Venta ASC
        ''', (f'%{producto}%',))
    elif id_venta:
        cursor.execute('''
            SELECT 
                dv.Id_DetalleVenta,
                dv.Id_Venta,
                p.Descripcion AS DescripcionPaquete,
                dv.CantidadPaquetes,
                dv.CantidadUnidades,
                dv.CantidadVendidaTotal,
                dv.PrecioUnitario,
                dv.Subtotal
            FROM DetalleVenta dv
            JOIN Paquete p ON dv.Id_Paquete = p.Id_Paquete
            WHERE dv.Id_Venta LIKE ?
            ORDER BY dv.Id_Venta ASC
        ''', (f'%{id_venta}%',))
    else:
        cursor.execute('''
            SELECT 
                dv.Id_DetalleVenta,
                dv.Id_Venta,
                p.Descripcion AS DescripcionPaquete,
                dv.CantidadPaquetes,
                dv.CantidadUnidades,
                dv.CantidadVendidaTotal,
                dv.PrecioUnitario,
                dv.Subtotal
            FROM DetalleVenta dv
            JOIN Paquete p ON dv.Id_Paquete = p.Id_Paquete
            ORDER BY dv.Id_Venta ASC
        ''')
    detalles_ventas = cursor.fetchall()


    # Agregar Detalle Venta
    if request.method == 'POST':
        try:
            id_venta = int(request.form['id_venta'])
            id_paquete = int(request.form['paquete_id'])
            paquetes_finales = int(request.form['paquetes_finales'])
            unidades_finales = int(request.form['unidades_finales'])
            
            cursor.execute('''
                EXEC RegistrarCierreDeInventario ?, ?, ?, ?
            ''', (id_paquete, paquetes_finales, unidades_finales, id_venta))
            conn.commit()
            flash('Detalle de venta registrado correctamente.', 'success')
            conn.close()
            return redirect(url_for('ver_detalles_ventas'))

        except ValueError:
            error = 'Todos los campos deben contener números válidos.'
        except pyodbc.Error as e:
            error = f'Error de base de datos: {str(e)}'


    # Cargar combos: Paquetes y ventas
    cursor.execute('SELECT Id_Paquete, Descripcion, PaquetesCompletos, UnidadesSobrantes, Inventario FROM Paquete')
    paquetes = cursor.fetchall()

    cursor.execute('SELECT MAX(Id_Venta) FROM Venta')
    max_id_venta = cursor.fetchone()[0] or 1

    cursor.execute('SELECT Id_Venta, Fecha, TotalVenta FROM Venta ORDER BY Fecha DESC')
    ventas = cursor.fetchall()

    tiene_detalles = len(detalles_ventas) > 0
    conn.close()
    return render_template(
        'detalles_ventas.html',
        detalles_ventas=detalles_ventas,
        producto=producto,
        id_venta=id_venta,
        paquetes=paquetes,
        ventas=ventas,
        max_id_venta=max_id_venta,
        error=error,
        tiene_detalles=tiene_detalles
    )



@app.route('/crear_venta', methods=['POST'])
@login_requerido
def crear_venta():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('INSERT INTO Venta DEFAULT VALUES;')
        cursor.execute('SELECT SCOPE_IDENTITY();')
        nueva_venta_id = int(cursor.fetchone()[0])

        conn.commit()
        flash(f'Venta creada exitosamente. ID: {nueva_venta_id}', 'success')
        return redirect(url_for('ver_detalles_ventas'))

    except Exception as e:
        conn.rollback()
        flash(f'Ocurrió un error al crear la venta: {str(e)}', 'danger')
        return redirect(url_for('ver_detalles_ventas'))

    finally:
        cursor.close()
        conn.close()



@app.route('/editar_detalle_venta/<int:id>', methods=['GET', 'POST'])
@login_requerido
def editar_detalle_venta(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''SELECT 
                    dv.Id_DetalleVenta,
                    dv.Id_Paquete,
                    dv.Id_Venta,
                    p.PaquetesCompletos AS PaquetesCompletos,
                    p.UnidadesSobrantes AS UnidadesSobrantes,
                    p.Inventario AS Inventario,
                    p.Descripcion AS Descripcion,
                    dv.CantidadPaquetes,
                    dv.CantidadUnidades
                    FROM DetalleVenta dv
                    inner join Paquete p on dv.Id_Paquete = p.Id_Paquete
                    WHERE Id_DetalleVenta = ?''', (id,))
    detalle = cursor.fetchone()

    # Obtener paquetes para el combo
    cursor.execute('SELECT Id_Paquete, Descripcion, PaquetesCompletos, UnidadesSobrantes, Inventario FROM Paquete')
    paquetes = cursor.fetchall()

    cursor.execute('SELECT MAX(Id_Venta) FROM Venta')
    max_id_venta = cursor.fetchone()[0] or 1


    if not detalle:
        cursor.close()
        conn.close()
        flash('Detalle de venta no encontrado.', 'danger')
        return redirect(url_for('ver_detalles_ventas'))

    if request.method == 'POST':
        try:
            id_venta = int(request.form['id_venta'])
            id_paquete = int(request.form['paquete_id'])
            cantidad_paquetes = int(request.form['cantidad_paquetes'])
            cantidad_unidades = int(request.form['cantidad_unidades'])
            # Si quieres actualizar precio unitario y subtotal, también agregar aquí y en el form

            # Actualizamos solo los campos que sí están en DetalleVenta
            cursor.execute('''
                UPDATE DetalleVenta
                SET Id_Venta = ?, Id_Paquete = ?, CantidadPaquetes = ?, CantidadUnidades = ?
                WHERE Id_DetalleVenta = ?
            ''', (id_venta, id_paquete, cantidad_paquetes, cantidad_unidades, id))

            conn.commit()
            flash('Detalle de venta actualizado correctamente.', 'success')
            return redirect(url_for('ver_detalles_ventas'))

        except Exception as e:
            flash(f'Error al actualizar el detalle: {str(e)}', 'danger')


    cursor.close()
    conn.close()

    return render_template(
        'editar_detalle_venta.html',
        detalle=detalle,
        paquetes=paquetes,
        max_id_venta=max_id_venta)

""" @app.route('/eliminar_detalle_venta/<int:id>', methods=['POST'])
@login_requerido
def eliminar_detalle_venta(id):
    print(id)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM DetallesDeVentas WHERE Id_DetallesDeVentas = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('ver_detalles_ventas'))

 """

@app.route('/detalles_compras',methods=['GET', 'POST'])
@login_requerido
def ver_detalles_compras():
    producto = request.args.get('producto', '').strip()
    id_compra = request.args.get('id_compra', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    # Filtro según búsqueda
    if producto:
        cursor.execute('''
            SELECT 
                dc.Id_DetalleDeCompra,
                dc.Id_Compra,
                dc.Cantidad,
                dc.PrecioAntDes,
                dc.TotalAntDes,
                dc.DescuentoTotal,
                dc.TotalConDes,
                dc.TotalConIva,
                p.Descripcion AS DescripcionPaquete
            FROM DetallesDeCompras dc
            JOIN Paquete p ON dc.Id_Paquete = p.Id_Paquete
            WHERE p.Descripcion LIKE ?
            ORDER BY Id_Compra ASC
        ''', (f'%{producto}%',))
    elif id_compra:
        cursor.execute('''
            SELECT 
                dc.Id_DetalleDeCompra,
                dc.Id_Compra,
                dc.Cantidad,
                dc.PrecioAntDes,
                dc.TotalAntDes,
                dc.DescuentoTotal,
                dc.TotalConDes,
                dc.TotalConIva,
                p.Descripcion AS DescripcionPaquete
            FROM DetallesDeCompras dc
            JOIN Paquete p ON dc.Id_Paquete = p.Id_Paquete
            WHERE dc.Id_Compra = ?
            ORDER BY Id_Compra ASC
        ''', (id_compra,))
    else:
        cursor.execute('''
            SELECT 
                dc.Id_DetalleDeCompra,
                dc.Id_Compra,
                dc.Cantidad,
                dc.PrecioAntDes,
                dc.TotalAntDes,
                dc.DescuentoTotal,
                dc.TotalConDes,
                dc.TotalConIva,
                p.Descripcion AS DescripcionPaquete
            FROM DetallesDeCompras dc
            JOIN Paquete p ON dc.Id_Paquete = p.Id_Paquete
            ORDER BY Id_Compra ASC
        ''')

    detalles = cursor.fetchall()

    # Crear detalle de compra
    if request.method == 'POST':
        id_compra = request.form['id_compra']
        id_paquete = request.form['paquete_id']
        cantidad = request.form['cantidad']


        cursor.execute('''
            INSERT INTO DetallesDeCompras (Id_Compra, Id_Paquete, Cantidad)
            VALUES (?, ?, ?)
        ''', (id_compra, id_paquete, cantidad))
        conn.commit()
        conn.close()
        return redirect(url_for('ver_detalles_compras'))

    # Obtener paquetes para el combo
    cursor.execute('SELECT Id_Paquete, Descripcion FROM Paquete')
    paquetes = cursor.fetchall()

    # Obtener el máximo Id_Compra de DetallesDeCompras
    cursor.execute('SELECT MAX(Id_Compra) FROM Compras')
    max_id_compra = cursor.fetchone()[0] or 1  # Si no hay registros, usa 1


    # Ver compras
    cursor.execute('''
        SELECT c.Id_Compra, c.FechaDeCompra, p.CompanyName,ISNULL(SUM(dc.TotalConIva), 0) AS TotalFactura
        FROM Compras c
        JOIN Company p ON c.Id_Company = p.Id_Company
        LEFT JOIN DetallesDeCompras dc ON c.Id_Compra = dc.Id_Compra
        GROUP BY c.Id_Compra, c.FechaDeCompra, p.CompanyName
        ORDER BY c.FechaDeCompra asc
    ''')
    compras = cursor.fetchall()



    conn.close()
    return render_template(
        'detalles_compras.html', 
        detalles_compras=detalles, 
        paquetes=paquetes, 
        compras=compras, 
        max_id_compra=max_id_compra)


# Editar detalle de compra
@app.route('/editar_detalle_compra/<int:id>', methods=['GET', 'POST'])
@login_requerido
def editar_detalle_compra(id):
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        id_compra = request.form['Id_Compra']
        id_paquete = request.form['Id_Paquete']
        cantidad = request.form['Cantidad']

        cursor.execute('''
            UPDATE DetallesDeCompras
            SET Id_Compra = ?, Id_Paquete = ?, Cantidad = ?
            WHERE Id_DetalleDeCompra = ?
        ''', (id_compra, id_paquete, cantidad, id))
        conn.commit()
        conn.close()
        return redirect(url_for('ver_detalles_compras'))

    cursor.execute('SELECT * FROM DetallesDeCompras WHERE Id_DetalleDeCompra = ?', (id,))
    detalle = cursor.fetchone()

    # Obtener paquetes para el combo
    cursor.execute('SELECT Id_Paquete, Descripcion FROM Paquete')
    paquetes = cursor.fetchall()

    # Obtener el máximo Id_Compra de DetallesDeCompras
    cursor.execute('SELECT MAX(Id_Compra) FROM Compras')
    max_id_compra = cursor.fetchone()[0] or 1  # Si no hay registros, usa 1

    conn.close()
    return render_template('editar_detalle_compra.html', detalle=detalle, paquetes=paquetes, max_id_compra=max_id_compra )

""" #Eliminar detalle de compra
@app.route('/eliminar_detalle_compra/<int:id>', methods=['POST'])
@login_requerido
def eliminar_detalle_compra(id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('DELETE FROM DetallesDeCompras WHERE Id_DetalleDeCompra = ?', (id,))
    conn.commit()
    conn.close()
    
    flash('Detalle de compra eliminado correctamente.', 'success')
    return redirect(url_for('ver_detalles_compras'))
 """

# Crear compra automáticamente con fecha actual
@app.route('/crear_compra', methods=['POST'])
@login_requerido
def crear_compra():
    proveedor_id = 1  # o dinámico si lo necesitás
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO Compras (FechaDeCompra, Id_Proveedor) VALUES (GETDATE(), ?)", (proveedor_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('ver_detalles_compras'))




@app.route('/empleados', methods=['GET', 'POST'])
@login_requerido
def ver_empleados():
    busqueda = request.args.get('busqueda', '').strip()
    conn = get_db_connection()
    cursor = conn.cursor()

    # Buscar empleados
    if busqueda:
        cursor.execute('''
            SELECT 
                e.Id_Empleado,
                e.Nombres,
                e.Apellidos,
                e.FechaDeNacimiento,
                e.FechaDeContrato,
                e.Direccion,
                e.Region,
                s.Nombres AS NombreSupervisor,
                s.Apellidos AS ApellidoSupervisor
            FROM Empleado e
            LEFT JOIN Empleado s ON e.Supervisor = s.Id_Empleado
            WHERE e.Nombres LIKE ? OR e.Apellidos LIKE ? OR e.Region LIKE ?
            ORDER BY e.Id_Empleado ASC
        ''', (f'%{busqueda}%', f'%{busqueda}%', f'%{busqueda}%'))
    else:
        cursor.execute('''
            SELECT 
                e.Id_Empleado,
                e.Nombres,
                e.Apellidos,
                e.FechaDeNacimiento,
                e.FechaDeContrato,
                e.Direccion,
                e.Region,
                s.Nombres AS NombreSupervisor,
                s.Apellidos AS ApellidoSupervisor
            FROM Empleado e
            LEFT JOIN Empleado s ON e.Supervisor = s.Id_Empleado
            ORDER BY e.Id_Empleado ASC
        ''')

    columnas = [col[0] for col in cursor.description]
    empleados = [dict(zip(columnas, fila)) for fila in cursor.fetchall()]
    for emp in empleados:
        emp['Edad'] = calcular_edad(emp['FechaDeNacimiento'])

    # Crear empleado (si POST)
    if request.method == 'POST':
        nombres = request.form['nombres']
        apellidos = request.form['apellidos']
        fecha_nacimiento = request.form['fecha_nacimiento']
        fecha_contrato = request.form['fecha_contrato']
        direccion = request.form['direccion']
        region = request.form['region']
        supervisor = request.form['supervisor'] or None  # Puede ser None si no hay supervisor

        cursor.execute('''
            INSERT INTO Empleado (Nombres, Apellidos, FechaDeNacimiento, FechaDeContrato, Direccion, Supervisor, Region)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (nombres, apellidos, fecha_nacimiento, fecha_contrato, direccion, supervisor, region))
        conn.commit()
        conn.close()
        return redirect(url_for('ver_empleados'))

    # Obtener supervisores para el combo
    cursor.execute('SELECT Id_Empleado, Nombres, Apellidos FROM Empleado')
    supervisores = cursor.fetchall()

    conn.close()
    return render_template(
        'empleados.html',
        empleados=empleados,
        busqueda=busqueda,
        supervisores=supervisores
    )


@app.route('/editar_empleado/<int:id>', methods=['GET', 'POST'])
@login_requerido
def editar_empleado(id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Obtener el empleado como tupla
    cursor.execute('SELECT * FROM Empleado WHERE Id_Empleado = ?', (id,))
    empleado = cursor.fetchone()

    # Obtener supervisores para el combo (excluyendo el mismo empleado)
    cursor.execute('SELECT Id_Empleado, Nombres, Apellidos FROM Empleado WHERE Id_Empleado != ?', (id,))
    supervisores = cursor.fetchall()

    if not empleado:
        conn.close()
        flash('Empleado no encontrado.', 'danger')
        return redirect(url_for('ver_empleados'))

    if request.method == 'POST':
        nombres = request.form['nombres']
        apellidos = request.form['apellidos']
        fecha_nacimiento = request.form['fecha_nacimiento']
        fecha_contrato = request.form['fecha_contrato']
        direccion = request.form['direccion']
        region = request.form['region']
        supervisor = request.form['supervisor'] or None

        cursor.execute('''
            UPDATE Empleado
            SET Nombres=?, Apellidos=?, FechaDeNacimiento=?, FechaDeContrato=?, Direccion=?, Supervisor=?, Region=?
            WHERE Id_Empleado=?
        ''', (nombres, apellidos, fecha_nacimiento, fecha_contrato, direccion, supervisor, region, id))
        conn.commit()
        conn.close()
        return redirect(url_for('ver_empleados'))

    conn.close()
    return render_template('editar_empleado.html', empleado=empleado, supervisores=supervisores)


#Ganancia Diaria
@app.route('/ganancia_diaria')
@login_requerido
def ganancia_diaria():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Traer todas las ganancias
    cursor.execute('''
        SELECT gd.Id_Venta, gd.Fecha, gd.TotalVenta, gd.GananciaCalculada
        FROM GananciaDiaria gd
        ORDER BY gd.Id_Venta ASC
    ''')
    ganancias = cursor.fetchall()

    # Obtener ventas disponibles para mostrar o calcular
    cursor.execute('SELECT Id_Venta FROM Venta ORDER BY Id_Venta ASC')
    ventas = cursor.fetchall()

    fechas = [row.Fecha.strftime('%Y-%m-%d') for row in ganancias if row.GananciaCalculada is not None]
    valores = [float(row.GananciaCalculada) for row in ganancias if row.GananciaCalculada is not None]

    conn.close()
    return render_template('ganancia_diaria.html', ganancias=ganancias, ventas=ventas,fechas=fechas,
    valores=valores)


@app.route('/calcular_ganancia/<int:id_venta>', methods=['POST'])
@login_requerido
def calcular_ganancia(id_venta):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('EXEC CalcularGananciaDiaria ?', (id_venta,))
        conn.commit()
        flash(f'Ganancia calculada para venta #{id_venta}', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Error al calcular ganancia: {str(e)}', 'danger')
    finally:
        conn.close()

    return redirect(url_for('ganancia_diaria'))


#Ejecucion

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)