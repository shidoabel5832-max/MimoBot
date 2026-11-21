import network
import time
import urequests
import dht
from machine import Pin

WIFI = "RED"
CLAVE = "CONTRASEÑA"
SERVIDOR = "http://192.168.1.50:8000"   # IP de la lap

PIN_DHT, PIN_PIR, PIN_BOTON = 16, 14, 15
CADA_SENSOR_MS = 5000      
PAUSA_DESPERTAR_MS = 3000  

sensor = dht.DHT11(Pin(PIN_DHT))
pir = Pin(PIN_PIR, Pin.IN)
boton = Pin(PIN_BOTON, Pin.IN, Pin.PULL_UP)
led = Pin("LED", Pin.OUT)

wlan = network.WLAN(network.STA_IF)


def conectar():
    wlan.active(True)
    if wlan.isconnected():
        return
    wlan.connect(WIFI, CLAVE)
    print("Conectando al Wi-Fi", end="")
    while not wlan.isconnected():
        print(".", end="")
        led.toggle()
        time.sleep(0.5)
    led.on()
    print("\nConectada. IP de la Pico:", wlan.ifconfig()[0])


def enviar(ruta, datos=None):
    """POST al servidor. Devuelve True si salió bien."""
    try:
        r = urequests.post(SERVIDOR + ruta, json=datos or {})
        r.close()   
        return True
    except Exception as e:
        print("Error de red:", e)
        return False


def pedir_comandos():
    """Por ahora solo los muestra; luego moverán servo, luces y zumbador."""
    try:
        r = urequests.get(SERVIDOR + "/comandos")
        lista = r.json()
        r.close()
        for c in lista:
            print("Comando recibido:", c)
    except Exception as e:
        print("Error de red:", e)


t_sensor = time.ticks_add(time.ticks_ms(), -CADA_SENSOR_MS)
t_despertar = time.ticks_add(time.ticks_ms(), -PAUSA_DESPERTAR_MS)
pir_antes = 0
boton_antes = 1


def despertar(motivo):
    global t_despertar
    if time.ticks_diff(time.ticks_ms(), t_despertar) < PAUSA_DESPERTAR_MS:
        return
    t_despertar = time.ticks_ms()
    print("Despertar por", motivo)
    enviar("/despertar")


conectar()
while True:
    if not wlan.isconnected():
        conectar()

    v = pir.value()
    if v and not pir_antes:     
        despertar("PIR")
    pir_antes = v

    b = boton.value()
    if b == 0 and boton_antes == 1:
        despertar("botón")
    boton_antes = b

    if time.ticks_diff(time.ticks_ms(), t_sensor) >= CADA_SENSOR_MS:
        t_sensor = time.ticks_ms()
        try:
            sensor.measure()
            t, h = sensor.temperature(), sensor.humidity()
            print(f"DHT11: {t} °C | {h} %")
            enviar("/sensor", {"temperatura": t, "humedad": h})
        except OSError as e:
            print("DHT11: error de lectura", e)
        pedir_comandos()

    time.sleep_ms(50)
