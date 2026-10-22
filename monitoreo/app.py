# app.py  -  API del Sistema de Monitoreo Materno-Fetal (FastAPI + PostgreSQL)
import secrets, string, hashlib, hmac, random, math, time, unicodedata
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Optional, Literal

from fastapi import FastAPI, HTTPException, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import psycopg2, psycopg2.errors
from psycopg2.extras import RealDictCursor

app = FastAPI(title="API Monitoreo Materno-Fetal")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# =====================  CONFIGURACION (cambia estos datos)  =====================
DB_CONFIG = {
    "host": "localhost",
    "database": "monitoreo",   # <--- nombre de tu base en pgAdmin
    "user": "postgres",
    "password": "12345678",       # <--- tu contraseña de PostgreSQL
    "port": "5432",
}
API_KEY_DISPOSITIVO = "cambia-esta-clave"   # clave que usara el equipo (ESP32) para enviar lecturas
HORAS_SESION = 2
# ===============================================================================

ALFANUM = string.ascii_letters + string.digits
# rol -> (tabla, columna id, cargo)
ROLES = {"administrador": ("administrador", "id_administrador", "Administrador"),
         "operador": ("operador", "id_operador", "Operador"),
         "tecnico": ("servicio_tecnico", "id_tecnico", "Servicio tecnico")}


# ------------------------------------------------------------------ utilidades
@contextmanager
def tx():
    """Abre conexion, confirma al terminar bien y revierte si hay error."""
    try:
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
    except Exception as e:
        raise HTTPException(500, f"Error conectando a PostgreSQL: {e}")
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def hash_pw(p: str, salt: Optional[str] = None) -> str:
    salt = salt or secrets.token_hex(8)
    return salt + "$" + hashlib.pbkdf2_hmac("sha256", p.encode(), salt.encode(), 100_000).hex()


def check_pw(p: str, guardado: str) -> bool:
    return hmac.compare_digest(hash_pw(p, guardado.split("$")[0]), guardado)


def nuevo_token() -> str:
    return "".join(secrets.choice(ALFANUM) for _ in range(48))   # token alfanumerico creado por Python


def edad(f: date) -> int:
    h = date.today()
    return h.year - f.year - ((h.month, h.day) < (f.month, f.day))


def auth(cur, token: str, *roles):
    cur.execute("SELECT rol, id_usuario FROM sesion_token WHERE token=%s AND expira > CURRENT_TIMESTAMP", (token,))
    s = cur.fetchone()
    if not s:
        raise HTTPException(401, "Sesion invalida o expirada.")
    if s["rol"] not in roles:
        raise HTTPException(403, "Acceso no autorizado.")
    tabla, col, _ = ROLES[s["rol"]]
    cur.execute(f"SELECT {col} AS id, nombre, apellido, cargo FROM {tabla} WHERE {col}=%s", (s["id_usuario"],))
    u = cur.fetchone()
    if not u:
        raise HTTPException(401, "Usuario inexistente.")
    u["rol"] = s["rol"]
    return u


def generar_credenciales(cur, tabla, nombre, apellido):
    limpio = lambda s: "".join(c for c in unicodedata.normalize("NFD", s.lower()) if c.isalnum() and ord(c) < 128)
    base = limpio(nombre)[:1] + limpio(apellido.split()[0])
    while True:
        usuario = base + str(random.randint(100, 999))
        cur.execute(f"SELECT 1 FROM {tabla} WHERE usuario=%s", (usuario,))
        if not cur.fetchone():
            break
    return usuario, "".join(secrets.choice(ALFANUM) for _ in range(10))


