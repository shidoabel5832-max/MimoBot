"""mimo - firmware de la Pico W con los pines del diagrama de referencia.
Guárdalo en la Pico como main.py. Necesita ssd1306.py en la Pico (opcional: sin OLED también corre).

Qué hace:
  - DHT11 -> manda temperatura y humedad a la app.
  - Ultrasónico (alguien a menos de UMBRAL_CM) o botón Wake -> despierta a mimo.
  - Botón Scan -> apaga la alarma si está sonando (si no, despierta).
  - Atiende las órdenes de la app: despertar, dormir, alarma_on, alarma_off (mueve el servo).
  - OLED: muestra modo, temperatura, distancia y Wi-Fi.
"""
import network
import time
import urequests
import dht
from machine import Pin, PWM, I2C, time_pulse_us

WIFI = "TU_RED"
CLAVE = "TU_CONTRASEÑA"
SERVIDOR = "http://192.168.1.50:8000"   # IP de la laptop (ipconfig)

UMBRAL_CM = 80             # a menos de esta distancia se considera "hay alguien"
CADA_SENSOR_MS = 5000
PAUSA_DESPERTAR_MS = 3000

# ---- Pines (diagrama de referencia) ----
sensor = dht.DHT11(Pin(12))
btn_scan = Pin(13, Pin.IN, Pin.PULL_DOWN)   # un pie a 3V3, activo en 1
btn_wake = Pin(14, Pin.IN, Pin.PULL_UP)     # un pie a GND, activo en 0
trig = Pin(16, Pin.OUT)
echo = Pin(17, Pin.IN)                      # ¡con divisor 1 kΩ + 2 kΩ!
servo = PWM(Pin(15))
servo.freq(50)
led = Pin("LED", Pin.OUT)

try:
    import ssd1306
    oled = ssd1306.SSD1306_I2C(128, 64, I2C(0, sda=Pin(0), scl=Pin(1)))
except Exception as e:
    oled = None
    print("OLED no disponible:", e)

wlan = network.WLAN(network.STA_IF)
modo_txt, temp, hum, dist = "reposo", "--", "--", None
alarma = False


def angulo(a):
    a = max(0, min(180, a))
    servo.duty_u16(int(1638 + (8192 - 1638) * a / 180))


def medir_cm():
    trig.low()
    time.sleep_us(2)
    trig.high()
    time.sleep_us(10)
    trig.low()
    t = time_pulse_us(echo, 1, 30000)
    return None if t < 0 else round(t / 58.2)


def pantalla():
    if not oled:
        return
    oled.fill(0)
    oled.text("mimo", 0, 0)
    oled.text(modo_txt, 48, 0)
    oled.text("T:%s C H:%s %%" % (temp, hum), 0, 16)
    oled.text("Dist: %s cm" % ("--" if dist is None else dist), 0, 32)
    oled.text("WiFi OK" if wlan.isconnected() else "Sin WiFi", 0, 48)
    oled.show()


def conectar():
    wlan.active(True)
    if wlan.isconnected():
        return
    wlan.connect(WIFI, CLAVE)
    print("Conectando al Wi-Fi", end="")
    while not wlan.isconnected():
        print(".", end="")
        led.toggle()
        pantalla()
        time.sleep(0.5)
    led.on()
    print("\nConectada. IP de la Pico:", wlan.ifconfig()[0])


def enviar(ruta, datos=None):
    try:
        r = urequests.post(SERVIDOR + ruta, json=datos or {})
        r.close()
        return True
    except Exception as e:
        print("Error de red:", e)
        return False


def mover_cabeza():
    for a in (60, 120, 90):
        angulo(a)
        time.sleep_ms(250)


def aplicar(c):
    global alarma, modo_txt
    print("Comando recibido:", c)
    if c == "despertar":
        modo_txt = "despierto"
        mover_cabeza()
    elif c == "dormir":
        modo_txt, alarma = "reposo", False
        angulo(90)
    elif c == "alarma_on":
        modo_txt, alarma = "ALARMA", True
    elif c == "alarma_off":
        modo_txt, alarma = "despierto", False
        angulo(90)


def atender_comandos():
    try:
        r = urequests.get(SERVIDOR + "/comandos")
        lista = r.json()
        r.close()
        for c in lista:
            aplicar(c)
    except Exception as e:
        print("Error de red:", e)


t_despertar = time.ticks_add(time.ticks_ms(), -PAUSA_DESPERTAR_MS)


def despertar(motivo):
    global t_despertar
    if time.ticks_diff(time.ticks_ms(), t_despertar) < PAUSA_DESPERTAR_MS:
        return
    t_despertar = time.ticks_ms()
    print("Despertar por", motivo)
    enviar("/despertar")


def boton_scan():
    global alarma, modo_txt
    if alarma:
        enviar("/aviso/apagar")
        alarma, modo_txt = False, "despierto"
        angulo(90)
    else:
        despertar("botón Scan")


angulo(90)
conectar()
ahora = time.ticks_ms()
t_dist = t_sensor = t_cmd = t_oled = t_servo = ahora
t_sensor = time.ticks_add(ahora, -CADA_SENSOR_MS)
cuenta, w_antes, s_antes, lado = 0, 1, 0, False

while True:
    ahora = time.ticks_ms()
    if not wlan.isconnected():
        conectar()

    w, s = btn_wake.value(), btn_scan.value()
    if w == 0 and w_antes == 1:
        despertar("botón Wake")
    if s == 1 and s_antes == 0:
        boton_scan()
    w_antes, s_antes = w, s

    if time.ticks_diff(ahora, t_dist) >= 200:
        t_dist = ahora
        dist = medir_cm()
        cerca = dist is not None and dist < UMBRAL_CM
        cuenta = cuenta + 1 if cerca else 0
        if cuenta == 2:          # dos lecturas seguidas: alguien se acercó
            despertar("ultrasónico")

    if time.ticks_diff(ahora, t_sensor) >= CADA_SENSOR_MS:
        t_sensor = ahora
        try:
            sensor.measure()
            temp, hum = sensor.temperature(), sensor.humidity()
            enviar("/sensor", {"temperatura": temp, "humedad": hum})
        except OSError as e:
            print("DHT11: error de lectura", e)

    if time.ticks_diff(ahora, t_cmd) >= 1000:
        t_cmd = ahora
        atender_comandos()

    if alarma and time.ticks_diff(ahora, t_servo) >= 400:   # la cabeza se mueve mientras suena
        t_servo = ahora
        lado = not lado
        angulo(60 if lado else 120)

    if time.ticks_diff(ahora, t_oled) >= 1000:
        t_oled = ahora
        pantalla()

    time.sleep_ms(30)
