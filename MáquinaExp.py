import os
import sqlite3
from datetime import datetime
from typing import List

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
import fastapi.middleware.cors
app = FastAPI()

# Origen permitido
origins = [
    "http://localhost:8000",
    "http://localhost:5501",  # Agrega aquí el puerto de tu frontend si es diferente
]
# Configurar el middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permitir cualquier origen
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # Agrega OPTIONS aquí
    allow_headers=["*"],
)




def obtener_directorio_actual():
    return os.path.dirname(os.path.realpath(__file__))


try:
    directorio_actual = obtener_directorio_actual()
    ruta_db = os.path.join(directorio_actual, "registro.db")

    conexion = sqlite3.connect(ruta_db)
    cursor = conexion.cursor()

    cursor.execute('''CREATE TABLE IF NOT EXISTS maquinas (
                        serial INTEGER PRIMARY KEY,
                        ubicacion TEXT,
                        direccion TEXT,  -- Nuevo campo para la dirección
                        estado TEXT DEFAULT 'apagada'
                      )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS productos (
                        num_serie INTEGER PRIMARY KEY,
                        nombre TEXT,
                        precio REAL
                      )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS ventas (
                        id INTEGER PRIMARY KEY,
                        serie_maquina INTEGER,
                        num_serie INTEGER,
                        nombre_producto TEXT,
                        monto REAL,
                        cantidad INTEGER,
                        fecha TEXT,
                        FOREIGN KEY (serie_maquina) REFERENCES maquinas (serial),
                        FOREIGN KEY (num_serie) REFERENCES productos (num_serie)
                      )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS resurtidos (
                    id INTEGER PRIMARY KEY,
                    serie_maquina INTEGER,
                    num_serie INTEGER,
                    cantidad INTEGER,
                    fecha TEXT,
                    num_slot INTEGER,
                    FOREIGN KEY (serie_maquina) REFERENCES maquinas (serial),
                    FOREIGN KEY (num_serie) REFERENCES productos (num_serie)
                  )''')


    cursor.execute('''CREATE TABLE IF NOT EXISTS incidencias (
                        id INTEGER PRIMARY KEY,
                        descripcion TEXT,
                        serie_maquina INTEGER,
                        fecha TEXT,
                        FOREIGN KEY (serie_maquina) REFERENCES maquinas (serial)
                      )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS solicitudes_relleno (
                        id INTEGER PRIMARY KEY,
                        id_informe INTEGER,
                        num_serie_maquina INTEGER,
                        productos_restantes INTEGER,
                        fecha TEXT,
                        hora TEXT
                      )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS slots (
                    id INTEGER PRIMARY KEY,
                    serial_maquina INTEGER,
                    num_slot INTEGER,
                    capacidad_maxima INTEGER,
                    FOREIGN KEY (serial_maquina) REFERENCES maquinas (serial)
                  )''')


    cursor.execute("INSERT INTO productos (nombre, precio) VALUES (?, ?)", ("Soles", 15.5))
    cursor.execute("INSERT INTO productos (nombre, precio) VALUES (?, ?)", ("Gansito", 19.5))
    cursor.execute("INSERT INTO productos (nombre, precio) VALUES (?, ?)", ("Donas Bimbo", 15.0))

    conexion.commit()

    cursor.close()
    conexion.close()
except Exception as e:
    print("Error al conectar y crear la base de datos:", e)

class Producto(BaseModel):
    num_serie:int
    nombre:str
    precio: float

class Slot(BaseModel):
    num_slot: int
    productos: List[Producto] = []
    capacidad_maxima: int

class MaquinaExpendedora(BaseModel):
    serial: int
    ubicacion: str
    direccion: str
    estado: str
    num_slots: int = 30  # Definir num_slots como una variable de clase con un valor predeterminado
    capacidad_por_slot: int = 10
    slots: List[Slot] = []

class Venta(BaseModel):
    id_maquina: int
    num_serie: int
    cantidad: int = 1
    num_slot: Optional[int] = None

class Incidencia(BaseModel):
    id: int
    descripcion: str
    serie_maquina: int
    nombre_persona: str

