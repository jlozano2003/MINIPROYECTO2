import time
import random
import statistics
import os
import json
from gpiozero import DistanceSensor
from datetime import datetime
REMOTE_LOG_DIR = "."
LOG_FILENAME = "player_events.log"
PLAYER_LOG_PATH = os.path.join(REMOTE_LOG_DIR, LOG_FILENAME)
HOST_LOG_FILE = "game_status.log"
LOG_WRITTEN = False
PLAYER_ID = "P10"
GAME_ID = 4
GAME_STAGE = "R1"
ROUND_SECS = 5
MIN_TARGET_CM = 15
MAX_TARGET_CM = 100
PLAYERS = ["Jugador 1", "Jugador 2", "Jugador 3"]
sensor = DistanceSensor(echo=20, trigger=16, max_distance=2.0)


def log_lobby_join(player_id):
    if not os.path.exists(REMOTE_LOG_DIR):
        os.makedirs(REMOTE_LOG_DIR)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {"stage": "Lobby", "PlayerID": player_id, "Action": "Join"}
    with open(PLAYER_LOG_PATH, "a") as f:
        f.write(f"{ts} {json.dumps(payload)}\n")
    print(f"📨 Join enviado -> {payload}")


def esperar_accepted_desde_host(player_id, timeout=None):
    print("\n⌛ Esperando 'Accepted' del host...")
    start = time.time()
    while True:
        try:
            lines = [l.strip() for l in open(HOST_LOG_FILE).readlines()]
        except:
            lines = []
        for line in lines:
            if not line or line.startswith("#"):
                continue
            try:
                idx = line.find(" ")
                payload = json.loads(line[idx+1:])
            except:
                continue
            if payload.get("stage") == "Lobby" and payload.get("PlayerID") == player_id and payload.get("Action") == "Accepted":
                print(f"✅ Host respondió: {payload}")
                return True
        if timeout and time.time()-start > timeout:
            print("⛔ Timeout esperando Accepted.")
            return False
        time.sleep(1)


def log_lobby_ready(player_id):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {"stage": "Lobby", "PlayerID": player_id, "Action": "Ready"}
    with open(PLAYER_LOG_PATH, "a") as f:
        f.write(f"{ts} {json.dumps(payload)}\n")
    print(f"⚡ Ready enviado -> {payload}")


def lobby_handshake(player_id):
    print("===== LOBBY / HANDSHAKE =====")
    log_lobby_join(player_id)
    if not esperar_accepted_desde_host(player_id):
        print("No se pudo establecer conexión con host.")
        return False
    log_lobby_ready(player_id)
    print("✔ Jugador listo.\n")
    return True


def registrar_log_minijuego(score, result, player_id=PLAYER_ID, game_id=GAME_ID):
    global LOG_WRITTEN
    if not os.path.exists(REMOTE_LOG_DIR):
        os.makedirs(REMOTE_LOG_DIR)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {"stage": GAME_STAGE, "PlayerID": player_id,
               "Action": "Ready", "GameID": game_id, "Result": result, "Score": score}
    with open(PLAYER_LOG_PATH, "a") as f:
        f.write(f"{ts} {json.dumps(payload)}\n")
    print(f"📄 Log guardado: {payload}")


def read_once(avg_samples=7, sample_dt=0.04):
    vals = []
    for _ in range(avg_samples):
        d = sensor.distance*100
        if 3 <= d <= 350:
            vals.append(d)
        time.sleep(sample_dt)
    return statistics.median(vals) if vals else None


def countdown(s):
    t_end = time.time()+s
    while True:
        r = int(t_end-time.time())
        if r < 0:
            break
        print(f"\r⏳ Quedan {r}s...", end="", flush=True)
        time.sleep(0.2)
    print()


def play_turn(player, target):
    print(f"\n▶️ Intento {player}")
    print(f"   Objetivo: {target:.1f} cm")
    countdown(ROUND_SECS)
    dist = read_once()
    if dist is None:
        dist, err = 999.0, 999.0
    else:
        err = abs(dist-target)
    print(f"📏 Medición: {dist:.1f}cm → Error: {err:.1f}")
    registrar_log_minijuego(round(err, 1), "Turn",
                            player_id=player.replace(" ", ""))
    return dist, err


def main():
    global LOG_WRITTEN
    if not lobby_handshake(PLAYER_ID):
        return
    print("Reglas: coloca la mano a la distancia indicada en 15s.\n")
    target = random.uniform(MIN_TARGET_CM, MAX_TARGET_CM)
    print(f"🎯 Objetivo global: {target:.1f}cm")
    input("Presiona ENTER para comenzar...")
    results = []
    for p in PLAYERS:
        d, e = play_turn(p, target)
        results.append((p, d, e))
    winner = min(results, key=lambda x: x[2])
    winner_err = winner[2]
    print("\n=== RESULTADOS ===")
    for p, d, e in results:
        outcome = "Win" if e == winner_err else "Lose"
        registrar_log_minijuego(round(e, 1), outcome, p.replace(" ", ""))
        print(
            f" - {p:10s}: {d:5.1f} cm (error {e:4.1f}) {'🏆' if outcome=='Win' else ''}")
    if not LOG_WRITTEN:
        registrar_log_minijuego(round(winner_err, 1), "GameWin")
        LOG_WRITTEN = True
    print(f"\n🏆 GANADOR: {winner[0]} (error {winner_err:.1f} cm)\n")


if __name__ == "__main__":
    main()