def insertar_persona(cur, rol, p, usuario, pw_hash):
    tabla, _, cargo = ROLES[rol]
    try:
        cur.execute(f"""INSERT INTO {tabla}
            (nombre, apellido, fecha_nacimiento, celular, carnet_identidad, cargo, usuario, contrasena)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (p.nombre.strip(), p.apellido.strip(), p.fecha_nacimiento, p.celular,
                     p.carnet_identidad.strip(), cargo, usuario, pw_hash))
    except psycopg2.errors.UniqueViolation:
        raise HTTPException(400, "Ya existe una persona registrada con ese carnet o usuario.")


# ------------------------------------------------------------------ modelos
class Persona(BaseModel):
    nombre: str
    apellido: str
    fecha_nacimiento: date
    carnet_identidad: str
    celular: Optional[str] = ""

class PrimerAdmin(Persona):
    usuario: str
    contrasena: str

class PersonalNuevo(Persona):
    tipo: Literal["administrador", "operador", "tecnico"]

class Login(BaseModel):
    rol: Literal["administrador", "operador", "tecnico"]
    usuario: str
    contrasena: str

class PacienteNuevo(Persona):
    mes_gestacion: int = Field(ge=1, le=9)

class Lectura(BaseModel):
    id_paciente: int
    fcf: Optional[int] = None
    toco: Optional[float] = None

class Reporte(BaseModel):
    sensor: Literal["Doppler fetal", "Tocodinamometro", "Otro"]
    tipo: Literal["Falla", "Cambio de componente", "Mantenimiento"]
    que_fallo: str
    por_que: str
    componente_cambiado: Optional[str] = None
    acciones: Optional[str] = None


# ------------------------------------------------------------------ sesion
@app.get("/")
def inicio():
    return FileResponse(Path(__file__).parent / "index.html")


@app.get("/api/check-admin")
def check_admin():
    with tx() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM administrador")
        return {"has_admin": cur.fetchone()["n"] > 0}


@app.post("/api/first-admin")
def primer_admin(d: PrimerAdmin):
    with tx() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM administrador")
        if cur.fetchone()["n"] > 0:
            raise HTTPException(403, "Ya existe un administrador.")
        insertar_persona(cur, "administrador", d, d.usuario.strip(), hash_pw(d.contrasena))
    return {"status": "ok"}


@app.post("/api/login")
def login(d: Login):
    tabla, col, _ = ROLES[d.rol]
    with tx() as cur:
        cur.execute(f"SELECT * FROM {tabla} WHERE usuario=%s", (d.usuario.strip(),))
        u = cur.fetchone()
        if not u or not check_pw(d.contrasena, u["contrasena"]):
            raise HTTPException(401, "Usuario, contraseña o tipo de cuenta incorrectos.")
        cur.execute("DELETE FROM sesion_token WHERE expira < CURRENT_TIMESTAMP")
        token = nuevo_token()
        cur.execute("INSERT INTO sesion_token (token, rol, id_usuario, expira) "
                    f"VALUES (%s,%s,%s, CURRENT_TIMESTAMP + INTERVAL '{HORAS_SESION} hours')", (token, d.rol, u[col]))
    return {"token": token, "rol": d.rol}


@app.get("/api/me")
def me(token: str = Query(...)):
    with tx() as cur:
        return auth(cur, token, "administrador", "operador", "tecnico")


@app.post("/api/logout")
def logout(token: str = Query(...)):
    with tx() as cur:
        cur.execute("DELETE FROM sesion_token WHERE token=%s", (token,))
    return {"status": "ok"}


# ------------------------------------------------------------------ ADMINISTRADOR
@app.post("/api/personal")
def registrar_personal(d: PersonalNuevo, token: str = Query(...)):
    """El administrador registra operadores, administradores o servicio tecnico.
    El usuario y la contraseña se generan automaticamente."""
    with tx() as cur:
        auth(cur, token, "administrador")
        tabla = ROLES[d.tipo][0]
        usuario, clave = generar_credenciales(cur, tabla, d.nombre, d.apellido)
        insertar_persona(cur, d.tipo, d, usuario, hash_pw(clave))
    return {"usuario": usuario, "contrasena": clave}


@app.get("/api/operadores")
def listar_operadores(token: str = Query(...)):
    with tx() as cur:
        auth(cur, token, "administrador")
        cur.execute("""SELECT o.id_operador, o.nombre, o.apellido, o.carnet_identidad, o.celular, o.usuario,
                              o.fecha_registro, COUNT(p.id_paciente) AS n_pacientes
                       FROM operador o LEFT JOIN paciente p USING (id_operador)
                       GROUP BY o.id_operador ORDER BY o.fecha_registro DESC""")
        return cur.fetchall()


@app.get("/api/administradores")
def listar_admins(token: str = Query(...)):
    with tx() as cur:
        auth(cur, token, "administrador")
        cur.execute("""SELECT id_administrador, nombre, apellido, carnet_identidad, celular, usuario, fecha_registro
                       FROM administrador ORDER BY fecha_registro""")
        return cur.fetchall()


@app.get("/api/operadores/{oid}")
def detalle_operador(oid: int, token: str = Query(...)):
    with tx() as cur:
        auth(cur, token, "administrador")
        cur.execute("""SELECT id_operador, nombre, apellido, carnet_identidad, celular, usuario, fecha_registro
                       FROM operador WHERE id_operador=%s""", (oid,))
        op = cur.fetchone()
        if not op:
            raise HTTPException(404, "Operador no encontrado.")
        cur.execute("""SELECT id_paciente, nombre, apellido, carnet_identidad, celular, fecha_nacimiento,
                              mes_gestacion, fecha_registro FROM paciente
                       WHERE id_operador=%s ORDER BY fecha_registro DESC""", (oid,))
        pacs = cur.fetchall()
        for p in pacs:
            p["edad"] = edad(p["fecha_nacimiento"])
        return {"operador": op, "pacientes": pacs}


@app.delete("/api/operadores/{oid}")
def eliminar_operador(oid: int, token: str = Query(...)):
    with tx() as cur:
        auth(cur, token, "administrador")
        cur.execute("DELETE FROM paciente WHERE id_operador=%s", (oid,))
        cur.execute("DELETE FROM sesion_token WHERE rol='operador' AND id_usuario=%s", (oid,))
        cur.execute("DELETE FROM operador WHERE id_operador=%s RETURNING 1", (oid,))
        if not cur.fetchone():
            raise HTTPException(404, "Operador no encontrado.")
    return {"status": "ok"}


@app.delete("/api/pacientes/{pid}")
def eliminar_paciente_admin(pid: int, token: str = Query(...)):
    with tx() as cur:
        auth(cur, token, "administrador")
        cur.execute("DELETE FROM paciente WHERE id_paciente=%s RETURNING 1", (pid,))
        if not cur.fetchone():
            raise HTTPException(404, "Paciente no encontrada.")
    return {"status": "ok"}


# ------------------------------------------------------------------ OPERADOR
def mi_paciente(cur, u, pid):
    """Un operador solo accede a las pacientes que el mismo registro."""
    cur.execute("SELECT * FROM paciente WHERE id_paciente=%s AND id_operador=%s", (pid, u["id"]))
    p = cur.fetchone()
    if not p:
        raise HTTPException(404, "Paciente no encontrada.")
    return p


@app.post("/api/pacientes")
def registrar_paciente(d: PacienteNuevo, token: str = Query(...)):
    with tx() as cur:
        u = auth(cur, token, "operador")
        try:
            cur.execute("""INSERT INTO paciente (nombre, apellido, fecha_nacimiento, celular, carnet_identidad,
                                                 mes_gestacion, id_operador)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                        (d.nombre.strip(), d.apellido.strip(), d.fecha_nacimiento, d.celular,
                         d.carnet_identidad.strip(), d.mes_gestacion, u["id"]))
        except psycopg2.errors.UniqueViolation:
            raise HTTPException(400, "Ya existe una paciente con ese carnet.")
    return {"status": "ok"}