@app.get("/maquinas/{serial}/estado")
async def obtener_informacion_maquina(serial: int):
    try:
        conexion = sqlite3.connect(ruta_db)
        cursor = conexion.cursor()

        cursor.execute("SELECT serial, ubicacion, direccion, estado FROM maquinas WHERE serial=?", (serial,))
        maquina_info = cursor.fetchone()
        if not maquina_info:
            raise HTTPException(status_code=404, detail="La máquina no existe")

        cursor.execute("SELECT p.num_serie, p.nombre, p.precio, r.cantidad, r.num_slot FROM productos p "
                       "INNER JOIN resurtidos r ON p.num_serie = r.num_serie AND r.serie_maquina = ?", (serial,))
        productos = [{"num_serie": row[0], "nombre": row[1], "precio": row[2], "cantidad": row[3], "num_slot": row[4]}
                     for row in cursor.fetchall()]

        cursor.execute("SELECT num_slot, capacidad_maxima FROM slots WHERE serial_maquina=?", (serial,))
        slots_info = cursor.fetchall()

        cursor.execute("SELECT id, descripcion, fecha FROM incidencias WHERE serie_maquina=?", (serial,))
        incidencias = [{"id": row[0], "descripcion": row[1], "fecha": row[2]} for row in cursor.fetchall()]

        cursor.execute("SELECT * FROM solicitudes_relleno WHERE num_serie_maquina=?", (serial,))
        solicitudes_relleno = [{"id_informe": row[0], "num_serie_maquina": row[2], "productos_restantes": row[3], "fecha": row[4], "hora": row[5]} for row in cursor.fetchall()]

        cursor.execute("SELECT SUM(monto) AS ganancia_total FROM ventas WHERE serie_maquina=?", (serial,))
        ganancia_total_venta = cursor.fetchone()[0] or 0
        cursor.close()
        conexion.close()

        num_slots = len(slots_info)
        capacidad_por_slot = sum(slot[1] for slot in slots_info) if slots_info else 0

        maquina_info_dict = {
            "serial": maquina_info[0],
            "ubicacion": maquina_info[1],
            "direccion": maquina_info[2],
            "estado": maquina_info[3],
            "productos": productos,
            "numero_de_slots": num_slots,
            "capacidad_de_cada_slot": capacidad_por_slot,
            "incidencias": incidencias,
            "ganancia_total_ventas": ganancia_total_venta,
            "solicitudes_relleno": solicitudes_relleno
        }
        return maquina_info_dict

    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=str(e))





 

@app.post("/maquinas/{serial}")
async def crear_maquina(serial: int, ubicacion: str, direccion: str):
    try:
        # Crear una instancia de MaquinaExpendedora
        maquina_expendedora = MaquinaExpendedora(serial=serial, ubicacion=ubicacion, direccion=direccion, estado='apagada')

        conexion = sqlite3.connect(ruta_db)
        cursor = conexion.cursor()

        # Verificar si ya existe una máquina con el mismo ID serial
        cursor.execute("SELECT * FROM maquinas WHERE serial=?", (serial,))
        maquina_existente = cursor.fetchone()
        if maquina_existente:
            raise HTTPException(status_code=400, detail="Máquina ya existente, pruebe otro ID serial.")

        # Si no existe, crear la máquina y sus slots utilizando los valores predeterminados
        cursor.execute("INSERT INTO maquinas (serial, ubicacion, direccion) VALUES (?, ?, ?)",
                       (maquina_expendedora.serial, maquina_expendedora.ubicacion, maquina_expendedora.direccion))
        for num in range(maquina_expendedora.num_slots):
            cursor.execute("INSERT INTO slots (serial_maquina, num_slot, capacidad_maxima) VALUES (?, ?, ?)",
                           (maquina_expendedora.serial, num, maquina_expendedora.capacidad_por_slot))

        conexion.commit()
        return {"mensaje": "Máquina registrada correctamente", "serial": maquina_expendedora.serial}
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conexion.close()
        







