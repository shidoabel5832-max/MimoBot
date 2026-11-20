"""Prueba HTTP desde la Raspberry Pi Pico W (MicroPython).

Antes de correrlo:
  - Pon el nombre y contraseña de tu Wi-Fi (usa el hotspot del celular).
  - Pon la IP de tu laptop (Windows: ipconfig, Mac/Linux: ifconfig) en SERVIDOR.
  - Inicia el servidor con:  uvicorn main:app --host 0.0.0.0
  - La laptop y la Pico deben estar en la MISMA red.
Si no conecta, revisa el firewall de la laptop (permite el puerto 8000).
Guárdalo en la Pico como main.py para que corra al encender.
"""
import network
import time
import urequests
import random
from machine import Pin

WIFI = "TU_RED"
CLAVE = "TU_CONTRASEÑA"
SERVIDOR = "http://192.168.1.50:8000"  # <-- cambia por la IP de tu laptop

led = Pin("LED", Pin.OUT)

wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(WIFI, CLAVE)
while not wlan.isconnected():
    print("Conectando al Wi-Fi...")
    time.sleep(1)
print("Conectada. IP de la Pico:", wlan.ifconfig()[0])

while True:
    try:
        # 1) Mandar una lectura (aquí falsa; luego será la del DHT11)
        datos = {"temperatura": 20 + random.random() * 8, "humedad": 50}
        r = urequests.post(SERVIDOR + "/sensor", json=datos)
        print("POST /sensor →", r.status_code)
        r.close()  # siempre cierra la respuesta, la Pico tiene poca memoria

        # 2) Preguntar si hay comandos pendientes
        r = urequests.get(SERVIDOR + "/comandos")
        comandos = r.json()
        r.close()
        for c in comandos:
            print("Comando recibido:", c)
            if c == "mover_servo":
                led.toggle()  # por ahora solo parpadea el LED de la placa
    except Exception as e:
        print("Error de red:", e)
    time.sleep(2)