@app.get("/api/pacientes")
def mis_pacientes(token: str = Query(...)):
    with tx() as cur:
        u = auth(cur, token, "operador")
        cur.execute("""SELECT id_paciente, nombre, apellido, carnet_identidad, celular, fecha_nacimiento,
                              mes_gestacion, fecha_registro, id_operador
                       FROM paciente WHERE id_operador=%s ORDER BY fecha_registro DESC""", (u["id"],))
        rows = cur.fetchall()
        for r in rows:
            r["edad"] = edad(r["fecha_nacimiento"])
        return rows


def guardar_lectura(cur, pid, fcf, toco):
    if fcf is not None:
        cur.execute("INSERT INTO lectura_doppler (id_paciente, fcf) VALUES (%s,%s)", (pid, fcf))
    if toco is not None:
        cur.execute("INSERT INTO lectura_tocodinamometro (id_paciente, presion) VALUES (%s,%s)", (pid, toco))


@app.get("/api/pacientes/{pid}/datos")
def datos_paciente(pid: int, token: str = Query(...)):
    with tx() as cur:
        u = auth(cur, token, "operador")
        mi_paciente(cur, u, pid)
        cur.execute("SELECT fcf AS v, fecha FROM lectura_doppler WHERE id_paciente=%s ORDER BY fecha DESC LIMIT 120", (pid,))
        d = cur.fetchall()
        cur.execute("SELECT presion AS v, fecha FROM lectura_tocodinamometro WHERE id_paciente=%s ORDER BY fecha DESC LIMIT 120", (pid,))
        t = cur.fetchall()
    fmt = lambda rows: [{"v": float(r["v"]), "h": r["fecha"].strftime("%H:%M:%S")} for r in reversed(rows)]
    return {"doppler": fmt(d), "toco": fmt(t)}