# Método para encender una máquina
@app.post("/encender_maquina/{serial}")
async def encender_maquina(serial: int):
    try:
        conexion = sqlite3.connect(ruta_db)
        cursor = conexion.cursor()
        cursor.execute("SELECT * FROM maquinas WHERE serial=?", (serial,))
        maquina = cursor.fetchone()
        if maquina:
            cursor.execute("UPDATE maquinas SET estado='encendida' WHERE serial=?", (serial,))
            conexion.commit()
            cursor.close()
            conexion.close()
            return {"mensaje": "Máquina encendida"}
        else:
            raise HTTPException(status_code=404, detail="La máquina no existe")
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=str(e))


# Método para apagar una máquina
@app.post("/apagar_maquina/{serial}")
async def apagar_maquina(serial: int):
    try:
        conexion = sqlite3.connect(ruta_db)
        cursor = conexion.cursor()
        cursor.execute("SELECT * FROM maquinas WHERE serial=?", (serial,))
        maquina = cursor.fetchone()
        if maquina:
            cursor.execute("UPDATE maquinas SET estado='apagada' WHERE serial=?", (serial,))
            conexion.commit()
            cursor.close()
            conexion.close()
            return {"mensaje": "Máquina apagada correctamente"}
        else:
            raise HTTPException(status_code=404, detail="La máquina no existe")
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=str(e))


# Método para eliminar una máquina
@app.delete("/maquinas/{serial}")
async def eliminar_maquina(serial: int):
    try:
        conexion = sqlite3.connect(ruta_db)
        cursor = conexion.cursor()
        
        # Verificar si la máquina existe
        cursor.execute("SELECT * FROM maquinas WHERE serial=?", (serial,))
        maquina = cursor.fetchone()
        if not maquina:
            raise HTTPException(status_code=404, detail="La máquina no existe")
        
        # Eliminar la máquina
        cursor.execute("DELETE FROM maquinas WHERE serial=?", (serial,))
        conexion.commit()
        
        return {"mensaje": "Máquina eliminada correctamente"}
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conexion.close()
        

        


@app.get("/productos/{serial_maquina}")
async def leer_productos(serial_maquina: int):
    try:
        conexion = sqlite3.connect(ruta_db)
        cursor = conexion.cursor()
        cursor.execute("SELECT p.num_serie, p.nombre, p.precio, r.cantidad, r.num_slot \
                        FROM productos p \
                        INNER JOIN resurtidos r ON p.num_serie = r.num_serie AND r.serie_maquina = ?",
                       (serial_maquina,))
        resultados = cursor.fetchall()
        
        # Calcular la cantidad total de productos en la máquina
        cursor.execute("SELECT SUM(cantidad) FROM resurtidos WHERE serie_maquina=?", (serial_maquina,))
        cantidad_total = cursor.fetchone()[0] or 0  # Si no hay resultados, establecer la cantidad total en 0
        
        cursor.close()
        conexion.close()
        
        if resultados:
            return {"productos": [{"num_serie": row[0], "nombre": row[1], "precio": row[2], "cantidad": row[3], "num_slot": row[4]} for row in resultados],
                    "cantidad total de productos": cantidad_total}
        else:
            raise HTTPException(status_code=404, detail="No se encontraron productos para esta máquina.")
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    


@app.post("/resurtir/")
async def resurtir_producto(serie_maquina: int, num_serie: int, cantidad: int, num_slot: int):
    try:
        conexion = sqlite3.connect(ruta_db)
        cursor = conexion.cursor()
        
        # Verificar si ya existe un registro para este producto en el mismo slot
        cursor.execute("SELECT * FROM resurtidos WHERE serie_maquina=? AND num_serie=? AND num_slot=?", 
                       (serie_maquina, num_serie, num_slot))
        producto_existente = cursor.fetchone()
        
        if producto_existente:
            # Si ya existe, actualizar la cantidad
            cursor.execute("UPDATE resurtidos SET cantidad = cantidad + ? WHERE serie_maquina = ? AND num_serie = ? AND num_slot = ?",
                           (cantidad, serie_maquina, num_serie, num_slot))
        else:
            # Si no existe, insertar un nuevo registro
            cursor.execute("INSERT INTO resurtidos (serie_maquina, num_serie, cantidad, fecha, num_slot) VALUES (?, ?, ?, ?, ?)",
                           (serie_maquina, num_serie, cantidad, datetime.now(), num_slot))
        
        conexion.commit()
        return {"mensaje": "Productos resurtidos correctamente en el slot especificado"}
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conexion.close()





    


        





