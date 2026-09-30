#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
SISTEMA VIGIL - VIGIL AGENT & WEB DASHBOARD (v2.5)
==============================================================================
NOC, Observabilidade de Servidores, Monitor Térmico, Spotify Hub & DevOps Deck
==============================================================================
"""

import time
import os
import json
import socket
import collections
import threading
import urllib.request
import urllib.parse
import subprocess
import base64
try:
    import psutil
    PSUTIL_AVAILABLE = True
except Exception:
    psutil = None
    PSUTIL_AVAILABLE = False
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler

try:
    from PIL import Image
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

# ==============================================================================
# LOGS DO SISTEMA EM MEMÓRIA (RING BUFFER)
# ==============================================================================
logs_lock = threading.Lock()
system_logs = collections.deque(maxlen=60)

def add_log(event_type, msg):
    with logs_lock:
        system_logs.append({
            "ts": time.strftime("%H:%M:%S"),
            "type": event_type,  # 'info', 'cmd', 'warn', 'alert'
            "msg": msg
        })

add_log("info", "Vigil Agent v2.5 iniciado com sucesso na porta 5000")

# ==============================================================================
# ESTADO & INTEGRAÇÃO SPOTIFY
# ==============================================================================
spotify_lock = threading.Lock()
spotify_state = {
    "active": False,
    "is_playing": False,
    "track": "Nenhuma música",
    "artist": "Spotify Ocioso",
    "album": "",
    "progress_ms": 0,
    "duration_ms": 0,
    "volume": 75,
    "art_id": "",
    "art_url": "/api/spotify/art.jpg"
}
spotify_art_bytes = b""
spotify_last_art_src = ""
spotify_access_token = ""
spotify_token_exp = 0.0

def load_spotify_config():
    for p in ["/home/leo/spotify_config.json", os.path.join(os.path.dirname(__file__), "..", "spotify_config.json"), "spotify_config.json"]:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return None

def get_spotify_token():
    global spotify_access_token, spotify_token_exp
    now = time.time()
    if spotify_access_token and now < spotify_token_exp - 60:
        return spotify_access_token
    cfg = load_spotify_config()
    if not cfg or not cfg.get("refresh_token"):
        return None
    try:
        auth_str = f"{cfg['client_id']}:{cfg['client_secret']}"
        b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
        data = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "refresh_token": cfg["refresh_token"]
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://accounts.spotify.com/api/token",
            data=data,
            headers={
                "Authorization": f"Basic {b64_auth}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            spotify_access_token = res.get("access_token", "")
            spotify_token_exp = now + int(res.get("expires_in", 3600))
            return spotify_access_token
    except Exception:
        return None

def update_spotify_art(img_url, track_id):
    global spotify_art_bytes, spotify_last_art_src
    if not img_url or img_url == spotify_last_art_src:
        return
    try:
        req = urllib.request.Request(img_url, headers={"User-Agent": "VigilAgent/2.5"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read()
        if PIL_AVAILABLE:
            im = Image.open(io.BytesIO(raw)).convert("RGB")
            im = im.resize((80, 80), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            im.save(out, format="JPEG", quality=82, optimize=False, progressive=False)
            spotify_art_bytes = out.getvalue()
        else:
            spotify_art_bytes = raw
        spotify_last_art_src = img_url
    except Exception:
        pass

def spotify_command(action):
    token = get_spotify_token()
    if not token:
        add_log("warn", "Comando Spotify rejeitado: token não configurado")
        return False
    try:
        with spotify_lock:
            currently_playing = spotify_state.get("is_playing", False)
        if action == "toggle":
            action = "pause" if currently_playing else "play"
        if action == "play":
            url = "https://api.spotify.com/v1/me/player/play"
            method = "PUT"
        elif action == "pause":
            url = "https://api.spotify.com/v1/me/player/pause"
            method = "PUT"
        elif action == "next":
            url = "https://api.spotify.com/v1/me/player/next"
            method = "POST"
        elif action == "prev":
            url = "https://api.spotify.com/v1/me/player/previous"
            method = "POST"
        elif action.startswith("volume"):
            vol = 75
            if ":" in action:
                vol = max(0, min(100, int(action.split(":")[1])))
            url = f"https://api.spotify.com/v1/me/player/volume?volume_percent={vol}"
            method = "PUT"
            with spotify_lock:
                spotify_state["volume"] = vol
        else:
            return False
        req = urllib.request.Request(url, data=b"", method=method, headers={
            "Authorization": f"Bearer {token}",
            "Content-Length": "0"
        })
        with urllib.request.urlopen(req, timeout=4) as resp:
            ok = resp.status in [200, 202, 204]
            if ok:
                add_log("info", f"Spotify comando executado: {action}")
            return ok
    except Exception as e:
        add_log("warn", f"Falha no comando Spotify '{action}': {str(e)[:30]}")
        return False

def execute_devops_command(cmd_name):
    """Executa comandos rápidos do Vigil Command Deck com segurança"""
    try:
        if cmd_name == "restart_gaia":
            subprocess.Popen(["sh", "-c", "docker restart $(docker ps -q --filter ancestor=gaia) 2>/dev/null || docker restart gaia 2>/dev/null || true"])
            msg = "Container Gaia reiniciado"
            add_log("cmd", msg)
            return True, msg
        elif cmd_name == "restart_agro":
            subprocess.Popen(["sh", "-c", "docker restart $(docker ps -q --filter name=agro) 2>/dev/null || true"])
            msg = "Container Agroclima reiniciado"
            add_log("cmd", msg)
            return True, msg
        elif cmd_name == "restart_mqtt":
            subprocess.Popen(["sh", "-c", "docker restart $(docker ps -q --filter name=mosquitto) 2>/dev/null || systemctl restart mosquitto 2>/dev/null || true"])
            msg = "Broker Mosquitto MQTT reiniciado"
            add_log("cmd", msg)
            return True, msg
        elif cmd_name == "wol":
            mac_bytes = bytes.fromhex("FFFFFFFFFFFF")
            pkt = b"\xff" * 6 + mac_bytes * 16
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                s.sendto(pkt, ("255.255.255.255", 9))
            msg = "Magic Packet WOL transmitido na LAN"
            add_log("cmd", msg)
            return True, msg
        elif cmd_name == "clear_cache":
            subprocess.Popen(["sh", "-c", "sync"])
            msg = "Buffers do SO sincronizados (sync)"
            add_log("cmd", msg)
            return True, msg
        elif cmd_name == "test_tunnel":
            t0 = time.time()
            req = urllib.request.Request("https://server1.taila7d06b.ts.net:10000/api/status", headers={"User-Agent": "VigilDeck/2.5"})
            with urllib.request.urlopen(req, timeout=4) as r:
                ms = int((time.time() - t0) * 1000)
                msg = f"Túnel OK ({ms}ms)"
                add_log("cmd", f"Healthcheck Túnel HTTPS: {msg}")
                return (r.status == 200), msg
    except Exception as e:
        err_msg = f"Erro: {str(e)[:32]}"
        add_log("warn", f"Comando '{cmd_name}' falhou: {err_msg}")
        return False, err_msg
    return False, "Comando desconhecido"

def spotify_sampler():
    global spotify_state
    while True:
        try:
            token = get_spotify_token()
            if token:
                req = urllib.request.Request(
                    "https://api.spotify.com/v1/me/player",
                    headers={"Authorization": f"Bearer {token}"}
                )
                with urllib.request.urlopen(req, timeout=4) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        item = data.get("item") or {}
                        if item:
                            track_name = item.get("name") or "Faixa Desconhecida"
                            artists = ", ".join([a.get("name", "") for a in item.get("artists", []) if a.get("name")])
                            album_obj = item.get("album") or {}
                            album_name = album_obj.get("name") or ""
                            images = album_obj.get("images") or []
                            img_url = images[-1]["url"] if images else ""
                            if len(images) >= 2:
                                img_url = images[1]["url"]
                            track_id = (item.get("id") or track_name)[:12]
                            update_spotify_art(img_url, track_id)
                            with spotify_lock:
                                spotify_state = {
                                    "active": True,
                                    "is_playing": bool(data.get("is_playing", False)),
                                    "track": track_name,
                                    "artist": artists or "Artista",
                                    "album": album_name,
                                    "progress_ms": int(data.get("progress_ms") or 0),
                                    "duration_ms": int(item.get("duration_ms") or 0),
                                    "volume": int((data.get("device") or {}).get("volume_percent") or spotify_state.get("volume", 75)),
                                    "art_id": track_id,
                                    "art_url": f"/api/spotify/art.jpg?id={track_id}"
                                }
                    elif resp.status == 204:
                        with spotify_lock:
                            spotify_state["is_playing"] = False
                            if not spotify_state.get("active"):
                                spotify_state["track"] = "Nenhuma música"
                                spotify_state["artist"] = "Spotify Ocioso"
        except Exception:
            pass
        time.sleep(2.0)

# Ring buffer de histórico para gráficos em tempo real (últimos 30 pontos)
history_lock = threading.Lock()
history_cpu = collections.deque(maxlen=30)
history_temp = collections.deque(maxlen=30)
history_ram = collections.deque(maxlen=30)

class MockNet:
    bytes_recv = 1024 * 1024
    bytes_sent = 512 * 1024

last_net = psutil.net_io_counters() if PSUTIL_AVAILABLE else MockNet()
last_time = time.time()

current_metrics = {
    "cpu": 0.0,
    "cpu_temp": 0.0,
    "ram": 0.0,
    "disk": 0.0,
    "rx_kbps": 0.0,
    "tx_kbps": 0.0,
    "uptime_sec": 0,
    "alert_level": "normal",
    "alert_msg": "Sistema operando normalmente",
    "alerts": []
}

def get_cpu_temp():
    if not PSUTIL_AVAILABLE:
        return 46.5
    try:
        temps = psutil.sensors_temperatures()
        if 'coretemp' in temps and len(temps['coretemp']) > 0:
            return round(temps['coretemp'][0].current, 1)
        for key, entries in temps.items():
            if entries and len(entries) > 0:
                return round(entries[0].current, 1)
    except Exception:
        pass
    try:
        if os.path.exists('/sys/class/thermal/thermal_zone2/temp'):
            return round(int(open('/sys/class/thermal/thermal_zone2/temp').read().strip()) / 1000.0, 1)
        elif os.path.exists('/sys/class/thermal/thermal_zone0/temp'):
            return round(int(open('/sys/class/thermal/thermal_zone0/temp').read().strip()) / 1000.0, 1)
    except Exception:
        pass
    return 0.0

def check_port(host, port, timeout=0.12):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False

def get_services_status():
    t0 = time.time()
    s_gaia = check_port('127.0.0.1', 3000)
    s_agro = check_port('127.0.0.1', 3001)
    s_pg = check_port('127.0.0.1', 5432)
    s_mqtt = check_port('127.0.0.1', 1883)
    s_nginx = check_port('127.0.0.1', 80)
    ping_ms = max(1, int((time.time() - t0) * 1000))
    
    return [
        {"name": "Gaia Server", "port": 3000, "status": s_gaia, "type": "API / Backend"},
        {"name": "Agroclima Server", "port": 3001, "status": s_agro, "type": "Microserviço"},
        {"name": "PostgreSQL DB", "port": 5432, "status": s_pg, "type": "Banco de Dados"},
        {"name": "Mosquitto MQTT", "port": 1883, "status": s_mqtt, "type": "Broker IoT"},
        {"name": "Nginx Proxy", "port": 80, "status": s_nginx, "type": "Reverse Proxy"}
    ], ping_ms

def get_top_processes(limit=5):
    """Retorna os top processos consumidores de CPU e memória"""
    if not PSUTIL_AVAILABLE:
        return [
            {"pid": 1240, "name": "node (gaia)", "cpu": 3.8, "mem": 7.4},
            {"pid": 2315, "name": "postgres", "cpu": 1.9, "mem": 11.2},
            {"pid": 3142, "name": "dockerd", "cpu": 1.5, "mem": 5.8},
            {"pid": 4510, "name": "tailscaled", "cpu": 0.8, "mem": 3.2},
            {"pid": 5894, "name": "python3 (agent)", "cpu": 0.6, "mem": 2.1}
        ]
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
        try:
            info = p.info
            name = info.get('name') or ''
            if not name or name.startswith('[') or name in ['kworker', 'systemd']:
                continue
            cpu = float(info.get('cpu_percent') or 0.0)
            mem = round(float(info.get('memory_percent') or 0.0), 1)
            procs.append({
                "pid": info['pid'],
                "name": name,
                "cpu": cpu,
                "mem": mem
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    procs.sort(key=lambda x: (x['cpu'], x['mem']), reverse=True)
    return procs[:limit]

def get_field_station_metrics():
    try:
        req = urllib.request.Request("http://127.0.0.1:3000/api/estacoes", headers={"User-Agent": "VigilAgent/2.5"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if isinstance(data, list) and len(data) > 0:
                st = data[0]
                return {
                    "station": st.get("cod_estacao", "G00001"),
                    "nome": st.get("nome", "Estacao G00001"),
                    "cultura": st.get("cultura", "Cafe Arabica"),
                    "status": st.get("status", "ONLINE"),
                    "temp": float(st.get("temp_ref") or 0.0),
                    "umid": float(st.get("umidade") or 0.0),
                    "pressao": float(st.get("pressao") or 0.0),
                    "vpd": float(st.get("vpd") or 0.0),
                    "et0": float(st.get("et0") or 0.0),
                    "itu": float(st.get("itu") or 0.0),
                    "sec_ago": int(st.get("segundos_desde_ultimo_envio") or 0)
                }
    except Exception:
        pass
    return {
        "station": "G00001",
        "nome": "Estacao G00001",
        "cultura": "Cafe Arabica",
        "status": "OFFLINE",
        "temp": 0.0,
        "umid": 0.0,
        "pressao": 0.0,
        "vpd": 0.0,
        "et0": 0.0,
        "itu": 0.0,
        "sec_ago": 9999
    }

def background_sampler():
    """Coleta métricas continuamente a cada 1.2s para alimentar gráficos e alertas"""
    global last_net, last_time, current_metrics
    last_alert_logged = "normal"
    while True:
        try:
            now = time.time()
            dt = max(now - last_time, 0.5)
            if PSUTIL_AVAILABLE:
                curr_net = psutil.net_io_counters()
                rx_kbps = round(((curr_net.bytes_recv - last_net.bytes_recv) / 1024.0) / dt, 1)
                tx_kbps = round(((curr_net.bytes_sent - last_net.bytes_sent) / 1024.0) / dt, 1)
                last_net = curr_net
                last_time = now

                cpu = psutil.cpu_percent(interval=None)
                cpu_temp = get_cpu_temp()
                ram = psutil.virtual_memory().percent
                disk = psutil.disk_usage('/').percent
                uptime = int(now - psutil.boot_time())
            else:
                rx_kbps = 4.5
                tx_kbps = 1.2
                cpu = 14.2
                cpu_temp = 46.5
                ram = 43.8
                disk = 12.0
                uptime = 934000

            with history_lock:
                history_cpu.append(cpu)
                history_temp.append(cpu_temp)
                history_ram.append(ram)

            alerts = []
            level = "normal"

            if cpu_temp >= 75.0:
                alerts.append(f"TEMPERATURA CRÍTICA: CPU em {cpu_temp:.1f}°C")
                level = "critical"
            elif cpu_temp >= 65.0:
                alerts.append(f"Temperatura elevada: CPU em {cpu_temp:.1f}°C")
                if level != "critical": level = "warning"

            if cpu >= 90.0:
                alerts.append(f"Sobrecarga de CPU: {cpu:.1f}%")
                if level != "critical": level = "warning"

            if ram >= 90.0:
                alerts.append(f"Memória RAM alta: {ram:.1f}% em uso")
                if level != "critical": level = "warning"

            msg = "Sistema operando normalmente"
            if alerts:
                msg = alerts[0]

            if level != last_alert_logged:
                if level != "normal":
                    add_log("alert" if level == "critical" else "warn", msg)
                else:
                    add_log("info", "Alertas normalizados: Sistema estável")
                last_alert_logged = level

            current_metrics = {
                "cpu": cpu,
                "cpu_temp": cpu_temp,
                "ram": ram,
                "disk": disk,
                "rx_kbps": rx_kbps,
                "tx_kbps": tx_kbps,
                "uptime_sec": uptime,
                "alert_level": level,
                "alert_msg": msg,
                "alerts": alerts
            }
        except Exception:
            pass
        time.sleep(1.2)

# ==============================================================================
# HTML DASHBOARD (VIGIL WEB v2.5 — GLASSMORPHISM & DEVOPS COMMAND DECK)
# ==============================================================================
HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Vigil // Centro de Controle & Observabilidade</title>
  <meta name="theme-color" content="#0b0f19">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <link rel="manifest" href="/manifest.json">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #0b0f19;
      --card-bg: rgba(18, 24, 39, 0.82);
      --card-border: rgba(255, 255, 255, 0.08);
      --primary: #10b981;
      --primary-glow: rgba(16, 185, 129, 0.28);
      --accent: #06b6d4;
      --warning: #f59e0b;
      --danger: #ef4444;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --spotify: #1db954;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Outfit', -apple-system, sans-serif;
      background: radial-gradient(circle at 10% 10%, #152238 0%, #0b0f19 70%);
      color: var(--text);
      min-height: 100vh;
      padding: 16px 14px 60px;
    }
    .container { max-width: 1180px; margin: 0 auto; }
    
    /* Header */
    header {
      display: flex; justify-content: space-between; align-items: center;
      margin-bottom: 16px; flex-wrap: wrap; gap: 14px;
      border-bottom: 1px solid var(--card-border); padding-bottom: 14px;
    }
    .logo-area { display: flex; align-items: center; gap: 12px; }
    .logo-icon {
      width: 44px; height: 44px; border-radius: 12px;
      background: linear-gradient(135deg, #10b981, #06b6d4);
      display: flex; align-items: center; justify-content: center;
      font-weight: 800; font-size: 24px; color: #fff;
      box-shadow: 0 0 20px var(--primary-glow);
    }
    .title h1 { font-size: 22px; font-weight: 700; letter-spacing: -0.5px; }
    .title p { font-size: 12px; color: var(--text-muted); }
    
    .header-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .btn-action {
      background: rgba(255, 255, 255, 0.05); border: 1px solid var(--card-border);
      color: var(--text); padding: 7px 12px; border-radius: 20px; font-size: 12px;
      cursor: pointer; display: flex; align-items: center; gap: 6px; transition: all 0.2s;
    }
    .btn-action:hover { background: rgba(255, 255, 255, 0.12); border-color: rgba(255,255,255,0.2); }
    .badge-status {
      display: inline-flex; align-items: center; gap: 6px;
      padding: 6px 14px; border-radius: 30px; font-size: 12px; font-weight: 600;
      background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3);
    }
    .pulse-dot {
      width: 8px; height: 8px; border-radius: 50%; background: #10b981;
      animation: pulse 1.8s infinite;
    }
    @keyframes pulse {
      0% { transform: scale(0.9); opacity: 1; box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
      70% { transform: scale(1.1); opacity: 0.8; box-shadow: 0 0 0 8px rgba(16, 185, 129, 0); }
      100% { transform: scale(0.9); opacity: 1; }
    }

    /* Ecosystem Quick Launch Bar */
    .ecosystem-bar {
      display: flex; gap: 10px; margin-bottom: 18px; overflow-x: auto; padding-bottom: 4px;
    }
    .eco-chip {
      background: rgba(255, 255, 255, 0.03); border: 1px solid var(--card-border);
      border-radius: 10px; padding: 7px 14px; font-size: 12px; font-weight: 500;
      color: var(--text); text-decoration: none; display: flex; align-items: center; gap: 8px;
      white-space: nowrap; transition: all 0.2s;
    }
    .eco-chip:hover {
      background: rgba(255, 255, 255, 0.08); border-color: var(--primary);
      transform: translateY(-1px);
    }
    .eco-dot { width: 6px; height: 6px; border-radius: 50%; background: #10b981; }

    /* Alert Banner */
    .alert-banner {
      border-radius: 12px; padding: 12px 18px; margin-bottom: 20px;
      display: flex; align-items: center; justify-content: space-between; gap: 14px;
      transition: all 0.3s ease;
    }
    .alert-normal { background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.25); }
    .alert-warning { background: rgba(245, 158, 11, 0.12); border: 1px solid rgba(245, 158, 11, 0.4); animation: alertPulse 2s infinite; }
    .alert-critical { background: rgba(239, 68, 68, 0.18); border: 1px solid rgba(239, 68, 68, 0.6); box-shadow: 0 0 25px rgba(239, 68, 68, 0.3); animation: alertFlash 1.2s infinite; }
    @keyframes alertPulse { 0%, 100% { border-color: rgba(245, 158, 11, 0.4); } 50% { border-color: rgba(245, 158, 11, 0.85); } }
    @keyframes alertFlash { 0%, 100% { background: rgba(239, 68, 68, 0.18); } 50% { background: rgba(239, 68, 68, 0.32); } }
    .alert-left { display: flex; align-items: center; gap: 12px; }
    .alert-icon-box { font-size: 24px; }
    .alert-title-text { font-size: 14px; font-weight: 700; letter-spacing: -0.2px; }
    .alert-desc-text { font-size: 12px; color: var(--text-muted); margin-top: 1px; }

    /* Grid Layout */
    .grid {
      display: grid; grid-template-columns: repeat(auto-fit, minmax(330px, 1fr));
      gap: 18px; margin-bottom: 20px;
    }
    
    /* Cards */
    .card {
      background: var(--card-bg); border: 1px solid var(--card-border);
      border-radius: 16px; padding: 20px; backdrop-filter: blur(14px);
      box-shadow: 0 10px 25px -10px rgba(0,0,0,0.5); position: relative;
    }
    .card-header {
      display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;
    }
    .card-title {
      font-size: 13px; font-weight: 600; text-transform: uppercase;
      letter-spacing: 0.8px; color: var(--text-muted); display: flex; align-items: center; gap: 8px;
    }

    /* Metric Rows & Progress Bars */
    .metric-row { margin-bottom: 12px; }
    .metric-label-val { display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 5px; }
    .metric-val { font-family: 'JetBrains Mono', monospace; font-weight: 600; }
    .progress-bar-bg { height: 8px; background: rgba(255,255,255,0.07); border-radius: 6px; overflow: hidden; }
    .progress-bar-fill { height: 100%; border-radius: 6px; transition: width 0.4s ease; }
    .fill-cpu { background: linear-gradient(90deg, #10b981, #06b6d4); }
    .fill-ram { background: linear-gradient(90deg, #06b6d4, #8b5cf6); }
    .fill-disk { background: linear-gradient(90deg, #f59e0b, #ec4899); }

    /* Canvas Sparklines */
    .sparkline-box { margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--card-border); }
    .sparkline-header { display: flex; justify-content: space-between; font-size: 11px; color: var(--text-muted); margin-bottom: 5px; }
    .sparkline-canvas { width: 100%; height: 38px; display: block; border-radius: 6px; background: rgba(0,0,0,0.25); }

    /* Net stats pill */
    .net-box {
      display: grid; grid-template-columns: 1fr 1fr; gap: 10px;
      margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--card-border);
    }
    .net-pill {
      background: rgba(255,255,255,0.02); border-radius: 10px; padding: 8px; text-align: center;
      border: 1px solid rgba(255,255,255,0.05);
    }
    .net-pill-label { font-size: 10px; color: var(--text-muted); text-transform: uppercase; }
    .net-pill-val { font-family: 'JetBrains Mono', monospace; font-size: 15px; font-weight: 700; margin-top: 2px; }
    .rx-color { color: #34d399; }
    .tx-color { color: #fbbf24; }

    /* Temp Badge */
    .temp-badge {
      display: inline-flex; align-items: center; gap: 6px;
      font-family: 'JetBrains Mono', monospace; font-size: 13px; font-weight: 700;
      padding: 4px 10px; border-radius: 8px;
    }
    .temp-good { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16,185,129,0.3); }
    .temp-warn { background: rgba(245, 158, 11, 0.18); color: #fbbf24; border: 1px solid rgba(245,158,11,0.4); }
    .temp-crit { background: rgba(239, 68, 68, 0.22); color: #f87171; border: 1px solid rgba(239,68,68,0.5); }

    /* Station Stat Tiles */
    .station-tiles { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
    .station-tile {
      background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05);
      border-radius: 10px; padding: 12px;
    }
    .station-tile-lbl { font-size: 11px; color: var(--text-muted); }
    .station-tile-val { font-family: 'JetBrains Mono', monospace; font-size: 20px; font-weight: 700; margin-top: 3px; }
    .station-tile-unit { font-size: 12px; font-weight: 400; color: var(--text-muted); }

    /* Services List */
    .services-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 14px; }
    .service-item {
      display: flex; justify-content: space-between; align-items: center;
      background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05);
      padding: 8px 12px; border-radius: 8px;
    }
    .service-info { display: flex; flex-direction: column; gap: 1px; }
    .service-name { font-size: 13px; font-weight: 600; }
    .service-sub { font-size: 11px; color: var(--text-muted); }
    .service-badge { font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 5px; }
    .srv-ok { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16,185,129,0.3); }
    .srv-err { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239,68,68,0.3); }

    /* Top Processes Table (htop compact) */
    .proc-table { width: 100%; border-collapse: collapse; font-size: 11px; margin-top: 8px; font-family: 'JetBrains Mono', monospace; }
    .proc-table th { text-align: left; color: var(--text-muted); padding: 5px 8px; border-bottom: 1px solid var(--card-border); font-size: 10px; text-transform: uppercase; }
    .proc-table td { padding: 6px 8px; border-bottom: 1px solid rgba(255,255,255,0.03); }
    .proc-cpu-bar { width: 45px; height: 5px; background: rgba(255,255,255,0.08); border-radius: 3px; display: inline-block; vertical-align: middle; margin-left: 6px; overflow: hidden; }
    .proc-cpu-fill { height: 100%; background: #06b6d4; border-radius: 3px; }

    /* DevOps Command Deck */
    .cmd-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; }
    .btn-cmd {
      background: rgba(255,255,255,0.03); border: 1px solid var(--card-border);
      border-radius: 10px; padding: 12px 10px; color: var(--text); cursor: pointer;
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      gap: 6px; text-align: center; transition: all 0.2s; font-family: 'Outfit', sans-serif;
    }
    .btn-cmd:hover { background: rgba(255,255,255,0.08); border-color: var(--accent); transform: translateY(-2px); }
    .btn-cmd-icon { font-size: 20px; }
    .btn-cmd-title { font-size: 12px; font-weight: 600; }
    .btn-cmd-sub { font-size: 10px; color: var(--text-muted); }
    .cmd-status-box {
      margin-top: 12px; padding: 10px 14px; border-radius: 8px;
      background: rgba(0,0,0,0.3); border: 1px solid var(--card-border);
      font-size: 12px; font-family: 'JetBrains Mono', monospace;
      display: flex; justify-content: space-between; align-items: center;
    }

    /* Spotify Media Hub */
    .spotify-card {
      grid-column: 1 / -1;
      background: linear-gradient(135deg, rgba(18, 24, 39, 0.92), rgba(29, 185, 84, 0.12));
      border-color: rgba(29, 185, 84, 0.32);
    }
    .vol-slider-wrap {
      display: flex; align-items: center; gap: 10px; min-width: 160px;
    }
    input[type=range] {
      -webkit-appearance: none; width: 100%; height: 5px;
      border-radius: 5px; background: rgba(255,255,255,0.15); outline: none;
    }
    input[type=range]::-webkit-slider-thumb {
      -webkit-appearance: none; width: 14px; height: 14px;
      border-radius: 50%; background: #1db954; cursor: pointer; box-shadow: 0 0 6px rgba(29,185,84,0.6);
    }

    /* Live Terminal Drawer */
    .console-drawer {
      position: fixed; bottom: 0; left: 0; right: 0;
      background: rgba(8, 12, 22, 0.96); border-top: 1px solid rgba(255,255,255,0.12);
      backdrop-filter: blur(16px); z-index: 1000;
      transform: translateY(100%); transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
      box-shadow: 0 -10px 30px rgba(0,0,0,0.7); max-height: 45vh; display: flex; flex-direction: column;
    }
    .console-drawer.open { transform: translateY(0); }
    .console-header {
      padding: 10px 18px; display: flex; justify-content: space-between; align-items: center;
      border-bottom: 1px solid var(--card-border); background: rgba(0,0,0,0.3);
    }
    .console-title { font-family: 'JetBrains Mono', monospace; font-size: 12px; font-weight: 700; color: #34d399; display: flex; align-items: center; gap: 8px; }
    .console-body {
      padding: 12px 18px; overflow-y: auto; font-family: 'JetBrains Mono', monospace;
      font-size: 11px; line-height: 1.6; color: #cbd5e1;
    }
    .log-line { display: flex; gap: 10px; margin-bottom: 4px; word-break: break-all; }
    .log-ts { color: var(--text-muted); }
    .log-tag { font-weight: 700; padding: 0 4px; border-radius: 3px; font-size: 10px; }
    .tag-info { color: #38bdf8; }
    .tag-cmd { color: #a78bfa; }
    .tag-warn { color: #fbbf24; }
    .tag-alert { color: #f87171; }

    /* Footer */
    footer {
      display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;
      gap: 12px; font-size: 12px; color: var(--text-muted); padding-top: 16px;
      border-top: 1px solid var(--card-border);
    }
    .tag-desk {
      background: rgba(99, 102, 241, 0.15); color: #a5b4fc; padding: 4px 10px;
      border-radius: 8px; border: 1px solid rgba(99, 102, 241, 0.3); font-weight: 500;
    }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="logo-area">
        <div class="logo-icon">V</div>
        <div class="title">
          <h1>Sistema Vigil</h1>
          <p>NOC & Observabilidade &middot; Servidor Ubuntu &middot; Vigil Desk</p>
        </div>
      </div>
      <div class="header-actions">
        <button class="btn-action" onclick="toggleConsole()">📜 Console Logs</button>
        <button class="btn-action" id="btn-sound" onclick="toggleSound()">🔔 Alertas: On</button>
        <div class="badge-status">
          <span class="pulse-dot"></span>
          <span id="conn-status">VIGIL ATIVO AO VIVO</span>
        </div>
      </div>
    </header>

    <!-- Barra de Acesso Rápido ao Ecossistema -->
    <div class="ecosystem-bar">
      <a href="http://192.168.0.105:3000" target="_blank" class="eco-chip">
        <span class="eco-dot"></span> 🌾 Gaia Server (:3000)
      </a>
      <a href="http://192.168.0.105:3001" target="_blank" class="eco-chip">
        <span class="eco-dot"></span> 🌿 Central Agroclima (:3001)
      </a>
      <a href="http://192.168.0.105:9000" target="_blank" class="eco-chip">
        <span class="eco-dot"></span> 🐳 Portainer CE (:9000)
      </a>
      <a href="http://192.168.0.105:8080" target="_blank" class="eco-chip">
        <span class="eco-dot"></span> 🗄️ Adminer DB (:8080)
      </a>
      <a href="https://server1.taila7d06b.ts.net:10000" target="_blank" class="eco-chip">
        <span class="eco-dot" style="background:#06b6d4;"></span> 🔒 Túnel Tailscale HTTPS
      </a>
    </div>

    <!-- Banner Dinâmico de Alertas -->
    <div id="alert-banner" class="alert-banner alert-normal">
      <div class="alert-left">
        <div class="alert-icon-box" id="alert-icon">🛡️</div>
        <div>
          <div class="alert-title-text" id="alert-title">SISTEMA VIGIL OPERANDO NORMALMENTE</div>
          <div class="alert-desc-text" id="alert-desc">Infraestrutura estável, parâmetros térmicos e telemetria sob controle.</div>
        </div>
      </div>
      <div id="alert-stamp" style="font-family:'JetBrains Mono'; font-size:12px; color:var(--text-muted);">OK</div>
    </div>

    <div class="grid">
      <!-- Card 1: Servidor Ubuntu -->
      <div class="card">
        <div class="card-header">
          <div class="card-title">
            <svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>
            Servidor Ubuntu (192.168.0.105)
          </div>
          <div id="temp-badge" class="temp-badge temp-good">--.- &deg;C</div>
        </div>

        <div class="metric-row">
          <div class="metric-label-val">
            <span>Uso de CPU</span>
            <span class="metric-val" id="val-cpu">--%</span>
          </div>
          <div class="progress-bar-bg">
            <div id="bar-cpu" class="progress-bar-fill fill-cpu" style="width: 0%;"></div>
          </div>
        </div>

        <div class="sparkline-box">
          <div class="sparkline-header">
            <span>Histórico CPU (Últimos 30s)</span>
            <span id="lbl-cpu-avg">--</span>
          </div>
          <canvas id="canvas-cpu" class="sparkline-canvas" width="300" height="38"></canvas>
        </div>

        <div class="metric-row" style="margin-top: 12px;">
          <div class="metric-label-val">
            <span>Memória RAM</span>
            <span class="metric-val" id="val-ram">--%</span>
          </div>
          <div class="progress-bar-bg">
            <div id="bar-ram" class="progress-bar-fill fill-ram" style="width: 0%;"></div>
          </div>
        </div>

        <div class="metric-row">
          <div class="metric-label-val">
            <span>Armazenamento SSD</span>
            <span class="metric-val" id="val-disk">--%</span>
          </div>
          <div class="progress-bar-bg">
            <div id="bar-disk" class="progress-bar-fill fill-disk" style="width: 0%;"></div>
          </div>
        </div>

        <div class="net-box">
          <div class="net-pill">
            <div class="net-pill-label">&darr; Download (RX)</div>
            <div class="net-pill-val rx-color" id="val-rx">-- KB/s</div>
          </div>
          <div class="net-pill">
            <div class="net-pill-label">&uarr; Upload (TX)</div>
            <div class="net-pill-val tx-color" id="val-tx">-- KB/s</div>
          </div>
        </div>

        <div style="margin-top: 12px; font-size: 11px; color: var(--text-muted); display:flex; justify-content:space-between;">
          <span>Uptime: <strong id="val-uptime" style="color:var(--text);">--</strong></span>
          <span>Porta: <strong style="color:var(--text);">5000 / 3000</strong></span>
        </div>
      </div>

      <!-- Card 2: Estação de Campo G00001 & Curva Térmica -->
      <div class="card">
        <div class="card-header">
          <div class="card-title">
            <svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/><circle cx="12" cy="12" r="4"/></svg>
            Estação de Campo &middot; G00001
          </div>
          <div class="badge-status" id="station-badge" style="font-size: 11px; padding: 4px 10px;">ONLINE</div>
        </div>

        <div class="station-tiles">
          <div class="station-tile">
            <div class="station-tile-lbl">Temperatura</div>
            <div class="station-tile-val" style="color: #f3f4f6;" id="g-temp">--.-<span class="station-tile-unit">&deg;C</span></div>
          </div>
          <div class="station-tile">
            <div class="station-tile-lbl">Umidade Relativa</div>
            <div class="station-tile-val" style="color: #06b6d4;" id="g-umid">--.-<span class="station-tile-unit">%</span></div>
          </div>
          <div class="station-tile">
            <div class="station-tile-lbl">Déficit Pressão (VPD)</div>
            <div class="station-tile-val" style="color: #10b981;" id="g-vpd">-.--<span class="station-tile-unit">kPa</span></div>
          </div>
          <div class="station-tile">
            <div class="station-tile-lbl">Pressão Atmosférica</div>
            <div class="station-tile-val" style="color: #fbbf24;" id="g-press">---.-<span class="station-tile-unit">hPa</span></div>
          </div>
        </div>

        <div class="sparkline-box">
          <div class="sparkline-header">
            <span>Curva Térmica da CPU (°C últimos 30s)</span>
            <span id="lbl-temp-avg">--</span>
          </div>
          <canvas id="canvas-temp" class="sparkline-canvas" width="300" height="38"></canvas>
        </div>

        <div style="margin-top: 14px; padding: 10px; background: rgba(255,255,255,0.02); border-radius: 8px; font-size: 12px; display:flex; justify-content:space-between; align-items:center;">
          <span>Cultura: <strong id="g-cultura" style="color:#10b981;">Café Arábica</strong></span>
          <span style="font-size: 11px; color: var(--text-muted);" id="g-ago">Último envio: há -- seg</span>
        </div>
      </div>

      <!-- Card 3: Serviços Docker & Top 5 Processos -->
      <div class="card">
        <div class="card-header">
          <div class="card-title">
            <svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg>
            Serviços & Top Processos
          </div>
          <div class="badge-status" id="ping-badge" style="font-size: 11px; padding: 4px 10px;">Ping: ~2ms</div>
        </div>

        <div class="services-list" id="services-container">
          <!-- Renderizado dinamicamente -->
        </div>

        <div style="border-top: 1px solid var(--card-border); padding-top: 10px; margin-top: 10px;">
          <div style="font-size: 11px; color: var(--text-muted); font-weight: 600; text-transform: uppercase; margin-bottom: 4px;">Top Processos do Servidor (CPU/RAM)</div>
          <table class="proc-table">
            <thead>
              <tr><th>Processo</th><th>PID</th><th>% CPU</th><th>% RAM</th></tr>
            </thead>
            <tbody id="top-procs-body">
              <tr><td colspan="4" style="color:var(--text-muted)">Carregando processos...</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Card 4: DevOps Command Deck -->
      <div class="card" style="grid-column: 1 / -1;">
        <div class="card-header">
          <div class="card-title" style="color: #38bdf8;">
            <svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="4 17 10 11 4 5"></polyline><line x1="12" y1="19" x2="20" y2="19"></line></svg>
            DevOps Command Deck &middot; Ações Rápidas no Servidor
          </div>
          <div style="display:flex; align-items:center; gap:8px;">
            <label style="font-size: 11px; color: var(--text-muted); display:flex; align-items:center; gap:6px; cursor:pointer;">
              <input type="checkbox" id="chk-safety" checked style="accent-color:#10b981;">
              🛡️ Confirmação de Segurança
            </label>
          </div>
        </div>

        <div class="cmd-grid">
          <button class="btn-cmd" onclick="triggerDevops('restart_gaia', 'Reiniciar Gaia Server')">
            <span class="btn-cmd-icon">🔄</span>
            <span class="btn-cmd-title">Restart Gaia</span>
            <span class="btn-cmd-sub">Container :3000</span>
          </button>
          <button class="btn-cmd" onclick="triggerDevops('restart_agro', 'Reiniciar Agroclima')">
            <span class="btn-cmd-icon">🌾</span>
            <span class="btn-cmd-title">Restart Agro</span>
            <span class="btn-cmd-sub">Container :3001</span>
          </button>
          <button class="btn-cmd" onclick="triggerDevops('restart_mqtt', 'Reiniciar Mosquitto')">
            <span class="btn-cmd-icon">📡</span>
            <span class="btn-cmd-title">Restart MQTT</span>
            <span class="btn-cmd-sub">Broker :1883</span>
          </button>
          <button class="btn-cmd" onclick="triggerDevops('wol', 'Wake-on-LAN')">
            <span class="btn-cmd-icon">⚡</span>
            <span class="btn-cmd-title">Wake-on-LAN</span>
            <span class="btn-cmd-sub">Magic Packet LAN</span>
          </button>
          <button class="btn-cmd" onclick="triggerDevops('clear_cache', 'Limpar Buffers')">
            <span class="btn-cmd-icon">🧹</span>
            <span class="btn-cmd-title">Limpar Cache</span>
            <span class="btn-cmd-sub">Sync RAM</span>
          </button>
          <button class="btn-cmd" onclick="triggerDevops('test_tunnel', 'Testar Túnel HTTPS')">
            <span class="btn-cmd-icon">🌐</span>
            <span class="btn-cmd-title">Testar Túnel</span>
            <span class="btn-cmd-sub">Ping Tailscale</span>
          </button>
        </div>

        <div class="cmd-status-box" id="cmd-status-box">
          <span id="cmd-status-msg">Pronto para executar comandos do servidor</span>
          <span id="cmd-status-badge" style="color:var(--text-muted); font-size:11px;">STANDBY</span>
        </div>
      </div>

      <!-- Card 5: Spotify Media Hub com Slider de Volume -->
      <div class="card spotify-card">
        <div class="card-header" style="margin-bottom: 12px;">
          <div class="card-title" style="color: #1db954;">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.521 17.34c-.24.359-.66.48-1.021.24-2.82-1.74-6.36-2.101-10.561-1.141-.418.122-.779-.179-.899-.539-.12-.421.18-.78.54-.9 4.56-1.021 8.52-.6 11.64 1.32.42.18.479.659.301 1.02zm1.44-3.3c-.301.42-.841.6-1.262.3-3.239-1.98-8.159-2.58-11.939-1.38-.479.12-1.02-.12-1.14-.6-.12-.48.12-1.021.6-1.141C9.6 9.9 15 10.561 18.72 12.84c.361.181.54.78.241 1.2zm.12-3.36C15.24 8.4 8.82 8.16 5.16 9.301c-.6.179-1.2-.181-1.38-.721-.18-.601.18-1.2.72-1.381 4.26-1.26 11.28-1.02 15.721 1.621.539.3.719 1.02.419 1.56-.299.421-1.02.599-1.559.3z"/></svg>
            Spotify Media Hub &middot; Volume & Controles Físicos
          </div>
          <div class="badge-status" id="sp-badge" style="font-size: 11px; padding: 4px 10px; color: #1db954;">OCIOSO</div>
        </div>

        <div style="display: flex; align-items: center; gap: 18px; flex-wrap: wrap;">
          <img id="sp-art" src="/api/spotify/art.jpg" onerror="this.style.display='none'" style="width: 76px; height: 76px; border-radius: 12px; object-fit: cover; border: 1px solid rgba(255,255,255,0.12); display: none;" alt="Capa">
          <div style="flex: 1; min-width: 220px;">
            <div id="sp-track" style="font-size: 17px; font-weight: 700; color: #fff; margin-bottom: 3px;">Nenhuma música em reprodução</div>
            <div id="sp-artist" style="font-size: 12px; color: #9ca3af; margin-bottom: 8px;">Abra o Spotify no PC ou celular para sincronizar</div>
            
            <div class="progress-bar-bg" style="height: 6px; margin-bottom: 5px;">
              <div id="sp-bar" class="progress-bar-fill" style="width: 0%; background: linear-gradient(90deg, #1db954, #10b981);"></div>
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 11px; font-family: 'JetBrains Mono', monospace; color: #9ca3af;">
              <span id="sp-prog">00:00</span>
              <span id="sp-dur">00:00</span>
            </div>
          </div>

          <!-- Controles de Mídia & Slider de Volume -->
          <div style="display: flex; flex-direction: column; gap: 10px; align-items: flex-end;">
            <div style="display: flex; gap: 8px; align-items: center;">
              <button onclick="spotifyCmd('prev')" class="btn-action" style="padding: 9px 13px; font-size: 14px;">⏮</button>
              <button onclick="spotifyCmd('toggle')" id="sp-btn-play" class="btn-action" style="padding: 9px 18px; font-size: 14px; background: #1db954; color: #000; font-weight: 700; border: none;">▶ Play</button>
              <button onclick="spotifyCmd('next')" class="btn-action" style="padding: 9px 13px; font-size: 14px;">⏭</button>
            </div>
            <div class="vol-slider-wrap">
              <span id="vol-icon" style="font-size: 14px;">🔊</span>
              <input type="range" id="sp-vol-slider" min="0" max="100" value="75" oninput="changeVolume(this.value)">
              <span id="sp-vol-val" style="font-family:'JetBrains Mono'; font-size:12px; min-width:32px; text-align:right;">75%</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Rodapé -->
    <footer>
      <div>
        Hardware de Bancada: <span class="tag-desk">Vigil Desk (ESP32 - IP: 192.168.0.108)</span>
      </div>
      <div id="last-updated">
        Sincronizado via Fast-Path LAN (3ms)
      </div>
    </footer>
  </div>

  <!-- Drawer Retrátil de Console / Logs -->
  <div class="console-drawer" id="console-drawer">
    <div class="console-header">
      <div class="console-title">
        <span>📜 CONSOLE VIGIL // EVENTOS EM TEMPO REAL</span>
      </div>
      <div style="display:flex; gap:8px;">
        <button class="btn-action" onclick="fetchLogs()" style="padding:4px 10px; font-size:11px;">🔄 Atualizar</button>
        <button class="btn-action" onclick="toggleConsole()" style="padding:4px 10px; font-size:11px;">✕ Fechar</button>
      </div>
    </div>
    <div class="console-body" id="console-logs-container">
      <div class="log-line"><span class="log-ts">--:--:--</span><span class="log-tag tag-info">[INIT]</span> Carregando stream de eventos...</div>
    </div>
  </div>

  <script>
    let soundEnabled = true;
    let audioCtx = null;
    let lastAlertLevel = 'normal';
    let volDebounce = null;
    let isUserSliding = false;

    function toggleSound() {
      soundEnabled = !soundEnabled;
      const btn = document.getElementById('btn-sound');
      if (soundEnabled) {
        btn.innerText = '🔔 Alertas: On';
        btn.style.color = 'var(--text)';
        playChime(660, 880);
      } else {
        btn.innerText = '🔕 Alertas: Off';
        btn.style.color = 'var(--text-muted)';
      }
    }

    function toggleConsole() {
      const d = document.getElementById('console-drawer');
      d.classList.toggle('open');
      if (d.classList.contains('open')) fetchLogs();
    }

    function playChime(freq1, freq2) {
      if (!soundEnabled) return;
      try {
        if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        if (audioCtx.state === 'suspended') audioCtx.resume();
        const now = audioCtx.currentTime;
        const o1 = audioCtx.createOscillator();
        const o2 = audioCtx.createOscillator();
        const g = audioCtx.createGain();
        o1.type = 'sine'; o1.frequency.setValueAtTime(freq1, now);
        o2.type = 'sine'; o2.frequency.setValueAtTime(freq2, now + 0.12);
        g.gain.setValueAtTime(0.12, now);
        g.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
        o1.connect(g); o2.connect(g); g.connect(audioCtx.destination);
        o1.start(now); o1.stop(now + 0.12);
        o2.start(now + 0.12); o2.stop(now + 0.35);
      } catch (e) { console.error(e); }
    }

    function drawSparkline(canvasId, data, colorStroke, colorFill, minVal, maxVal) {
      const cvs = document.getElementById(canvasId);
      if (!cvs || !data || data.length < 2) return;
      const ctx = cvs.getContext('2d');
      const w = cvs.width;
      const h = cvs.height;
      ctx.clearRect(0, 0, w, h);
      const len = data.length;
      const step = w / (len - 1);
      ctx.beginPath();
      for (let i = 0; i < len; i++) {
        const val = data[i];
        const norm = (val - minVal) / Math.max((maxVal - minVal), 1);
        const y = h - Math.min(Math.max(norm * (h - 8) + 4, 4), h - 4);
        const x = i * step;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.strokeStyle = colorStroke; ctx.lineWidth = 2; ctx.stroke();
      ctx.lineTo(w, h); ctx.lineTo(0, h); ctx.closePath();
      const grad = ctx.createLinearGradient(0, 0, 0, h);
      grad.addColorStop(0, colorFill); grad.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = grad; ctx.fill();
    }

    async function spotifyCmd(act) {
      try {
        await fetch('/api/spotify/' + act, { method: 'POST' });
        setTimeout(updateDashboard, 350);
      } catch (e) { console.error(e); }
    }

    function changeVolume(val) {
      isUserSliding = true;
      document.getElementById('sp-vol-val').innerText = val + '%';
      const icon = document.getElementById('vol-icon');
      if (val == 0) icon.innerText = '🔇';
      else if (val < 40) icon.innerText = '🔈';
      else if (val < 75) icon.innerText = '🔉';
      else icon.innerText = '🔊';

      clearTimeout(volDebounce);
      volDebounce = setTimeout(async () => {
        try {
          await fetch('/api/spotify/volume?val=' + val, { method: 'POST' });
          isUserSliding = false;
        } catch(e) { isUserSliding = false; }
      }, 250);
    }

    async function triggerDevops(cmd, label) {
      const safety = document.getElementById('chk-safety').checked;
      if (safety) {
        if (!confirm(`Confirmar execução de: "${label}" no servidor?`)) return;
      }
      const box = document.getElementById('cmd-status-box');
      const msg = document.getElementById('cmd-status-msg');
      const badge = document.getElementById('cmd-status-badge');
      msg.innerText = `Executando: ${label}...`;
      badge.innerText = 'EXECUTANDO';
      badge.style.color = '#38bdf8';

      try {
        const t0 = performance.now();
        const r = await fetch('/api/cmd/' + cmd, { method: 'POST' });
        const data = await r.json();
        const ms = Math.round(performance.now() - t0);
        if (data.ok) {
          msg.innerText = `OK: ${data.message} (${ms}ms)`;
          badge.innerText = 'SUCESSO';
          badge.style.color = '#34d399';
          playChime(550, 750);
        } else {
          msg.innerText = `ERRO: ${data.message}`;
          badge.innerText = 'FALHA';
          badge.style.color = '#f87171';
        }
        fetchLogs();
      } catch(e) {
        msg.innerText = 'Falha de comunicação com o servidor';
        badge.innerText = 'ERRO HTTP';
        badge.style.color = '#f87171';
      }
    }

    async function fetchLogs() {
      try {
        const res = await fetch('/api/logs');
        if (!res.ok) return;
        const logs = await res.json();
        const container = document.getElementById('console-logs-container');
        container.innerHTML = logs.map(l => {
          let tagClass = 'tag-info';
          if (l.type === 'cmd') tagClass = 'tag-cmd';
          else if (l.type === 'warn') tagClass = 'tag-warn';
          else if (l.type === 'alert') tagClass = 'tag-alert';
          return `<div class="log-line"><span class="log-ts">${l.ts}</span><span class="log-tag ${tagClass}">[${l.type.toUpperCase()}]</span> <span>${l.msg}</span></div>`;
        }).join('');
        container.scrollTop = container.scrollHeight;
      } catch(e) {}
    }

    async function updateDashboard() {
      try {
        const res = await fetch('/api/status');
        if (!res.ok) throw new Error('Status ' + res.status);
        const data = await res.json();
        
        // Servidor
        const s = data.server || {};
        document.getElementById('val-cpu').innerText = s.cpu.toFixed(1) + '%';
        document.getElementById('bar-cpu').style.width = Math.min(100, Math.max(0, s.cpu)) + '%';

        document.getElementById('val-ram').innerText = s.ram.toFixed(1) + '%';
        document.getElementById('bar-ram').style.width = Math.min(100, Math.max(0, s.ram)) + '%';

        document.getElementById('val-disk').innerText = s.disk.toFixed(1) + '%';
        document.getElementById('bar-disk').style.width = Math.min(100, Math.max(0, s.disk)) + '%';

        document.getElementById('val-rx').innerText = (s.rx_kbps || 0).toFixed(1) + ' KB/s';
        document.getElementById('val-tx').innerText = (s.tx_kbps || 0).toFixed(1) + ' KB/s';

        // Temperatura CPU
        const temp = s.cpu_temp || 0;
        const tempEl = document.getElementById('temp-badge');
        tempEl.innerHTML = (temp > 0 ? temp.toFixed(1) : '--.-') + ' &deg;C';
        tempEl.className = 'temp-badge ' + (temp > 75 ? 'temp-crit' : (temp > 60 ? 'temp-warn' : 'temp-good'));

        // Uptime
        const up = s.uptime_sec || 0;
        const d = Math.floor(up / 86400);
        const h = Math.floor((up % 86400) / 3600);
        const m = Math.floor((up % 3600) / 60);
        document.getElementById('val-uptime').innerText = `${d}d ${h}h ${m}m`;

        // Alertas
        const level = s.alert_level || 'normal';
        const banner = document.getElementById('alert-banner');
        const alertTitle = document.getElementById('alert-title');
        const alertDesc = document.getElementById('alert-desc');
        const alertIcon = document.getElementById('alert-icon');
        const alertStamp = document.getElementById('alert-stamp');

        if (level === 'critical') {
          banner.className = 'alert-banner alert-critical';
          alertIcon.innerText = '🚨';
          alertTitle.innerText = 'ALERTA CRÍTICO DE SISTEMA';
          alertDesc.innerText = s.alert_msg || 'Parâmetros excederam o limite de segurança!';
          alertStamp.innerText = 'PERIGO';
          alertStamp.style.color = '#f87171';
          if (lastAlertLevel !== 'critical') playChime(880, 440);
        } else if (level === 'warning') {
          banner.className = 'alert-banner alert-warning';
          alertIcon.innerText = '⚠️';
          alertTitle.innerText = 'ATENÇÃO // AVISO DE MONITORAMENTO';
          alertDesc.innerText = s.alert_msg || 'Carga ou temperatura acima da média';
          alertStamp.innerText = 'AVISO';
          alertStamp.style.color = '#fbbf24';
          if (lastAlertLevel === 'normal') playChime(660, 550);
        } else {
          banner.className = 'alert-banner alert-normal';
          alertIcon.innerText = '🛡️';
          alertTitle.innerText = 'SISTEMA VIGIL OPERANDO NORMALMENTE';
          alertDesc.innerText = 'Infraestrutura estável, parâmetros térmicos e telemetria sob controle.';
          alertStamp.innerText = 'OK';
          alertStamp.style.color = '#34d399';
        }
        lastAlertLevel = level;

        // Sparklines
        const h_cpu = (data.history && data.history.cpu) ? data.history.cpu : [];
        const h_temp = (data.history && data.history.temp) ? data.history.temp : [];
        if (h_cpu.length > 0) {
          const avgCpu = (h_cpu.reduce((a, b) => a + b, 0) / h_cpu.length).toFixed(1);
          document.getElementById('lbl-cpu-avg').innerText = `Média: ${avgCpu}%`;
          drawSparkline('canvas-cpu', h_cpu, '#10b981', 'rgba(16, 185, 129, 0.25)', 0, 100);
        }
        if (h_temp.length > 0) {
          const avgTemp = (h_temp.reduce((a, b) => a + b, 0) / h_temp.length).toFixed(1);
          document.getElementById('lbl-temp-avg').innerText = `Média: ${avgTemp}°C`;
          drawSparkline('canvas-temp', h_temp, '#f59e0b', 'rgba(245, 158, 11, 0.25)', 30, 85);
        }

        // Estação de Campo
        const st = data.station || data.gaia || {};
        document.getElementById('g-temp').innerHTML = (st.temp > 0 ? st.temp.toFixed(1) : '--.-') + '<span class="station-tile-unit">&deg;C</span>';
        document.getElementById('g-umid').innerHTML = (st.umid > 0 ? st.umid.toFixed(1) : '--.-') + '<span class="station-tile-unit">%</span>';
        document.getElementById('g-vpd').innerHTML = (st.vpd > 0 ? st.vpd.toFixed(3) : '-.---') + '<span class="station-tile-unit">kPa</span>';
        document.getElementById('g-press').innerHTML = (st.pressao > 0 ? st.pressao.toFixed(1) : '---.-') + '<span class="station-tile-unit">hPa</span>';
        if (st.cultura) document.getElementById('g-cultura').innerText = st.cultura;
        document.getElementById('g-ago').innerText = `Último envio: há ${st.sec_ago !== undefined ? st.sec_ago : '--'} seg`;
        
        const stBadge = document.getElementById('station-badge');
        if (st.status === 'ONLINE') {
          stBadge.className = 'badge-status';
          stBadge.innerText = 'ONLINE';
          stBadge.style.color = '#34d399';
        } else {
          stBadge.className = 'badge-status';
          stBadge.innerText = 'OFFLINE';
          stBadge.style.color = '#f87171';
        }

        // Serviços Docker
        if (data.services && Array.isArray(data.services)) {
          const srvBox = document.getElementById('services-container');
          srvBox.innerHTML = data.services.map(srv => `
            <div class="service-item">
              <div class="service-info">
                <span class="service-name">${srv.name}</span>
                <span class="service-sub">Porta ${srv.port} &middot; ${srv.type}</span>
              </div>
              <span class="service-badge ${srv.status ? 'srv-ok' : 'srv-err'}">${srv.status ? 'ATIVO' : 'DOWN'}</span>
            </div>
          `).join('');
        }

        // Ping badge
        if (data.ping_ms) {
          document.getElementById('ping-badge').innerText = `Ping: ~${data.ping_ms}ms`;
        }

        // Top Processos
        if (data.top_processes && Array.isArray(data.top_processes)) {
          const tbody = document.getElementById('top-procs-body');
          tbody.innerHTML = data.top_processes.map(p => `
            <tr>
              <td><strong>${p.name}</strong></td>
              <td>${p.pid}</td>
              <td>
                ${p.cpu.toFixed(1)}%
                <span class="proc-cpu-bar"><span class="proc-cpu-fill" style="width:${Math.min(100, p.cpu)}%"></span></span>
              </td>
              <td>${p.mem.toFixed(1)}%</td>
            </tr>
          `).join('');
        }

        // Spotify Card
        const sp = data.spotify || {};
        const spArt = document.getElementById('sp-art');
        const spTrack = document.getElementById('sp-track');
        const spArtist = document.getElementById('sp-artist');
        const spBadge = document.getElementById('sp-badge');
        const spBar = document.getElementById('sp-bar');
        const spProg = document.getElementById('sp-prog');
        const spDur = document.getElementById('sp-dur');
        const spBtnPlay = document.getElementById('sp-btn-play');

        if (sp.active) {
          spTrack.innerText = sp.track || 'Reproduzindo';
          spArtist.innerText = (sp.artist || 'Artista') + (sp.album ? ' • ' + sp.album : '');
          spBadge.innerText = sp.is_playing ? 'TOCANDO' : 'PAUSADO';
          spBadge.style.color = sp.is_playing ? '#1db954' : '#fbbf24';
          spBtnPlay.innerText = sp.is_playing ? '⏸ Pause' : '▶ Play';

          const pct = sp.duration_ms > 0 ? (sp.progress_ms / sp.duration_ms) * 100 : 0;
          spBar.style.width = Math.min(100, Math.max(0, pct)) + '%';

          const curSec = Math.floor((sp.progress_ms || 0) / 1000);
          const durSec = Math.floor((sp.duration_ms || 0) / 1000);
          spProg.innerText = `${String(Math.floor(curSec/60)).padStart(2,'0')}:${String(curSec%60).padStart(2,'0')}`;
          spDur.innerText = `${String(Math.floor(durSec/60)).padStart(2,'0')}:${String(durSec%60).padStart(2,'0')}`;

          if (sp.art_id) {
            spArt.src = sp.art_url || '/api/spotify/art.jpg';
            spArt.style.display = 'block';
          }

          if (!isUserSliding && sp.volume !== undefined) {
            document.getElementById('sp-vol-slider').value = sp.volume;
            document.getElementById('sp-vol-val').innerText = sp.volume + '%';
            const icon = document.getElementById('vol-icon');
            if (sp.volume == 0) icon.innerText = '🔇';
            else if (sp.volume < 40) icon.innerText = '🔈';
            else if (sp.volume < 75) icon.innerText = '🔉';
            else icon.innerText = '🔊';
          }
        } else {
          spTrack.innerText = 'Nenhuma música em reprodução';
          spArtist.innerText = 'Abra o Spotify para acompanhar no Vigil Web e no Vigil Desk';
          spBadge.innerText = 'OCIOSO';
          spBadge.style.color = '#9ca3af';
          spBtnPlay.innerText = '▶ Play';
          spBar.style.width = '0%';
          spArt.style.display = 'none';
        }

        document.getElementById('conn-status').innerText = 'VIGIL ATIVO AO VIVO';
      } catch (err) {
        console.error(err);
        document.getElementById('conn-status').innerText = 'RECONECTANDO...';
      }
    }

    setInterval(updateDashboard, 1500);
    updateDashboard();
  </script>
</body>
</html>
"""

