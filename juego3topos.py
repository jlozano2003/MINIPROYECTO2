import time
import random
import os
import json
from datetime import datetime
from gpiozero import RGBLED, Button

# =======================================================
# CONFIGURACIÓN
# =======================================================
REMOTE_LOG_DIR = "."
LOG_FILE = "player_events.log"
PLAYER_LOG_PATH = os.path.join(REMOTE_LOG_DIR, LOG_FILE)
HOST_LOG_FILE = "game_status.log"

LOG_WRITTEN = False
PLAYER_ID = 10
GAME_ID = 3
GAME_STAGE = "R1"

# =======================================================
# FUNCIONES NUEVAS: sabotajes y asignaciones
# =======================================================


def leer_ultimo_sabotaje(stage):
    """Lee el último sabotaje del host para la stage indicada."""
    try:
        with open(HOST_LOG_FILE, "r") as f:
            lineas = [l.strip() for l in f.readlines()]
    except FileNotFoundError:
        return None

    ultimo = None
    for linea in lineas:
        if not linea or linea.startswith("#"):
            continue
        try:
            idx_space = linea.find(" ")
            payload = json.loads(linea[idx_space + 1:].strip())
        except Exception:
            continue
        if payload.get("stage") == stage and payload.get("Action") == "Sabotage":
            ultimo = {"Effect": payload.get(
                "Effect"), "Value": payload.get("Value")}
    return ultimo


def leer_ultima_asignacion():
    """Busca la última entrada con Action 'Assign' en game_status.log."""
    try:
        with open(HOST_LOG_FILE, "r") as f:
            lineas = [l.strip() for l in f.readlines()]
    except FileNotFoundError:
        return None, None

    asign = None
    for linea in lineas:
        if not linea or linea.startswith("#"):
            continue
        try:
            idx_space = linea.find(" ")
            payload = json.loads(linea[idx_space + 1:].strip())
        except Exception:
            continue
        if payload.get("Action") == "Assign" and "GameID" in payload:
            asign = (payload.get("stage"), payload.get("GameID"))
    return asign if asign else (None, None)


def leer_ultimo_score_local():
    """Devuelve el último Score registrado por el jugador."""
    try:
        with open(PLAYER_LOG_PATH, "r") as f:
            lineas = [l.strip() for l in f.readlines()]
    except FileNotFoundError:
        return 0

    for linea in reversed(lineas):
        if not linea or linea.startswith("#"):
            continue
        try:
            idx_space = linea.find(" ")
            payload = json.loads(linea[idx_space + 1:].strip())
        except Exception:
            continue
        if payload.get("Action") == "Ready" and "Score" in payload:
            try:
                return int(payload.get("Score", 0))
            except Exception:
                return 0
    return 0

# =======================================================
# LOBBY
# =======================================================