# Rutas para obtener información de las ventas
@app.get("/MontoMensualMasAlto/")
async def ingreso_mensual_mas_alto():
    try:
        conexion = sqlite3.connect(ruta_db)
        cursor = conexion.cursor()
        cursor.execute("SELECT serie_maquina, SUM(monto) AS total FROM ventas GROUP BY serie_maquina ORDER BY total DESC LIMIT 1")
        resultado = cursor.fetchone()
        cursor.close()
        conexion.close()
        if resultado:
            id_maquina_mas_alta = resultado[0]
            monto_total_mas_alto = resultado[1]
            return {"id_maquina": id_maquina_mas_alta, "monto_total": monto_total_mas_alto}
        else:
            return {"mensaje": "No hay datos de ventas"}
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/MontoMensualMasBajo/")
async def ingreso_mensual_mas_bajo():
    try:
        conexion = sqlite3.connect(ruta_db)
        cursor = conexion.cursor()
        cursor.execute("SELECT serie_maquina, SUM(monto) AS total FROM ventas GROUP BY serie_maquina ORDER BY total ASC LIMIT 1")
        resultado = cursor.fetchone()
        cursor.close()
        conexion.close()
        if resultado:
            id_maquina_mas_baja = resultado[0]
            monto_total_mas_bajo = resultado[1]
            return {"id_maquina": id_maquina_mas_baja, "monto_total": monto_total_mas_bajo}
        else:
            return {"mensaje": "No hay datos de ventas"}
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    
# Gestion para información de las ventas
@app.get("/ganancia-total-ventas/{serial_maquina}")
async def obtener_ganancia_total_ventas(serial_maquina: int):
    try:
        conexion = sqlite3.connect(ruta_db)
        cursor = conexion.cursor()

        cursor.execute("SELECT SUM(monto) AS ganancia_total FROM ventas WHERE serie_maquina=?", (serial_maquina,))
        ganancia_total_venta = cursor.fetchone()[0] or 0

        cursor.close()
        conexion.close()

        return {"ganancia_total_ventas": ganancia_total_venta}
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=str(e))



from fastapi import HTTPException

@app.post("/incidencias/")
async def crear_incidencia(descripcion: str, serie_maquina: int, nombre_persona: str):
    try:
        conexion = sqlite3.connect(ruta_db)
        cursor = conexion.cursor()
        
        # Verificar si la máquina existe
        cursor.execute("SELECT * FROM maquinas WHERE serial=?", (serie_maquina,))
        maquina = cursor.fetchone()
        if not maquina:
            raise HTTPException(status_code=404, detail="La máquina no existe")
        
        # Registrar la incidencia
        fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO incidencias (descripcion, serie_maquina, fecha, nombre_persona) VALUES (?, ?, ?, ?)",
                       (descripcion, serie_maquina, fecha_actual, nombre_persona))
        conexion.commit()
        
        # Obtener el ID de la incidencia recién insertada
        id_incidencia = cursor.lastrowid
        
        cursor.close()
        conexion.close()
        
        return {"mensaje": "Incidencia registrada", "id_incidencia": id_incidencia}
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=str(e))






