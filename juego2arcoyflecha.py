import pygame
import random
import math
import time
import os
import json
from datetime import datetime

# =========================================
# CONFIGURACIÓN BÁSICA
# =========================================
REMOTE_LOG_DIR = "."
LOG_FILE = "player_events.log"
PLAYER_LOG_PATH = os.path.join(REMOTE_LOG_DIR, LOG_FILE)
HOST_LOG_FILE = "game_status.log"
LOG_WRITTEN = False
PLAYER_ID = 10
GAME_ID = 2
GAME_STAGE = "R1"

# =========================================
# FUNCIONES NUEVAS: sabotajes y asignaciones
# =========================================


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
    """Devuelve el último Score del jugador para aplicar ScoreSteal."""
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


# =========================================
# LOBBY / HANDSHAKE
# =========================================
def log_lobby_join(player_id):
    os.makedirs(REMOTE_LOG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {"stage": "Lobby", "PlayerID": player_id, "Action": "Join"}
    with open(PLAYER_LOG_PATH, "a") as f:
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
            if (payload.get("stage") == "Lobby"
                and payload.get("PlayerID") == player_id
                    and payload.get("Action") == "Accepted"):
                print(f"✅ Recibido del host: {json.dumps(payload)}")
                return True

        if timeout and (time.time() - inicio) > timeout:
            print("⛔ Tiempo de espera agotado esperando 'Accepted'.")
            return False
        time.sleep(1)


def log_lobby_ready(player_id):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {"stage": "Lobby", "PlayerID": player_id, "Action": "Ready"}
    with open(PLAYER_LOG_PATH, "a") as f:
        f.write(f"{timestamp} {json.dumps(payload)}\n")
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


# =========================================
# LOGGING DEL JUEGO
# =========================================
def guardar_registro_json(score_final, resultado):
    global LOG_WRITTEN
    os.makedirs(REMOTE_LOG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if resultado == "VICTORIA":
        log_resultado = "Win"
    elif resultado == "TIEMPO_AGOTADO":
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
    try:
        with open(PLAYER_LOG_PATH, 'a') as f:
            f.write(log_entry)
        print(f"✅ REGISTRO GUARDADO: {log_entry.strip()}")
        LOG_WRITTEN = True
    except Exception as e:
        print(f"❌ Error al escribir el registro: {e}")


# =========================================
# FLUJO PRINCIPAL DEL JUEGO
# =========================================
if not lobby_handshake(PLAYER_ID):
    raise SystemExit("Saliendo: no se estableció conexión con el host.")

# Leer asignación (stage y GameID)
stage_asign, game_id_asign = leer_ultima_asignacion()
if stage_asign:
    GAME_STAGE = stage_asign
if game_id_asign:
    GAME_ID = game_id_asign

# Leer sabotaje (Delay, Disable, ScoreSteal)
sabotaje = leer_ultimo_sabotaje(GAME_STAGE)
GAME_DURATION_SECONDS = 15
if sabotaje:
    effect = sabotaje.get("Effect")
    value = sabotaje.get("Value")
    try:
        value = int(value)
    except Exception:
        value = 0
    if effect == "Disable":
        print("⚠️ Sabotaje Disable: no se puede jugar. Registrando TimeOut.")
        guardar_registro_json(0, "TIEMPO_AGOTADO")
        raise SystemExit("Partida anulada por sabotaje Disable.")
    elif effect == "Delay":
        GAME_DURATION_SECONDS = max(5, 15 - value)
        print(
            f"⚠️ Sabotaje Delay: duración reducida a {GAME_DURATION_SECONDS}s.")

# Configuración de Pygame
pygame.init()
WIDTH, HEIGHT = 800, 600
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Juego de Arco y Flecha")

WHITE = (255, 200, 200)
RED = (255, 100, 0)
BLACK = (0, 0, 0)
GREEN = (0, 255, 0)
WINNING_SCORE = 7

# Carga de imágenes con fallback
try:
    fondo_img = pygame.image.load("fondo.png")
    fondo_img = pygame.transform.scale(fondo_img, (WIDTH, HEIGHT))
except pygame.error:
    fondo_img = None

try:
    bow_img = pygame.image.load("bow.png")
    bow_img = pygame.transform.scale(bow_img, (150, 50))
except pygame.error:
    bow_img = pygame.Surface((150, 50))
    bow_img.fill((150, 75, 0))

try:
    arrow_img_orig = pygame.image.load("arrow.png")
    arrow_img_orig = pygame.transform.scale(arrow_img_orig, (100, 20))
except pygame.error:
    arrow_img_orig = pygame.Surface((100, 20))
    arrow_img_orig.fill((0, 0, 0))

try:
    target_img = pygame.image.load("target.png")
    target_img = pygame.transform.scale(target_img, (80, 80))
except pygame.error:
    target_img = pygame.Surface((80, 80), pygame.SRCALPHA)
    pygame.draw.circle(target_img, RED, (40, 40), 40)

# Variables del juego
bow_x, bow_y = 50, HEIGHT//2-25
arrow_x, arrow_y = bow_x+50, bow_y+15
arrow_speed_base = 15
arrow_speed_x = 0
arrow_speed_y = 0
arrow_angle_launch = 0
target_x, target_y = WIDTH-100, random.randint(100, HEIGHT-180)
target_speed = 4
target_direction = -1
arrow_flying = False
score = 0
font = pygame.font.SysFont(None, 36)
big_font = pygame.font.SysFont(None, 72)
game_over = False
start_time = time.time()
game_result = ""


def draw_text(text, font, color, x, y):
    text_surface = font.render(text, True, color)
    screen.blit(text_surface, (x, y))


def draw():
    if fondo_img:
        screen.blit(fondo_img, (0, 0))
    else:
        screen.fill(WHITE)
    screen.blit(bow_img, (bow_x, bow_y))
    rotated_arrow = pygame.transform.rotate(
        arrow_img_orig, -arrow_angle_launch)
    arrow_rect = rotated_arrow.get_rect(center=(arrow_x, arrow_y))
    screen.blit(rotated_arrow, arrow_rect.topleft)
    screen.blit(target_img, (target_x, target_y))
    draw_text(f"Puntaje: {score}/{WINNING_SCORE}", font, RED, 10, 10)
    elapsed = time.time()-start_time
    remaining = max(0, GAME_DURATION_SECONDS-int(elapsed))
    draw_text(f"Tiempo: {remaining}s", font, RED, WIDTH-150, 10)
    if game_over:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        screen.blit(overlay, (0, 0))
        color = GREEN if game_result == "VICTORIA" else RED
        draw_text(game_result, big_font, color, WIDTH//2-200, HEIGHT//2-50)
        draw_text(f"Puntaje Final: {score}", font,
                  WHITE, WIDTH//2-120, HEIGHT//2+30)
    pygame.display.flip()


def check_collision():
    rotated_arrow = pygame.transform.rotate(
        arrow_img_orig, -arrow_angle_launch)
    arrow_rect = rotated_arrow.get_rect(center=(arrow_x, arrow_y))
    target_rect = target_img.get_rect(topleft=(target_x, target_y))
    return arrow_rect.colliderect(target_rect)


clock = pygame.time.Clock()
running = True
while running:
    clock.tick(60)
    if not game_over and (time.time()-start_time >= GAME_DURATION_SECONDS or score >= WINNING_SCORE):
        game_over = True
        if score >= WINNING_SCORE:
            game_result = "VICTORIA"
        else:
            game_result = "TIEMPO_AGOTADO"

        # Aplicar ScoreSteal si existe
        if sabotaje and sabotaje.get("Effect") == "ScoreSteal":
            anterior = leer_ultimo_score_local()
            try:
                porcentaje = int(sabotaje.get("Value", 0))
            except Exception:
                porcentaje = 0
            robo = max(0, round(anterior * (porcentaje / 100.0)))
            score = max(0, score - robo)
            print(
                f"⚠️ Sabotaje ScoreSteal: -{robo} puntos (previo {anterior}).")

        if not LOG_WRITTEN:
            guardar_registro_json(score, game_result)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE and not game_over:
            arrow_flying = True
            radians = math.radians(arrow_angle_launch)
            arrow_speed_x = arrow_speed_base*math.cos(radians)
            arrow_speed_y = arrow_speed_base*math.sin(radians)
            arrow_x, arrow_y = bow_x+50, bow_y+15

    if not game_over:
        if arrow_flying:
            arrow_x += arrow_speed_x
            arrow_y += arrow_speed_y
            if check_collision():
                score += 1
                arrow_flying = False
                arrow_x, arrow_y = bow_x+50, bow_y+15
                target_y = random.randint(100, HEIGHT-180)
            elif arrow_x > WIDTH or arrow_x < 0 or arrow_y < 0 or arrow_y > HEIGHT:
                arrow_flying = False
                arrow_x, arrow_y = bow_x+50, bow_y+15

        target_y += target_speed*target_direction
        if target_y <= 50 or target_y >= HEIGHT-130:
            target_direction *= -1
    draw()

pygame.quit()
