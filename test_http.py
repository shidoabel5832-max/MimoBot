"""Prueba las peticiones HTTP desde Python (sin instalar nada extra).

1) Con el servidor corriendo, ejecuta en OTRA terminal:  python test_http.py
2) Cambia URL si pruebas desde otro equipo (usa la IP de la laptop).
"""
import json
import urllib.request

URL = "http://localhost:8000"


def pedir(metodo, ruta, datos=None):
    cuerpo = json.dumps(datos).encode() if datos is not None else None
    peticion = urllib.request.Request(
        URL + ruta, data=cuerpo, method=metodo,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(peticion) as respuesta:
        return respuesta.status, json.loads(respuesta.read())


print("GET  /estado   →", pedir("GET", "/estado"))
print("POST /sensor   →", pedir("POST", "/sensor", {"temperatura": 25.3, "humedad": 55}))
print("GET  /estado   →", pedir("GET", "/estado"))
print("POST /alarmas  →", pedir("POST", "/alarmas", {"hora": "07:00", "repetir": True}))
print("GET  /alarmas  →", pedir("GET", "/alarmas"))
print("POST /comandos →", pedir("POST", "/comandos", {"accion": "mover_servo"}))
print("GET  /comandos →", pedir("GET", "/comandos"))   # entrega y vacía la lista
print("GET  /comandos →", pedir("GET", "/comandos"))   # ahora debe venir vacía