@app.delete("/incidencias/{id_maquina}")
async def eliminar_incidencia(id_maquina: int):
    try:
        conexion = sqlite3.connect(ruta_db)
        cursor = conexion.cursor()
        
        # Verificar si la máquina existe
        cursor.execute("SELECT * FROM maquinas WHERE serial=?", (id_maquina,))
        maquina = cursor.fetchone()
        if not maquina:
            raise HTTPException(status_code=404, detail="La máquina no existe")
        
        # Eliminar todas las incidencias asociadas a la máquina
        cursor.execute("DELETE FROM incidencias WHERE serie_maquina=?", (id_maquina,))
        conexion.commit()
        
        return {"mensaje": "Todas las incidencias asociadas a la máquina han sido eliminadas"}
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conexion.close()
@app.get("/incidencias/")
async def leer_incidencias():
    try:
        conexion = sqlite3.connect(ruta_db)
        cursor = conexion.cursor()
        cursor.execute("SELECT * FROM incidencias")
        resultados = cursor.fetchall()
        
        cursor.close()
        conexion.close()
        
        return [{"id": row[0], "descripcion": row[1], "id_maquina": row[2], "fecha": row[3], "nombre_persona": row[4]} for row in resultados]
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/productos/")
async def crear_producto(producto: Producto):
    try:
        conexion = sqlite3.connect(ruta_db)
        cursor = conexion.cursor()

        # Verificar si el número de serie ya existe en la base de datos
        cursor.execute("SELECT * FROM productos WHERE num_serie=?", (producto.num_serie,))
        producto_existente = cursor.fetchone()
        if producto_existente:
            raise HTTPException(status_code=400, detail="El número de serie ya existe")

        # Insertar el producto en la tabla de productos
        cursor.execute("INSERT INTO productos (num_serie, nombre, precio) VALUES (?, ?, ?)",
                       (producto.num_serie, producto.nombre, producto.precio))
        conexion.commit()

        return {"mensaje": "Producto creado correctamente"}
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conexion.close()

# Eliminar producto por número de serie
@app.delete("/productos/{num_serie}")
async def eliminar_producto(num_serie: str):
    try:
        conexion = sqlite3.connect(ruta_db)
        cursor = conexion.cursor()

        # Verificar si el producto existe
        cursor.execute("SELECT * FROM productos WHERE num_serie=?", (num_serie,))
        producto = cursor.fetchone()
        if not producto:
            raise HTTPException(status_code=404, detail="El producto no existe")

        # Eliminar el producto
        cursor.execute("DELETE FROM productos WHERE num_serie=?", (num_serie,))
        conexion.commit()

        return {"mensaje": "Producto eliminado correctamente"}
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conexion.close()

# Modificar producto por número de serie
@app.put("/productos/{num_serie}")
async def modificar_producto(num_serie: str, nuevo_producto: Producto):
    try:
        conexion = sqlite3.connect(ruta_db)
        cursor = conexion.cursor()

        # Verificar si el producto existe
        cursor.execute("SELECT * FROM productos WHERE num_serie=?", (num_serie,))
        producto_existente = cursor.fetchone()
        if not producto_existente:
            raise HTTPException(status_code=404, detail="El producto no existe")

        # Modificar el producto
        cursor.execute("UPDATE productos SET nombre=?, precio=? WHERE num_serie=?",
                       (nuevo_producto.nombre, nuevo_producto.precio, num_serie))
        conexion.commit()

        return {"mensaje": "Producto modificado correctamente"}
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conexion.close()


  