def log_lobby_join(player_id):
    os.makedirs(REMOTE_LOG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {"stage": "Lobby", "PlayerID": player_id, "Action": "Join"}
    linea = f"{timestamp} {json.dumps(payload)}\n"
    with open(PLAYER_LOG_PATH, "a") as f:
        f.write(linea)
    print(f"📨 Lobby: JOIN enviado -> {json.dumps(payload)}")
    print("   (en la tarea esto se 'envía por SSH' al host)")


def esperar_accepted_desde_host(player_id, timeout=None):
    print("\n⌛ Esperando 'Accepted' del host en game_status.log...")
    inicio = time.time()
    while True:
        try:
            with open(HOST_LOG_FILE, "r") as f:
                lineas = [l.strip() for l in f.readlines()]
        except FileNotFoundError:
            lineas = []
        for linea in lineas:
            if not linea or linea.startswith("#"):
                continue
            try:
                idx_space = linea.find(" ")
                json_str = linea[idx_space + 1:].strip()
                payload = json.loads(json_str)
            except Exception:
                continue
            if (payload.get("stage") == "Lobby" and
                payload.get("PlayerID") == player_id and
                    payload.get("Action") == "Accepted"):
                print(f"✅ Recibido del host: {json.dumps(payload)}")
                return True
        if timeout and (time.time() - inicio) > timeout:
            print("⛔ Tiempo de espera agotado esperando 'Accepted'.")
            return False
        time.sleep(1)


def log_lobby_ready(player_id):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {"stage": "Lobby", "PlayerID": player_id, "Action": "Ready"}
    linea = f"{timestamp} {json.dumps(payload)}\n"
    with open(PLAYER_LOG_PATH, "a") as f:
        f.write(linea)
    print(f"✅ Lobby: READY registrado -> {json.dumps(payload)}")


def lobby_handshake(player_id=PLAYER_ID):
    print("===== LOBBY / REGISTRO DE JUGADOR =====")
    log_lobby_join(player_id)
    ok = esperar_accepted_desde_host(player_id)
    if not ok:
        print("No se recibió Accepted. No se puede iniciar la partida.")
        return False
    log_lobby_ready(player_id)
    print("Jugador listo para iniciar las rondas.\n")
    return True


# =======================================================
# LOGGING DEL JUEGO
# =======================================================
def guardar_registro_json(score_final, resultado_str):
    global LOG_WRITTEN
    os.makedirs(REMOTE_LOG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if resultado_str == "VICTORIA":
        log_resultado = "Win"
    elif resultado_str == "TIMEOUT":
        log_resultado = "TimeOut"
    else:
        log_resultado = "Lose"
    data_dict = {
        "stage": GAME_STAGE,
        "PlayerID": PLAYER_ID,
        "Action": "Ready",
        "GameID": GAME_ID,
        "Result": log_resultado,
        "Score": score_final
    }
    log_entry = f"{timestamp} {json.dumps(data_dict)}\n"
    with open(PLAYER_LOG_PATH, "a") as f:
        f.write(log_entry)
    print(f"✅ REGISTRO GUARDADO: {log_entry.strip()}")
    LOG_WRITTEN = True


# =======================================================
# CONFIGURACIÓN DE GPIO Y VARIABLES
# =======================================================
PIN_R = 13
PIN_G = 6
PIN_B = 12
led_rgb = RGBLED(PIN_R, PIN_G, PIN_B)

boton_rojo = Button(27, pull_up=True)
boton_amarillo = Button(21, pull_up=True)
boton_blanco = Button(17, pull_up=True)
boton_azul = Button(18, pull_up=True)

COLORES = {
    "ROJO": ((1, 0, 0), boton_rojo),
    "AMARILLO": ((1, 1, 0), boton_amarillo),
    "BLANCO": ((1, 1, 1), boton_blanco),
    "AZUL": ((0, 0, 1), boton_azul)
}
TODOS_LOS_BOTONES = [boton_rojo, boton_amarillo, boton_blanco, boton_azul]


def secuencia_inicio():
    print("Iniciando secuencia de prueba (Rojo, Amarillo, Blanco, Azul)...")
    for nombre in ["ROJO", "AMARILLO", "BLANCO", "AZUL"]:
        color_rgb, _ = COLORES[nombre]
        led_rgb.color = color_rgb
        time.sleep(0.5)
    led_rgb.off()
    time.sleep(0.3)
    print("Secuencia terminada. ¡Prepárate!")
    time.sleep(0.5)


def jugar():
    global LOG_WRITTEN

    # === LEER SABOTAJE ===
    sabotaje = leer_ultimo_sabotaje(GAME_STAGE)
    TIEMPO_TOTAL = 15.0
    if sabotaje:
        effect = sabotaje.get("Effect")
        value = sabotaje.get("Value")
        try:
            value = int(value)
        except Exception:
            value = 0

        if effect == "Disable":
            print("⚠️ Sabotaje Disable: partida anulada.")
            guardar_registro_json(0, "TIMEOUT")
            return
        elif effect == "Delay":
            TIEMPO_TOTAL = max(5.0, 15.0 - value)
            print(f"⚠️ Sabotaje Delay: tiempo reducido a {TIEMPO_TOTAL:.1f}s")

    secuencia_inicio()
    aciertos = 0
    puntos = 0
    DURACION_COLOR = 0.5
    tiempo_inicio_juego = time.time()

    while time.time() - tiempo_inicio_juego < TIEMPO_TOTAL:
        pausa = random.uniform(1.0, 2.0)
        time.sleep(pausa)
        nombre_color, (color_rgb, boton_correcto) = random.choice(
            list(COLORES.items()))
        led_rgb.color = color_rgb
        print(
            f"\n🎯 ¡Apareció el color {nombre_color}! (tienes {DURACION_COLOR:.1f}s)")
        tiempo_inicio_color = time.time()
        pulsado_correcto = False
        while time.time() - tiempo_inicio_color < DURACION_COLOR:
            if boton_correcto.is_pressed:
                aciertos += 1
                puntos += 12.5
                pulsado_correcto = True
                print(
                    f"✅ ¡Correcto! (+12.5 puntos) | Aciertos: {aciertos} | Total: {puntos}")
                time.sleep(0.2)
                break
            for boton in TODOS_LOS_BOTONES:
                if boton.is_pressed and boton != boton_correcto:
                    print("❌ ¡Botón INCORRECTO!")
                    time.sleep(0.2)
            time.sleep(0.01)
        led_rgb.off()
        if not pulsado_correcto:
            print("⏳ No golpeaste a tiempo.")

    print("\n--- 🕹️ ¡FIN DEL JUEGO! ---")
    print(f"Aciertos totales: {aciertos}")
    print(f"Puntuación final: {puntos}")

    if aciertos >= 5:
        resultado_final = "VICTORIA"
        led_rgb.color = (0, 1, 0)
    else:
        resultado_final = "DERROTA"
        led_rgb.color = (1, 0, 0)

    # === SABOTAJE SCORESTEAL ===
    if sabotaje and sabotaje.get("Effect") == "ScoreSteal":
        anterior = leer_ultimo_score_local()
        try:
            porcentaje = int(sabotaje.get("Value", 0))
        except Exception:
            porcentaje = 0
        robo = max(0, round(anterior * (porcentaje / 100.0)))
        puntos = max(0, puntos - robo)
        print(f"⚠️ Sabotaje ScoreSteal: -{robo} puntos (anterior {anterior}).")

    if not LOG_WRITTEN:
        guardar_registro_json(puntos, resultado_final)
    time.sleep(1.5)
    led_rgb.off()


# =======================================================
# EJECUCIÓN PRINCIPAL
# =======================================================
try:
    if lobby_handshake(PLAYER_ID):
        stage_asign, game_id_asign = leer_ultima_asignacion()
        if stage_asign:
            GAME_STAGE = stage_asign
        if game_id_asign:
            GAME_ID = game_id_asign
        jugar()
    else:
        print("Saliendo: no se estableció conexión con el host.")
except KeyboardInterrupt:
    print("\nJuego cancelado por el usuario.")
finally:
    led_rgb.close()
    for boton in TODOS_LOS_BOTONES:
        boton.close()
    print("Pines liberados correctamente.")