PWA_MANIFEST = """{
  "name": "Sistema Vigil",
  "short_name": "Vigil",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#0b0f19",
  "theme_color": "#0b0f19",
  "description": "NOC de Observabilidade e Controle DevOps",
  "icons": [
    {
      "src": "/api/spotify/art.jpg",
      "sizes": "80x80",
      "type": "image/jpeg"
    }
  ]
}"""

class MonitorHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # 1. Rota JSON API: /api/status
        if self.path in ['/api/status', '/status']:
            with history_lock:
                h_cpu = list(history_cpu)
                h_temp = list(history_temp)
                h_ram = list(history_ram)

            services, ping_ms = get_services_status()
            station = get_field_station_metrics()
            top_procs = get_top_processes(5)

            srvc_map = {
                "serverApiOk": any(s["port"] == 3000 and s["status"] for s in services),
                "agroclimaOk": any(s["port"] == 3001 and s["status"] for s in services),
                "postgresOk": any(s["port"] == 5432 and s["status"] for s in services),
                "mosquittoOk": any(s["port"] == 1883 and s["status"] for s in services),
                "pingMs": ping_ms
            }

            payload = {
                "server": {
                    "name": "Ubuntu Server1",
                    "status": "online",
                    "cpu": current_metrics["cpu"],
                    "cpu_temp": current_metrics["cpu_temp"],
                    "ram": current_metrics["ram"],
                    "disk": current_metrics["disk"],
                    "rx_kbps": current_metrics["rx_kbps"],
                    "tx_kbps": current_metrics["tx_kbps"],
                    "uptime_sec": current_metrics["uptime_sec"],
                    "alert_level": current_metrics["alert_level"],
                    "alert_msg": current_metrics["alert_msg"],
                    "alerts": current_metrics["alerts"]
                },
                "services": services,
                "services_status": srvc_map,
                "ping_ms": ping_ms,
                "top_processes": top_procs,
                "history": {
                    "cpu": h_cpu,
                    "temp": h_temp,
                    "ram": h_ram
                },
                "station": station,
                "gaia": station,
                "spotify": dict(spotify_state)
            }

            body = json.dumps(payload).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(body)

        # 1b. Rota de Logs do Sistema: /api/logs
        elif self.path in ['/api/logs', '/logs']:
            with logs_lock:
                logs_list = list(system_logs)
            body = json.dumps(logs_list).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(body)

        # 2. Rota Imagem Capa Spotify (80x80 Baseline JPEG)
        elif self.path.startswith('/api/spotify/art.jpg'):
            if spotify_art_bytes:
                self.send_response(200)
                self.send_header('Content-Type', 'image/jpeg')
                self.send_header('Content-Length', str(len(spotify_art_bytes)))
                self.send_header('Cache-Control', 'public, max-age=300')
                self.end_headers()
                self.wfile.write(spotify_art_bytes)
            else:
                self.send_response(404)
                self.end_headers()

        # 3. Rotas de Controle Spotify (GET ou POST, incluindo volume?val=XX)
        elif self.path.startswith('/api/spotify/'):
            parsed = urllib.parse.urlparse(self.path)
            act = parsed.path.split('/api/spotify/')[-1].strip('/')
            if act == "volume":
                qs = urllib.parse.parse_qs(parsed.query)
                val = qs.get("val", ["75"])[0]
                act = f"volume:{val}"
            ok = spotify_command(act)
            body = json.dumps({"ok": ok, "action": act}).encode('utf-8')
            self.send_response(200 if ok else 400)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(body)

        # 3b. Rotas do Vigil Command Deck (/api/cmd/<comando>)
        elif self.path.startswith('/api/cmd/'):
            cmd_name = self.path.split('/api/cmd/')[-1].split('?')[0].strip('/')
            ok, msg = execute_devops_command(cmd_name)
            body = json.dumps({"ok": ok, "command": cmd_name, "message": msg}).encode('utf-8')
            self.send_response(200 if ok else 400)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(body)

        # 3c. PWA Manifest: /manifest.json
        elif self.path == '/manifest.json':
            body = PWA_MANIFEST.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/manifest+json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        # 4. Rota Dashboard Web HTML: / ou /dashboard
        elif self.path in ['/', '/dashboard', '/index.html']:
            body = HTML_DASHBOARD.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        return self.do_GET()

    def log_message(self, format, *args):
        return

if __name__ == '__main__':
    if PSUTIL_AVAILABLE:
        psutil.cpu_percent(interval=None)
    t = threading.Thread(target=background_sampler, daemon=True)
    t.start()
    t_sp = threading.Thread(target=spotify_sampler, daemon=True)
    t_sp.start()

    server_address = ('0.0.0.0', 5000)
    httpd = ThreadingHTTPServer(server_address, MonitorHandler)
    httpd.serve_forever()