# Endpoint para realizar una venta
@app.post("/venta/")
async def realizar_venta(venta: Venta):
    try:
        # Verificar si la máquina existe y está encendida
        conexion = sqlite3.connect(ruta_db)
        cursor = conexion.cursor()
        cursor.execute("SELECT estado FROM maquinas WHERE serial=?", (venta.id_maquina,))
        estado_maquina = cursor.fetchone()
        cursor.close()
        conexion.close()
        
        if estado_maquina is None:
            raise HTTPException(status_code=404, detail="La máquina no existe")
        elif estado_maquina[0] == 'apagada':
            raise HTTPException(status_code=400, detail="La máquina está apagada, no se puede realizar la venta")
        
        # Verificar si el producto existe en la máquina
        conexion = sqlite3.connect(ruta_db)
        cursor = conexion.cursor()
        cursor.execute("SELECT cantidad FROM resurtidos WHERE serie_maquina=? AND num_serie=?", 
                       (venta.id_maquina, venta.num_serie))
        cantidad_producto = cursor.fetchone()
        
        if cantidad_producto is None or cantidad_producto[0] < venta.cantidad:
            raise HTTPException(status_code=404, detail="El producto no está disponible en la cantidad solicitada")
        
        # Calcular el monto total de la venta
        cursor.execute("SELECT precio FROM productos WHERE num_serie=?", (venta.num_serie,))
        precio_producto = cursor.fetchone()
        
        if precio_producto is None:
            raise HTTPException(status_code=404, detail="El producto no existe")
        
        monto_total = precio_producto[0] * venta.cantidad
        
        # Registrar la venta
        cursor.execute("INSERT INTO ventas (serie_maquina, num_serie, nombre_producto, monto, cantidad, fecha) VALUES (?, ?, ?, ?, ?, ?)",
                       (venta.id_maquina, venta.num_serie, venta.num_serie, monto_total, venta.cantidad, datetime.now()))
        
        # Restar la cantidad de productos vendidos de la máquina
        cursor.execute("UPDATE resurtidos SET cantidad = cantidad - ? WHERE serie_maquina = ? AND num_serie = ?", 
                       (venta.cantidad, venta.id_maquina, venta.num_serie))
        
        conexion.commit()
        cursor.close()
        conexion.close()
        
        return {"mensaje": "Venta realizada exitosamente", "monto_total": monto_total}
        
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=str(e))


# Endpoint para la solicitud de relleno
@app.post("/solicitud-relleno-por-maquina/")
async def solicitud_relleno_por_Maquina(num_serie_maquina: int, productos_restantes: int, fecha: str, hora: str):
    try:
        conexion = sqlite3.connect(ruta_db)
        cursor = conexion.cursor()

        if productos_restantes < 0 or productos_restantes > 100:
            raise HTTPException(status_code=400, detail="La cantidad de productos restantes debe estar entre 0 y 100.")
        
        porcentaje_restante = (productos_restantes / 100) * 100

        # Registrar la solicitud de relleno
        cursor.execute("INSERT INTO solicitudes_relleno (num_serie_maquina, productos_restantes, fecha, hora) VALUES (?, ?, ?, ?)",
                       (num_serie_maquina, productos_restantes, fecha, hora))
        conexion.commit()
        
        return {"mensaje": "Solicitud de relleno registrada correctamente"}
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conexion.close()

@app.get("/obtener-solicitud-relleno-por-maquina/")
async def obtener_solicitud_relleno_por_maquina():
    try:
        conexion = sqlite3.connect(ruta_db)
        cursor = conexion.cursor()
        cursor.execute("SELECT * FROM solicitudes_relleno")
        resultados = cursor.fetchall()
        cursor.close()
        conexion.close()

        if resultados:
            return [{"id_informe": row[0], "num_serie_maquina": row[2], "productos_restantes": row[3], "fecha": row[4], "hora": row[5]} for row in resultados]
        else:
            raise HTTPException(status_code=404, detail="No se encontraron solicitudes de relleno.")
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=str(e))


    
@app.get("/verificar-relleno-por-producto/{num_serie}")
async def verficar_relleno_por_producto(num_serie: int, serial_maquina: int):
    try:
        conexion = sqlite3.connect(ruta_db)
        cursor = conexion.cursor()

        # Verificar si el producto existe en el inventario de la máquina
        cursor.execute("SELECT cantidad FROM resurtidos WHERE serie_maquina=? AND num_serie=?", (serial_maquina, num_serie))
        cantidad_producto = cursor.fetchone()
        
        if not cantidad_producto:
            raise HTTPException(status_code=404, detail="No hay prodcutos disponibles en la maquina,se necesita urgentemente relleno del producto")

        cantidad_actual = cantidad_producto[0]

        # Determinar si se necesita resurtir el producto
        mensaje = "No se necesita relleno para este producto"
        if cantidad_actual <= 10:
            mensaje = "Se necesita relleno para el producto"

        cursor.close()
        conexion.close()

        return {"num_serie": num_serie, "cantidad_actual": cantidad_actual, "mensaje": mensaje}
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "_main_":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=5550)