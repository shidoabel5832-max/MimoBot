import network
import time
import json
import socket
import ntptime
import dht
import ssd1306
from machine import Pin, I2C, time_pulse_us

#### ---- WIFI Y SERVIDOR ---- ####

WIFI = "Nikko"
CLAVE = "NikkoFan"
SERVER_IP = "10.12.96.59"      # IP de la lap
SERVER_PORT = 8000
TIMEOUT_RED = 1.5                # segundos máximos esperando al servidor

#### ---- PINES ---- ####

i2c = I2C(0, sda=Pin(0), scl=Pin(1))          # OLED: SDA GP0, SCL GP1, 3V3
oled = ssd1306.SSD1306_I2C(128, 64, i2c)
btn_scan = Pin(13, Pin.IN, Pin.PULL_DOWN)     # GP13 -> 3V3 (activo en 1)
btn_wake = Pin(14, Pin.IN, Pin.PULL_UP)       # GP14 -> GND (activo en 0)
trig = Pin(16, Pin.OUT)                       # GP16, VBUS
echo = Pin(17, Pin.IN)                        # GP17 (¡con divisor de voltaje si el sensor es de 5 V!)
# GP15: antes era el servo, ahora queda sin usar
sensor = dht.DHT11(Pin(12))                   # GP12, 3V3
led = Pin("LED", Pin.OUT)

#### ---- VARIABLES ---- ####

det_dist = 40
CADA_SENSOR_MS = 5000
PAUSA_FALLO_MS = 15000     # si el servidor falla, espera esto antes de reintentar
PAUSA_DESPERTAR_MS = 3000
LEER_DHT_MS = 2000
AWAKE_MS = 7000           # el modo despierto dura 7 s

ZONA_HORARIA = -6         # horas respecto a UTC (centro de México)
NTP_CADA_MS = 3600000     # vuelve a sincronizar la hora cada hora
NTP_REINTENTO_MS = 60000  # si falla, reintenta cada minuto
ntptime.timeout = 2

wlan = network.WLAN(network.STA_IF)

temp = None
hum = None
dht_ok = False
hora_ok = False

#### ---- RED ---- ####


def conectar(esperar_ms=15000):
    """Conexión inicial. Si no hay Wi-Fi, el robot sigue funcionando."""
    wlan.active(True)
    if wlan.isconnected():
        return True
    wlan.connect(WIFI, CLAVE)
    print("Conectando al Wi-Fi", end="")
    t0 = time.ticks_ms()
    while not wlan.isconnected() and time.ticks_diff(time.ticks_ms(), t0) < esperar_ms:
        print(".", end="")
        led.toggle()
        time.sleep(0.5)
    if wlan.isconnected():
        led.on()
        print("\nConectada. IP de la Pico:", wlan.ifconfig()[0])
        return True
    led.off()
    print("\nSin Wi-Fi por ahora; reintentará en segundo plano")
    return False


def http(metodo, ruta, datos=None):
    """Petición HTTP simple con timeout. Devuelve (ok, cuerpo)."""
    s = None
    try:
        cuerpo = json.dumps(datos) if datos is not None else ""
        peticion = ("%s %s HTTP/1.0\r\nHost: %s\r\n"
                    "Content-Type: application/json\r\n"
                    "Content-Length: %d\r\nConnection: close\r\n\r\n%s"
                    % (metodo, ruta, SERVER_IP, len(cuerpo), cuerpo))
        s = socket.socket()
        s.settimeout(TIMEOUT_RED)
        s.connect(socket.getaddrinfo(SERVER_IP, SERVER_PORT)[0][-1])
        s.send(peticion.encode())
        resp = b""
        while True:
            try:
                trozo = s.recv(512)
            except OSError:
                break
            if not trozo:
                break
            resp += trozo
        ok = resp[9:10] == b"2"           # "HTTP/1.x 2xx"
        if b"\r\n\r\n" in resp:
            cuerpo_resp = resp.split(b"\r\n\r\n", 1)[1]
        else:
            cuerpo_resp = b""
        if not ok:
            print("Respuesta inesperada del servidor")
        return ok, cuerpo_resp
    except Exception as e:
        print("Error de red:", e)
        return False, b""
    finally:
        if s:
            s.close()


def enviar(ruta, datos=None):
    ok, _ = http("POST", ruta, datos or {})
    return ok


def pedir_comandos():
    """Por ahora solo los muestra; luego moverán servo, luces y zumbador."""
    ok, cuerpo = http("GET", "/comandos")
    if ok:
        try:
            for c in json.loads(cuerpo):
                print("Comando recibido:", c)
        except Exception as e:
            print("Comandos con formato no válido:", e)
    return ok


t_despertar = time.ticks_add(time.ticks_ms(), -PAUSA_DESPERTAR_MS)


def despertar(motivo):
    global t_despertar
    if time.ticks_diff(time.ticks_ms(), t_despertar) < PAUSA_DESPERTAR_MS:
        return
    t_despertar = time.ticks_ms()
    print("Despertar por", motivo)
    if wlan.isconnected():
        enviar("/despertar")

