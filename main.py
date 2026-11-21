import json, os, re, sys, threading, time
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Rutas:
EMPAQUETADO = getattr(sys, "frozen", False)
AQUI = os.path.dirname(sys.executable) if EMPAQUETADO else os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(sys._MEIPASS, "web") if EMPAQUETADO else os.path.join(AQUI, "..", "web")
ARCHIVO = os.path.join(AQUI, "data.json")  
IDLE = 45  
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

app = FastAPI()

# modo: 
estado = {"temperatura": None, "humedad": None, "modo": "reposo",
          "aviso": None, "actividad": time.time(), "lectura": None}
comandos = [] 


# guardado
def cargar():
    if os.path.exists(ARCHIVO):
        with open(ARCHIVO) as f:
            d = json.load(f)
            return d.get("alarmas", []), d.get("recordatorios", [])
    return [], []


def guardar():
    with open(ARCHIVO, "w") as f:
        json.dump({"alarmas": alarmas, "recordatorios": recordatorios}, f)


alarmas, recordatorios = cargar()


#Modelos
class Lectura(BaseModel):
    temperatura: float
    humedad: float

class Alarma(BaseModel):
    hora: str            
    repetir: bool = False
    etiqueta: str = "Nueva alarma"

class Recordatorio(BaseModel):
    texto: str
    cuando: str          

class Pregunta(BaseModel):
    texto: str

class Comando(BaseModel):
    accion: str


# Lógica 
def tocar_actividad():
    estado["actividad"] = time.time()


def sonar(aviso):
    estado["aviso"] = aviso
    estado["modo"] = "alarma"
    comandos.append("alarma_on")


def apagar():
    if estado["aviso"] is not None:
        comandos.append("alarma_off")
    estado["aviso"] = None
    estado["modo"] = "despierto"
    tocar_actividad()


def en_minutos(n):
    return datetime.now() + timedelta(minutes=n)


def resp(titulo, detalle, tipo="ok", accion=None):
    return {"titulo": titulo, "detalle": detalle, "tipo": tipo, "accion": accion}


def responder(texto):
    """Comandos fijos de 'Preguntar' (funcionan sin internet)."""
    t = texto.lower().strip()
    m = re.search(r"recu[eé]rdame\s+(.+?)\s+en\s+(\d+)\s+minutos?", t)
    if m:
        cuando = en_minutos(int(m.group(2)))
        txt = m.group(1).capitalize()
        recordatorios.append({"texto": txt, "cuando": cuando.strftime("%Y-%m-%dT%H:%M")})
        guardar()
        return resp(f"Te lo recordaré a las {cuando.strftime('%H:%M')}.", f"Recordatorio creado: {txt}.", accion="recordatorio")
    m = re.search(r"alarma.*?(\d{1,2})(?::(\d{2}))?", t)
    if m and int(m.group(1)) < 24 and int(m.group(2) or 0) < 60:
        hora = f"{int(m.group(1)):02d}:{int(m.group(2) or 0):02d}"
        alarmas.append({"hora": hora, "repetir": False, "etiqueta": "Nueva alarma"})
        guardar()
        dia = "hoy" if hora > datetime.now().strftime("%H:%M") else "mañana"
        return resp(f"Listo, {dia} a las {hora}.", "He creado una alarma de una sola vez.", accion="alarma")
    if "hora" in t:
        return resp("Son las " + datetime.now().strftime("%H:%M") + ".", "Un buen momento para seguir con tu día.")
    if "fecha" in t or "día" in t:
        d = datetime.now()
        return resp(f"{DIAS[d.weekday()].capitalize()}, {d.day} de {MESES[d.month - 1]}.", f"Estamos en {d.year}.")
    if "temperatura" in t or "humedad" in t or "calor" in t or "frío" in t:
        if estado["temperatura"] is None:
            return resp("Todavía no tengo lecturas.", "Esperando datos de la Pico.")
        return resp(f"Hay {estado['temperatura']:.0f} °C en tu espacio.", f"Humedad: {estado['humedad']:.0f} %. Datos recibidos de la Pico.")
    return resp("Eso todavía no lo entiendo.", "Puedo decirte la hora, la fecha y la temperatura, o crear alarmas y recordatorios.", tipo="no")