@app.post("/api/pacientes/{pid}/simular")
def simular(pid: int, token: str = Query(...)):
    """Lectura de practica (cuando no hay equipo conectado)."""
    with tx() as cur:
        u = auth(cur, token, "operador")
        mi_paciente(cur, u, pid)
        t = time.time()
        fcf = int(142 + 6 * math.sin(t / 7) + random.randint(-3, 3))
        toco = round(8 + max(0, math.sin(t / 12)) ** 3 * 70 + random.uniform(-2, 2), 1)
        guardar_lectura(cur, pid, fcf, toco)
    return {"status": "ok"}


@app.post("/api/lectura")
def recibir_lectura(d: Lectura, x_api_key: Optional[str] = Header(None)):
    """Endpoint para el equipo real (ESP32/Arduino). Header X-API-KEY."""
    if x_api_key != API_KEY_DISPOSITIVO:
        raise HTTPException(403, "Clave de dispositivo incorrecta.")
    with tx() as cur:
        cur.execute("SELECT 1 FROM paciente WHERE id_paciente=%s", (d.id_paciente,))
        if not cur.fetchone():
            raise HTTPException(404, "Paciente no encontrada.")
        guardar_lectura(cur, d.id_paciente, d.fcf, d.toco)
    return {"status": "ok"}


# ------------------------------------------------------------------ SERVICIO TECNICO
SENSORES = (("Doppler fetal", "lectura_doppler", "fcf", 30, 240),
            ("Tocodinamometro", "lectura_tocodinamometro", "presion", 0, 100))


@app.get("/api/sensores/estado")
def estado_sensores(token: str = Query(...)):
    out = []
    with tx() as cur:
        auth(cur, token, "tecnico")
        for nombre, tabla, col, lo, hi in SENSORES:
            cur.execute(f"""SELECT {col} AS valor,
                    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP::timestamp - fecha)) AS seg
                    FROM {tabla} ORDER BY fecha DESC LIMIT 1""")
            r = cur.fetchone()
            if not r:
                est, msg = "warn", "Sin datos registrados todavia"
            elif r["seg"] > 30:
                est, msg = "fail", f"Sin señal hace {int(r['seg'])} s (apagado o desconectado)"
            elif not lo <= float(r["valor"]) <= hi:
                est, msg = "fail", f"Valor fuera de rango ({float(r['valor']):g})"
            else:
                est, msg = "ok", f"Funcionando · ultimo valor {float(r['valor']):g}"
            out.append({"sensor": nombre, "estado": est, "mensaje": msg})
    return out


@app.post("/api/reportes")
def crear_reporte(d: Reporte, token: str = Query(...)):
    with tx() as cur:
        u = auth(cur, token, "tecnico")
        cur.execute("""INSERT INTO reporte_tecnico (id_tecnico, sensor, tipo, que_fallo, por_que,
                                                    componente_cambiado, acciones)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (u["id"], d.sensor, d.tipo, d.que_fallo, d.por_que,
                     d.componente_cambiado or None, d.acciones or None))
    return {"status": "ok"}


@app.get("/api/reportes")
def listar_reportes(token: str = Query(...)):
    with tx() as cur:
        u = auth(cur, token, "tecnico")
        cur.execute("SELECT * FROM reporte_tecnico WHERE id_tecnico=%s ORDER BY fecha DESC LIMIT 50", (u["id"],))
        return cur.fetchall()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