def sincronizar_hora():
    """Pone el reloj de la Pico con la hora de internet (NTP)."""
    global hora_ok, proximo_ntp
    try:
        ntptime.settime()
        hora_ok = True
        proximo_ntp = time.ticks_add(time.ticks_ms(), NTP_CADA_MS)
        print("Hora sincronizada")
    except Exception as e:
        print("No se pudo obtener la hora:", e)
        proximo_ntp = time.ticks_add(time.ticks_ms(), NTP_REINTENTO_MS)

#### ---- DHT11 (una sola lectura compartida) ---- ####


def leer_dht():
    global temp, hum, dht_ok
    try:
        sensor.measure()
        temp = sensor.temperature()
        hum = sensor.humidity()
        dht_ok = True
    except OSError as e:
        dht_ok = False
        print("DHT11: error de lectura", e)

#### ---- OLED ---- ####


def rrect(x, y, w, h, r, c):
    r = min(r, w // 2, h // 2)
    oled.fill_rect(x, y + r, w, h - 2 * r, c)
    for i in range(r):
        d = int((r * r - (r - i - 0.5) ** 2) ** 0.5)
        oled.hline(x + r - d, y + i, w - 2 * (r - d), c)
        oled.hline(x + r - d, y + h - 1 - i, w - 2 * (r - d), c)


def cara(eye_h=26):
    oled.fill(0)
    rrect(0, 0, 128, 64, 14, 1)
    rrect(2, 2, 124, 60, 12, 0)
    y = 32 - eye_h // 2
    rrect(38, y, 14, eye_h, 7, 1)
    rrect(76, y, 14, eye_h, 7, 1)
    oled.show()


def parpadeo():
    for h in (18, 8, 2, 8, 18, 26):
        cara(h)
        time.sleep_ms(30)


def datos():
    oled.fill(0)
    if hora_ok:
        local = time.localtime(time.time() + ZONA_HORARIA * 3600)
        oled.text("Hora: %02d:%02d" % (local[3], local[4]), 8, 6)
        y_temp, y_hum, y_err = 26, 46, 36
    else:
        y_temp, y_hum, y_err = 16, 36, 28
    if dht_ok:
        oled.text("Temp: %d C" % temp, 8, y_temp)
        oled.text("Hum:  %d %%" % hum, 8, y_hum)
    else:
        oled.text("Error sensor", 8, y_err)
    oled.show()

#### ---- ULTRASÓNICO (sin uso por ahora) ---- ####


def measure():
    trig.low()
    time.sleep_us(2)
    trig.high()
    time.sleep_us(10)
    trig.low()
    t = time_pulse_us(echo, 1, 12000)
    if t < 0:
        return 999
    return t * 0.0343 / 2


#### ---- ARRANQUE ---- ####

despierto = False
boton_antes = btn_wake.value()   # si arranca presionado, se ignora hasta soltarlo
presionado = False
inicio = proximo_parpadeo = time.ticks_ms()
t_dht = time.ticks_add(time.ticks_ms(), -LEER_DHT_MS)
proximo_envio = time.ticks_ms()
t_wifi = time.ticks_ms()
proximo_ntp = time.ticks_ms()

cara()
conectar()

##### ----- BUCLE PRINCIPAL ----- #####

while True:
    ahora = time.ticks_ms()

    # Wi-Fi: reconecta sin bloquear
    if wlan.isconnected():
        led.on()
    else:
        led.off()
        if time.ticks_diff(ahora, t_wifi) >= 10000:
            t_wifi = ahora
            try:
                wlan.connect(WIFI, CLAVE)
            except OSError as e:
                print("Wi-Fi:", e)

    # Botón de despertar: solo cuenta una pulsación real (baja y sigue abajo 30 ms)
    b = btn_wake.value()
    if b == 0 and boton_antes == 1:
        time.sleep_ms(30)                    # antirrebote / filtro de ruido
        if btn_wake.value() == 0:
            presionado = True
            print("Botón presionado")
            despertar("botón")
        else:
            b = 1                            # fue ruido, no una pulsación
    if b == 1:
        presionado = False
    boton_antes = b
    if presionado:
        if not despierto:
            despierto = True
            datos()
        inicio = ahora                       # reinicia los 7 s mientras se mantiene

    # Una sola lectura del DHT11 para pantalla y servidor
    if time.ticks_diff(ahora, t_dht) >= LEER_DHT_MS:
        t_dht = ahora
        leer_dht()
        if despierto:
            datos()

    # Servidor
    if wlan.isconnected() and time.ticks_diff(ahora, proximo_envio) >= 0:
        ok = True
        if dht_ok:
            print(f"DHT11: {temp} °C | {hum} %")
            ok = enviar("/sensor", {"temperatura": temp, "humedad": hum})
        if ok:
            ok = pedir_comandos()
        espera = CADA_SENSOR_MS if ok else PAUSA_FALLO_MS
        proximo_envio = time.ticks_add(time.ticks_ms(), espera)

    # Hora por internet (NTP)
    if wlan.isconnected() and time.ticks_diff(ahora, proximo_ntp) >= 0:
        sincronizar_hora()

    # Cara dormida / despierta
    if despierto:
        if time.ticks_diff(ahora, inicio) >= AWAKE_MS:
            despierto = False
            cara()
            proximo_parpadeo = time.ticks_add(ahora, 3000)
    elif time.ticks_diff(ahora, proximo_parpadeo) >= 0:
        parpadeo()
        proximo_parpadeo = time.ticks_add(time.ticks_ms(), 3000)

    time.sleep_ms(20)
