import time
import random
import json
import sys
import select
import termios
import tty
from datetime import datetime

PLAYER_LOG_FILE = "player_events.log"
HOST_LOG_FILE = "game_status.log"

TEXTOS_PARA_JUEGO = [
    "La Raspberry Pi es una computadora pequeña",
    "El protocolo SSH es seguro para la red",
    "TIC is Among Us",
    "Programar en Python es muy divertido",
    "Sensores de temperatura y ultrasonido"
]

# =========================
#  AÑADIDOS: Sabotajes y asignación
# =========================


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
    """Busca el último registro de minijuego en player_events.log y retorna su Score."""
    try:
        with open(PLAYER_LOG_FILE, "r") as f:
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
        if payload.get("Action") == "Ready" and "GameID" in payload and "Score" in payload:
            try:
                return int(payload.get("Score", 0))
            except Exception:
                return 0
    return 0

# =========================
#  Lobby / Handshake
# =========================


def log_lobby_join(player_id):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {"stage": "Lobby", "PlayerID": player_id, "Action": "Join"}
    with open(PLAYER_LOG_FILE, "a") as f:
        f.write(f"{timestamp} {json.dumps(payload)}\n")
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
        if timeout is not None and (time.time() - inicio) > timeout:
            print("⛔ Tiempo de espera agotado esperando 'Accepted'.")
            return False
        time.sleep(1)


def log_lobby_ready(player_id):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {"stage": "Lobby", "PlayerID": player_id, "Action": "Ready"}
    with open(PLAYER_LOG_FILE, "a") as f:
        f.write(f"{timestamp} {json.dumps(payload)}\n")
    print(f"✅ Lobby: READY registrado -> {json.dumps(payload)}")


def lobby_handshake(player_id=1):
    print("===== LOBBY / REGISTRO DE JUGADOR =====")
    log_lobby_join(player_id)
    ok = esperar_accepted_desde_host(player_id)
    if not ok:
        print("No se recibió Accepted. No se puede iniciar la partida.")
        return False
    log_lobby_ready(player_id)
    print("Jugador listo para iniciar las rondas.\n")
    return True

# =========================
#  Entrada con tiempo real
# =========================


def input_con_tiempo_real(prompt, tiempo_limite):
    print(prompt, end='', flush=True)
    texto_buffer = []
    inicio = time.time()
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(sys.stdin.fileno())
        while True:
            restante = tiempo_limite - (time.time() - inicio)
            if restante <= 0:
                break
            rlist, _, _ = select.select([sys.stdin], [], [], restante)
            if rlist:
                caracter = sys.stdin.read(1)
                if caracter in ['\n', '\r']:
                    print()
                    break
                elif caracter == '\x7f' and texto_buffer:
                    texto_buffer.pop()
                    print('\b \b', end='', flush=True)
                else:
                    texto_buffer.append(caracter)
                    print(caracter, end='', flush=True)
            else:
                break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    tiempo_usado = time.time() - inicio
    return "".join(texto_buffer), tiempo_usado >= tiempo_limite

# =========================
#  Logging del minijuego
# =========================


def registrar_evento_minijuego(player_id, stage, game_id, result, score):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "stage": stage,
        "PlayerID": player_id,
        "Action": "Ready",
        "GameID": game_id,
        "Result": result,
        "Score": score
    }
    with open(PLAYER_LOG_FILE, "a") as f:
        f.write(f"{timestamp} {json.dumps(payload)}\n")
    print(f"✅ LOG GUARDADO: {json.dumps(payload)}")

# =========================
#  Minijuego de tipeo
# =========================


def minijuego_tipeo_simple(player_id=1, stage="R1", game_id=3):
    # --- Sabotaje ---
    sabotaje = leer_ultimo_sabotaje(stage)
    tiempo_limite = 15.0

    if sabotaje:
        effect = sabotaje.get("Effect")
        value = sabotaje.get("Value")
        try:
            value = int(value)
        except Exception:
            pass
        if effect == "Disable":
            registrar_evento_minijuego(player_id, stage, game_id, "TimeOut", 0)
            print("⚠️ Sabotaje aplicado: Disable → TimeOut.")
            return 0
        if effect == "Delay" and isinstance(value, int):
            tiempo_limite = max(5.0, 15.0 - value)
            print(
                f"⚠️ Sabotaje Delay: tiempo reducido a {tiempo_limite:.0f}s.")

    # --- Juego original ---
    texto_objetivo = random.choice(TEXTOS_PARA_JUEGO)
    print("\n" + "="*40)
    print("      MINIJUEGO DE TIPEO RÁPIDO")
    print("="*40)
    print(f"OBJETIVO: Escribe esta frase EXACTA:\n👉  {texto_objetivo}  👈")
    print("\nPresiona ENTER para empezar el tiempo (15s)...")
    input()
    print("\n⚡ ¡YA! ¡ESCRIBE! ⚡")

    texto_usuario, tiempo_agotado = input_con_tiempo_real(
        "Tu respuesta: ", tiempo_limite)

    buenas = sum(1 for i in range(min(len(texto_usuario), len(
        texto_objetivo))) if texto_usuario[i] == texto_objetivo[i])
    malas = max(len(texto_objetivo), len(texto_usuario)) - buenas
    precision = (buenas / len(texto_objetivo)) * \
        100 if len(texto_objetivo) else 0
    penalidad_error = malas * 5
    score = int(max(0, min(100, precision - penalidad_error)))

    result = "Win" if score >= 60 else "TimeOut" if tiempo_agotado else "Lose"

    # --- Sabotaje ScoreSteal ---
    if sabotaje and sabotaje.get("Effect") == "ScoreSteal":
        anterior = leer_ultimo_score_local()
        try:
            porcentaje = int(sabotaje.get("Value", 0))
        except Exception:
            porcentaje = 0
        robo = max(0, round(anterior * (porcentaje / 100.0)))
        score = max(0, score - robo)
        print(f"⚠️ Sabotaje ScoreSteal: -{robo} puntos (anterior {anterior}).")

    print("-" * 30)
    print(f"Puntaje Final: {score}/100")
    print(f"Resultado:     {result}")
    print("-" * 30)
    registrar_evento_minijuego(player_id, stage, game_id, result, score)
    return score


# =========================
#  Main
# =========================
if __name__ == "__main__":
    try:
        player_id = 1
        if lobby_handshake(player_id):
            stage_asign, game_id_asign = leer_ultima_asignacion()
            stage = stage_asign if stage_asign else "R1"
            game_id = game_id_asign if game_id_asign else 3
            minijuego_tipeo_simple(player_id=player_id,
                                   stage=stage, game_id=game_id)
    except KeyboardInterrupt:
        print("\nCancelado.")