def vigilar():
    """Revisa cada segundo alarmas, recordatorios y el regreso a reposo."""
    while True:
        ahora = datetime.now()
        marca = ahora.strftime("%Y-%m-%d %H:%M")
        if estado["aviso"] is None:
            for a in alarmas[:]:
                if a["hora"] == ahora.strftime("%H:%M") and a.get("ultimo") != marca:
                    a["ultimo"] = marca
                    if not a["repetir"]:
                        alarmas.remove(a)
                    guardar()
                    sonar({"tipo": "alarma", "texto": a.get("etiqueta", "Nueva alarma"), "hora": a["hora"], "repetir": a["repetir"]})
                    break
        if estado["aviso"] is None:
            for r in recordatorios[:]:
                if r["cuando"] <= ahora.strftime("%Y-%m-%dT%H:%M"):
                    recordatorios.remove(r)
                    guardar()
                    sonar({"tipo": "recordatorio", "texto": r["texto"], "cuando": r["cuando"]})
                    break
        if estado["modo"] == "despierto" and time.time() - estado["actividad"] > IDLE:
            estado["modo"] = "reposo"
            comandos.append("dormir")
        time.sleep(1)


threading.Thread(target=vigilar, daemon=True).start()


# Endpoints 
@app.get("/estado")
def obtener_estado():
    d = datetime.now()
    return {"hora": d.strftime("%H:%M:%S"),
            "fecha": f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]}",
            "temperatura": estado["temperatura"], "humedad": estado["humedad"],
            "modo": estado["modo"], "aviso": estado["aviso"],
            "lectura_hace": None if estado["lectura"] is None else int(time.time() - estado["lectura"])}


@app.post("/sensor")
def recibir_sensor(lectura: Lectura):
    estado["temperatura"] = lectura.temperatura
    estado["humedad"] = lectura.humedad
    estado["lectura"] = time.time()
    return {"ok": True}


@app.post("/despertar")
def despertar():
    """Lo llaman la app (toque) y la Pico (PIR o botón). También reinicia el temporizador."""
    if estado["modo"] == "reposo":
        estado["modo"] = "despierto"
        comandos.append("despertar")
    tocar_actividad()
    return {"modo": estado["modo"]}


@app.get("/comandos")
def pedir_comandos():
    pendientes = comandos.copy()
    comandos.clear()
    return pendientes


@app.post("/comandos")
def agregar_comando(c: Comando):
    comandos.append(c.accion)
    return {"ok": True}


@app.get("/alarmas")
def listar_alarmas():
    return alarmas


@app.post("/alarmas")
def crear_alarma(a: Alarma):
    alarmas.append({"hora": a.hora, "repetir": a.repetir, "etiqueta": a.etiqueta})
    guardar()
    return {"ok": True}


@app.delete("/alarmas/{i}")
def borrar_alarma(i: int):
    if 0 <= i < len(alarmas):
        alarmas.pop(i)
        guardar()
    return {"ok": True}


@app.get("/recordatorios")
def listar_recordatorios():
    return sorted(recordatorios, key=lambda r: r["cuando"])


@app.post("/recordatorios")
def crear_recordatorio(r: Recordatorio):
    recordatorios.append(r.model_dump())
    guardar()
    return {"ok": True}


@app.delete("/recordatorios/{i}")
def borrar_recordatorio(i: int):
    ordenados = sorted(recordatorios, key=lambda r: r["cuando"])
    if 0 <= i < len(ordenados):
        recordatorios.remove(ordenados[i])
        guardar()
    return {"ok": True}


@app.post("/preguntar")
def preguntar(p: Pregunta):
    tocar_actividad()
    return responder(p.texto)


@app.post("/aviso/apagar")
def aviso_apagar():
    apagar()
    return {"ok": True}


@app.post("/aviso/posponer")
def aviso_posponer():
    a = estado["aviso"]
    cuando = en_minutos(5)
    tipo = a["tipo"] if a else "alarma"
    if a:
        if tipo == "alarma":
            alarmas.append({"hora": cuando.strftime("%H:%M"), "repetir": False, "etiqueta": a["texto"]})
        else:
            recordatorios.append({"texto": a["texto"], "cuando": cuando.strftime("%Y-%m-%dT%H:%M")})
        guardar()
    apagar()
    return {"tipo": tipo, "hasta": cuando.strftime("%H:%M")}


@app.post("/reposo")
def ir_a_reposo():
    if estado["modo"] == "despierto":
        estado["modo"] = "reposo"
        comandos.append("dormir")
    return {"modo": estado["modo"]}

# --
app.mount("/", StaticFiles(directory=WEB, html=True), name="web")


# para el .exe
if __name__ == "__main__":
    import uvicorn
    import webbrowser
    def abrir_navegador():
        url = "http://localhost:8000"
        if sys.platform == "win32":
            perfil = os.path.join(AQUI, "perfil_mimo")
            os.system(f'start "" msedge --user-data-dir="{perfil}" '
                      f'--autoplay-policy=no-user-gesture-required --app={url}')
        else:
            webbrowser.open(url)
    threading.Timer(1.5, abrir_navegador).start()
    uvicorn.run(app, host="0.0.0.0", port=8000)
