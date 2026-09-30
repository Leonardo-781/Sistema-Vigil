import subprocess
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
SISTEMA VIGIL - VIGIL AGENT & WEB DASHBOARD
==============================================================================
Observabilidade de Servidores, Monitoramento Térmico e Telemetria de Campo
==============================================================================
"""

import time
import os
import json
import socket
import collections
import threading
import urllib.request
import psutil
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
import base64
import urllib.parse
import io
try:
    from PIL import Image
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

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
        req = urllib.request.Request(img_url, headers={"User-Agent": "VigilAgent/2.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read()
        if PIL_AVAILABLE:
            im = Image.open(io.BytesIO(raw)).convert("RGB")
            im = im.resize((80, 80), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            # Baseline JPEG (progressive=False) obrigatorio para TJpg_Decoder no ESP32
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
            return resp.status in [200, 202, 204]
    except Exception:
        return False

def execute_devops_command(cmd_name):
    """Executa comandos rapidos do Vigil Command Deck com seguranca"""
    try:
        if cmd_name == "restart_gaia":
            subprocess.Popen(["sh", "-c", "docker restart $(docker ps -q --filter ancestor=gaia) 2>/dev/null || docker restart gaia 2>/dev/null || true"])
            return True, "Container Gaia reiniciado"
        elif cmd_name == "restart_agro":
            subprocess.Popen(["sh", "-c", "docker restart $(docker ps -q --filter name=agro) 2>/dev/null || true"])
            return True, "Container Agroclima reiniciado"
        elif cmd_name == "restart_mqtt":
            subprocess.Popen(["sh", "-c", "docker restart $(docker ps -q --filter name=mosquitto) 2>/dev/null || systemctl restart mosquitto 2>/dev/null || true"])
            return True, "Broker MQTT reiniciado"
        elif cmd_name == "wol":
            # Envia Magic Packet UDP broadcast na LAN
            mac_bytes = bytes.fromhex("FFFFFFFFFFFF")
            pkt = b"\xff" * 6 + mac_bytes * 16
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                s.sendto(pkt, ("255.255.255.255", 9))
            return True, "Magic Packet WOL enviado"
        elif cmd_name == "clear_cache":
            subprocess.Popen(["sh", "-c", "sync"])
            return True, "Buffers sincronizados"
        elif cmd_name == "test_tunnel":
            t0 = time.time()
            req = urllib.request.Request("https://server1.taila7d06b.ts.net:10000/api/status", headers={"User-Agent": "VigilDeck/2.0"})
            with urllib.request.urlopen(req, timeout=4) as r:
                ms = int((time.time() - t0) * 1000)
                return (r.status == 200), f"Tunel OK ({ms}ms)"
    except Exception as e:
        return False, str(e)[:32]
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

last_net = psutil.net_io_counters()
last_time = time.time()

# Cache de métricas atuais
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

def get_field_station_metrics():
    try:
        req = urllib.request.Request("http://127.0.0.1:3000/api/estacoes", headers={"User-Agent": "VigilAgent/2.0"})
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
    """Coleta métricas continuamente a cada 1s para alimentar os gráficos em tempo real"""
    global last_net, last_time, current_metrics
    while True:
        try:
            now = time.time()
            dt = max(now - last_time, 0.5)
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

            with history_lock:
                history_cpu.append(cpu)
                history_temp.append(cpu_temp)
                history_ram.append(ram)

            # Classifica status de alerta
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
        except Exception as e:
            pass
        time.sleep(1.2)

HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Vigil // Monitor de Infraestrutura</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #0b0f19;
      --card-bg: rgba(18, 24, 39, 0.78);
      --card-border: rgba(255, 255, 255, 0.08);
      --primary: #10b981;
      --primary-glow: rgba(16, 185, 129, 0.25);
      --accent: #06b6d4;
      --warning: #f59e0b;
      --danger: #ef4444;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Outfit', -apple-system, sans-serif;
      background: radial-gradient(circle at 15% 15%, #131c31 0%, #0b0f19 65%);
      color: var(--text);
      min-height: 100vh;
      padding: 20px 16px 40px;
    }
    .container { max-width: 1140px; margin: 0 auto; }
    
    /* Header */
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
      flex-wrap: wrap;
      gap: 16px;
      border-bottom: 1px solid var(--card-border);
      padding-bottom: 16px;
    }
    .logo-area { display: flex; align-items: center; gap: 14px; }
    .logo-icon {
      width: 46px; height: 46px; border-radius: 12px;
      background: linear-gradient(135deg, #10b981, #06b6d4);
      display: flex; align-items: center; justify-content: center;
      font-weight: 800; font-size: 26px; color: #fff;
      box-shadow: 0 0 24px var(--primary-glow);
    }
    .title h1 { font-size: 24px; font-weight: 700; letter-spacing: -0.5px; }
    .title p { font-size: 13px; color: var(--text-muted); }
    
    .header-actions { display: flex; align-items: center; gap: 12px; }
    .btn-sound {
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid var(--card-border);
      color: var(--text);
      padding: 7px 14px;
      border-radius: 20px;
      font-size: 13px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.2s;
    }
    .btn-sound:hover { background: rgba(255, 255, 255, 0.12); }
    .badge-status {
      display: inline-flex; align-items: center; gap: 8px;
      padding: 7px 16px; border-radius: 30px; font-size: 13px; font-weight: 600;
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

    /* Alert Banner */
    .alert-banner {
      border-radius: 14px;
      padding: 14px 20px;
      margin-bottom: 22px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      transition: all 0.3s ease;
    }
    .alert-normal {
      background: rgba(16, 185, 129, 0.08);
      border: 1px solid rgba(16, 185, 129, 0.25);
    }
    .alert-warning {
      background: rgba(245, 158, 11, 0.12);
      border: 1px solid rgba(245, 158, 11, 0.4);
      animation: alertPulse 2s infinite;
    }
    .alert-critical {
      background: rgba(239, 68, 68, 0.18);
      border: 1px solid rgba(239, 68, 68, 0.6);
      box-shadow: 0 0 25px rgba(239, 68, 68, 0.3);
      animation: alertFlash 1.2s infinite;
    }
    @keyframes alertPulse {
      0% { border-color: rgba(245, 158, 11, 0.4); }
      50% { border-color: rgba(245, 158, 11, 0.8); }
      100% { border-color: rgba(245, 158, 11, 0.4); }
    }
    @keyframes alertFlash {
      0% { background: rgba(239, 68, 68, 0.18); }
      50% { background: rgba(239, 68, 68, 0.32); }
      100% { background: rgba(239, 68, 68, 0.18); }
    }
    .alert-left { display: flex; align-items: center; gap: 14px; }
    .alert-icon-box { font-size: 26px; }
    .alert-title-text { font-size: 15px; font-weight: 700; letter-spacing: -0.3px; }
    .alert-desc-text { font-size: 13px; color: var(--text-muted); margin-top: 2px; }

    /* Grid Layout */
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
      gap: 20px;
      margin-bottom: 24px;
    }
    
    /* Cards */
    .card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 22px;
      backdrop-filter: blur(12px);
      box-shadow: 0 10px 30px -10px rgba(0,0,0,0.5);
      position: relative;
    }
    .card-header {
      display: flex; justify-content: space-between; align-items: center;
      margin-bottom: 18px;
    }
    .card-title {
      font-size: 14px; font-weight: 600; text-transform: uppercase;
      letter-spacing: 0.8px; color: var(--text-muted);
      display: flex; align-items: center; gap: 8px;
    }

    /* Server Card Elements */
    .metric-row { margin-bottom: 14px; }
    .metric-label-val { display: flex; justify-content: space-between; font-size: 14px; margin-bottom: 6px; }
    .metric-val { font-family: 'JetBrains Mono', monospace; font-weight: 600; }
    .progress-bar-bg {
      height: 8px; background: rgba(255,255,255,0.08); border-radius: 6px; overflow: hidden;
    }
    .progress-bar-fill {
      height: 100%; border-radius: 6px; transition: width 0.5s ease;
    }
    .fill-cpu { background: linear-gradient(90deg, #10b981, #06b6d4); }
    .fill-ram { background: linear-gradient(90deg, #06b6d4, #8b5cf6); }
    .fill-disk { background: linear-gradient(90deg, #f59e0b, #ec4899); }

    /* Canvas Sparklines */
    .sparkline-box {
      margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--card-border);
    }
    .sparkline-header {
      display: flex; justify-content: space-between; font-size: 12px; color: var(--text-muted); margin-bottom: 6px;
    }
    .sparkline-canvas {
      width: 100%; height: 42px; display: block; border-radius: 6px;
      background: rgba(0,0,0,0.25);
    }

    /* Net stats pill */
    .net-box {
      display: grid; grid-template-columns: 1fr 1fr; gap: 12px;
      margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--card-border);
    }
    .net-pill {
      background: rgba(255,255,255,0.03); border-radius: 10px; padding: 10px; text-align: center;
      border: 1px solid rgba(255,255,255,0.05);
    }
    .net-pill-label { font-size: 11px; color: var(--text-muted); text-transform: uppercase; }
    .net-pill-val { font-family: 'JetBrains Mono', monospace; font-size: 16px; font-weight: 700; margin-top: 2px; }
    .rx-color { color: #34d399; }
    .tx-color { color: #fbbf24; }

    /* Temp Badge */
    .temp-badge {
      display: inline-flex; align-items: center; gap: 6px;
      font-family: 'JetBrains Mono', monospace; font-size: 14px; font-weight: 700;
      padding: 5px 12px; border-radius: 8px;
    }
    .temp-good { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16,185,129,0.3); }
    .temp-warn { background: rgba(245, 158, 11, 0.18); color: #fbbf24; border: 1px solid rgba(245,158,11,0.4); }
    .temp-crit { background: rgba(239, 68, 68, 0.22); color: #f87171; border: 1px solid rgba(239,68,68,0.5); }

    /* Station Stat Tiles */
    .station-tiles {
      display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px;
    }
    .station-tile {
      background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06);
      border-radius: 12px; padding: 14px;
    }
    .station-tile-lbl { font-size: 12px; color: var(--text-muted); }
    .station-tile-val {
      font-family: 'JetBrains Mono', monospace; font-size: 22px; font-weight: 700;
      margin-top: 4px;
    }
    .station-tile-unit { font-size: 13px; font-weight: 400; color: var(--text-muted); }

    /* Services List */
    .services-list { display: flex; flex-direction: column; gap: 10px; }
    .service-item {
      display: flex; justify-content: space-between; align-items: center;
      background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06);
      padding: 10px 14px; border-radius: 10px;
    }
    .service-info { display: flex; flex-direction: column; gap: 2px; }
    .service-name { font-size: 14px; font-weight: 600; }
    .service-sub { font-size: 11px; color: var(--text-muted); }
    .service-badge {
      font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 700;
      padding: 3px 8px; border-radius: 6px;
    }
    .srv-ok { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16,185,129,0.3); }
    .srv-err { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239,68,68,0.3); }

    /* Footer info */
    footer {
      display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;
      gap: 12px; font-size: 13px; color: var(--text-muted); padding-top: 14px;
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
          <p>Monitor de Infraestrutura &middot; Servidor Ubuntu &middot; Vigil Desk</p>
        </div>
      </div>
      <div class="header-actions">
        <button class="btn-sound" id="btn-sound" onclick="toggleSound()">🔔 Alertas Sonoros: Ligado</button>
        <div class="badge-status">
          <span class="pulse-dot"></span>
          <span id="conn-status">VIGIL ATIVO AO VIVO</span>
        </div>
      </div>
    </header>

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
      <!-- Card Servidor -->
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

        <!-- Sparkline CPU -->
        <div class="sparkline-box">
          <div class="sparkline-header">
            <span>Histórico de CPU (Últimos 30s)</span>
            <span id="lbl-cpu-avg">--</span>
          </div>
          <canvas id="canvas-cpu" class="sparkline-canvas" width="300" height="42"></canvas>
        </div>

        <div class="metric-row" style="margin-top: 14px;">
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
            <span>Armazenamento (Disco SSD)</span>
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

        <div style="margin-top: 14px; font-size: 12px; color: var(--text-muted); display:flex; justify-content:space-between;">
          <span>Uptime: <strong id="val-uptime" style="color:var(--text);">--</strong></span>
          <span>Porta: <strong style="color:var(--text);">5000 / 3000</strong></span>
        </div>
      </div>

      <!-- Card Estacao de Campo -->
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
            <div class="station-tile-lbl">Déficit Pressão Vapor (VPD)</div>
            <div class="station-tile-val" style="color: #10b981;" id="g-vpd">-.--<span class="station-tile-unit">kPa</span></div>
          </div>
          <div class="station-tile">
            <div class="station-tile-lbl">Pressão Atmosférica</div>
            <div class="station-tile-val" style="color: #fbbf24;" id="g-press">---.-<span class="station-tile-unit">hPa</span></div>
          </div>
        </div>

        <!-- Sparkline Térmica da CPU -->
        <div class="sparkline-box">
          <div class="sparkline-header">
            <span>Curva Térmica da CPU (°C últimos 30s)</span>
            <span id="lbl-temp-avg">--</span>
          </div>
          <canvas id="canvas-temp" class="sparkline-canvas" width="300" height="42"></canvas>
        </div>

        <div style="margin-top: 16px; padding: 12px; background: rgba(255,255,255,0.02); border-radius: 10px; font-size: 13px; display:flex; justify-content:space-between; align-items:center;">
          <span>Cultura: <strong id="g-cultura" style="color:#10b981;">Café Arábica</strong></span>
          <span style="font-size: 12px; color: var(--text-muted);" id="g-ago">Último envio: há -- seg</span>
        </div>
      </div>

      <!-- Card Servicos & Docker -->
      <div class="card">
        <div class="card-header">
          <div class="card-title">
            <svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg>
            Serviços & Contêineres
          </div>
          <div class="badge-status" id="ping-badge" style="font-size: 11px; padding: 4px 10px;">Ping: ~2ms</div>
        </div>

        <div class="services-list" id="services-container">
          <!-- Renderizado dinamicamente -->
          <div class="service-item">
            <div class="service-info">
              <span class="service-name">Gaia Server</span>
              <span class="service-sub">Porta 3000 &middot; Backend Principal</span>
            </div>
            <span class="service-badge srv-ok">ATIVO</span>
          </div>
        </div>

        <div style="margin-top: 16px; padding: 12px; background: rgba(255,255,255,0.02); border-radius: 10px; font-size: 12px; color: var(--text-muted);">
          Monitoramento de sockets TCP locais executado a cada ciclo.
        </div>
      </div>
      <!-- Card Spotify Now Playing -->
      <div class="card" style="grid-column: 1 / -1; background: linear-gradient(135deg, rgba(18, 24, 39, 0.9), rgba(29, 185, 84, 0.12)); border-color: rgba(29, 185, 84, 0.28);">
        <div class="card-header" style="margin-bottom: 12px;">
          <div class="card-title" style="color: #1db954;">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.521 17.34c-.24.359-.66.48-1.021.24-2.82-1.74-6.36-2.101-10.561-1.141-.418.122-.779-.179-.899-.539-.12-.421.18-.78.54-.9 4.56-1.021 8.52-.6 11.64 1.32.42.18.479.659.301 1.02zm1.44-3.3c-.301.42-.841.6-1.262.3-3.239-1.98-8.159-2.58-11.939-1.38-.479.12-1.02-.12-1.14-.6-.12-.48.12-1.021.6-1.141C9.6 9.9 15 10.561 18.72 12.84c.361.181.54.78.241 1.2zm.12-3.36C15.24 8.4 8.82 8.16 5.16 9.301c-.6.179-1.2-.181-1.38-.721-.18-.601.18-1.2.72-1.381 4.26-1.26 11.28-1.02 15.721 1.621.539.3.719 1.02.419 1.56-.299.421-1.02.599-1.559.3z"/></svg>
            Spotify &middot; Vigil Media Control
          </div>
          <div class="badge-status" id="sp-badge" style="font-size: 11px; padding: 4px 10px; color: #1db954;">OCIOSO</div>
        </div>
        <div style="display: flex; align-items: center; gap: 18px; flex-wrap: wrap;">
          <img id="sp-art" src="/api/spotify/art.jpg" onerror="this.style.display='none'" style="width: 76px; height: 76px; border-radius: 12px; object-fit: cover; border: 1px solid rgba(255,255,255,0.12); display: none;" alt="Capa">
          <div style="flex: 1; min-width: 200px;">
            <div id="sp-track" style="font-size: 18px; font-weight: 700; color: #fff; margin-bottom: 4px;">Nenhuma música em reprodução</div>
            <div id="sp-artist" style="font-size: 13px; color: #9ca3af; margin-bottom: 10px;">Abra o Spotify para acompanhar no Vigil Web e no Vigil Desk</div>
            <div class="progress-bar-bg" style="height: 6px; margin-bottom: 6px;">
              <div id="sp-bar" class="progress-bar-fill" style="width: 0%; background: linear-gradient(90deg, #1db954, #10b981);"></div>
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 11px; font-family: 'JetBrains Mono', monospace; color: #9ca3af;">
              <span id="sp-prog">00:00</span>
              <span id="sp-dur">00:00</span>
            </div>
          </div>
          <div style="display: flex; gap: 10px; align-items: center;">
            <button onclick="spotifyCmd('prev')" class="btn-sound" style="padding: 10px 14px; font-size: 15px;">⏮</button>
            <button onclick="spotifyCmd('toggle')" id="sp-btn-play" class="btn-sound" style="padding: 10px 18px; font-size: 15px; background: #1db954; color: #000; font-weight: 700; border: none;">▶ Play</button>
            <button onclick="spotifyCmd('next')" class="btn-sound" style="padding: 10px 14px; font-size: 15px;">⏭</button>
          </div>
        </div>
      </div>
    </div>

    <footer>
      <div>
        Hardware de Bancada: <span class="tag-desk">Vigil Desk (ESP32 - IP: 192.168.0.108)</span>
      </div>
      <div id="last-updated">
        Atualizado há poucos segundos
      </div>
    </footer>
  </div>

  <script>
    let soundEnabled = true;
    let audioCtx = null;
    let lastAlertLevel = 'normal';

    function toggleSound() {
      soundEnabled = !soundEnabled;
      const btn = document.getElementById('btn-sound');
      if (soundEnabled) {
        btn.innerText = '🔔 Alertas Sonoros: Ligado';
        btn.style.color = 'var(--text)';
        playChime(660, 880);
      } else {
        btn.innerText = '🔕 Alertas Sonoros: Mudo';
        btn.style.color = 'var(--text-muted)';
      }
    }

    function playChime(freq1, freq2) {
      if (!soundEnabled) return;
      try {
        if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        if (audioCtx.state === 'suspended') audioCtx.resume();
        
        const now = audioCtx.currentTime;
        const osc1 = audioCtx.createOscillator();
        const osc2 = audioCtx.createOscillator();
        const gain = audioCtx.createGain();

        osc1.type = 'sine';
        osc1.frequency.setValueAtTime(freq1, now);
        osc2.type = 'sine';
        osc2.frequency.setValueAtTime(freq2, now + 0.12);

        gain.gain.setValueAtTime(0.12, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);

        osc1.connect(gain);
        osc2.connect(gain);
        gain.connect(audioCtx.destination);

        osc1.start(now);
        osc1.stop(now + 0.12);
        osc2.start(now + 0.12);
        osc2.stop(now + 0.35);
      } catch (e) {
        console.error(e);
      }
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

      ctx.strokeStyle = colorStroke;
      ctx.lineWidth = 2;
      ctx.stroke();

      // Gradiente de preenchimento
      ctx.lineTo(w, h);
      ctx.lineTo(0, h);
      ctx.closePath();
      const grad = ctx.createLinearGradient(0, 0, 0, h);
      grad.addColorStop(0, colorFill);
      grad.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = grad;
      ctx.fill();
    }

    async function spotifyCmd(act) {
      try {
        await fetch('/api/spotify/' + act, { method: 'POST' });
        setTimeout(updateDashboard, 350);
      } catch (e) { console.error(e); }
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
          alertTitle.innerText = 'ATENÇÃO // ELEVAÇÃO DE CARGA/TEMPERATURA';
          alertDesc.innerText = s.alert_msg || 'Monitorando métricas anormais.';
          alertStamp.innerText = 'ATENÇÃO';
          alertStamp.style.color = '#fbbf24';
          if (lastAlertLevel === 'normal') playChime(587, 880);
        } else {
          banner.className = 'alert-banner alert-normal';
          alertIcon.innerText = '🛡️';
          alertTitle.innerText = 'SISTEMA VIGIL OPERANDO NORMALMENTE';
          alertDesc.innerText = 'Infraestrutura estável, parâmetros térmicos e telemetria sob controle.';
          alertStamp.innerText = 'SAUDÁVEL';
          alertStamp.style.color = '#34d399';
        }
        lastAlertLevel = level;

        // Sparklines
        const hist = data.history || {};
        if (hist.cpu && hist.cpu.length > 0) {
          drawSparkline('canvas-cpu', hist.cpu, '#06b6d4', 'rgba(6, 182, 212, 0.25)', 0, 100);
          const lastCpu = hist.cpu[hist.cpu.length - 1];
          document.getElementById('lbl-cpu-avg').innerText = 'Agora: ' + lastCpu.toFixed(1) + '%';
        }
        if (hist.temp && hist.temp.length > 0) {
          drawSparkline('canvas-temp', hist.temp, '#fbbf24', 'rgba(251, 191, 36, 0.22)', 30, 90);
          const lastT = hist.temp[hist.temp.length - 1];
          document.getElementById('lbl-temp-avg').innerText = 'Agora: ' + lastT.toFixed(1) + '°C';
        }

        // Estacao
        const g = data.station || data.gaia || {};
        document.getElementById('g-temp').innerHTML = (g.temp || 0).toFixed(1) + '<span class="station-tile-unit">&deg;C</span>';
        document.getElementById('g-umid').innerHTML = (g.umid || 0).toFixed(1) + '<span class="station-tile-unit">%</span>';
        document.getElementById('g-vpd').innerHTML = (g.vpd || 0).toFixed(2) + '<span class="station-tile-unit">kPa</span>';
        document.getElementById('g-press').innerHTML = (g.pressao || 0).toFixed(1) + '<span class="station-tile-unit">hPa</span>';
        document.getElementById('g-ago').innerText = 'Último envio: há ' + (g.sec_ago || 0) + ' seg';
        if (g.cultura) document.getElementById('g-cultura').innerText = g.cultura;

        const badge = document.getElementById('station-badge');
        badge.innerText = g.status || 'ONLINE';
        badge.style.color = (g.status === 'ONLINE') ? '#34d399' : '#f87171';

        // Servicos
        const services = data.services || [];
        if (services.length > 0) {
          let sHtml = '';
          services.forEach(srv => {
            const isOk = srv.status;
            sHtml += `
              <div class="service-item">
                <div class="service-info">
                  <span class="service-name">${srv.name}</span>
                  <span class="service-sub">Porta ${srv.port} &middot; ${srv.type}</span>
                </div>
                <span class="service-badge ${isOk ? 'srv-ok' : 'srv-err'}">${isOk ? 'ATIVO' : 'OFFLINE'}</span>
              </div>
            `;
          });
          document.getElementById('services-container').innerHTML = sHtml;
        }
        if (data.ping_ms) {
          document.getElementById('ping-badge').innerText = 'Ping LAN: ~' + data.ping_ms + 'ms';
        }

        // Spotify
        const sp = data.spotify || {};
        document.getElementById('sp-track').innerText = sp.track || 'Nenhuma música';
        document.getElementById('sp-artist').innerText = (sp.artist || 'Spotify Ocioso') + (sp.album ? ' · ' + sp.album : '');
        const spBadge = document.getElementById('sp-badge');
        const spPlayBtn = document.getElementById('sp-btn-play');
        if (sp.is_playing) {
          spBadge.innerText = '▶ TOCANDO AGORA';
          spBadge.style.color = '#1db954';
          spPlayBtn.innerText = '⏸ Pause';
        } else {
          spBadge.innerText = sp.active ? '⏸ PAUSADO' : 'OCIOSO';
          spBadge.style.color = '#9ca3af';
          spPlayBtn.innerText = '▶ Play';
        }
        const durMs = sp.duration_ms || 0;
        const progMs = sp.progress_ms || 0;
        const pct = durMs > 0 ? Math.min(100, (progMs / durMs) * 100) : 0;
        document.getElementById('sp-bar').style.width = pct.toFixed(1) + '%';
        const fmtTime = (ms) => {
          const s = Math.floor(ms / 1000);
          const m = Math.floor(s / 60);
          const sec = s % 60;
          return String(m).padStart(2, '0') + ':' + String(sec).padStart(2, '0');
        };
        document.getElementById('sp-prog').innerText = fmtTime(progMs);
        document.getElementById('sp-dur').innerText = fmtTime(durMs);
        const artEl = document.getElementById('sp-art');
        if (sp.art_id) {
          const newSrc = '/api/spotify/art.jpg?id=' + sp.art_id;
          if (!artEl.src.endsWith(newSrc)) artEl.src = newSrc;
          artEl.style.display = 'block';
        }

        document.getElementById('last-updated').innerText = 'Sincronizado: ' + new Date().toLocaleTimeString();
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

            # Mapeia servicos para facilitar no ESP32
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
    # Inicializa psutil e sampler thread
    psutil.cpu_percent(interval=None)
    t = threading.Thread(target=background_sampler, daemon=True)
    t.start()
    t_sp = threading.Thread(target=spotify_sampler, daemon=True)
    t_sp.start()

    server_address = ('0.0.0.0', 5000)
    httpd = ThreadingHTTPServer(server_address, MonitorHandler)
    httpd.serve_forever()
