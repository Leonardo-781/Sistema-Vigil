#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
SISTEMA VIGIL - VIGIL AGENT & WEB DASHBOARD
==============================================================================
Agente de monitoramento ultraleve para servidores Linux/Windows com dashboard
web em tempo real e fornecimento de métricas via API JSON para o Vigil Desk.
==============================================================================
"""

import time
import os
import json
import urllib.request
import psutil
from http.server import HTTPServer, BaseHTTPRequestHandler

# Configuração de portas e endpoints
PORT = int(os.getenv("VIGIL_PORT", 5000))
EXTERNAL_STATION_URL = os.getenv("STATION_API_URL", "http://127.0.0.1:3000/api/estacoes")

last_net = psutil.net_io_counters()
last_time = time.time()

def get_cpu_temp():
    """Lê a temperatura da CPU através do subsistema térmico do SO."""
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

def get_field_station_metrics():
    """Consulta dados de sensores externos ou estação de campo (opcional)."""
    try:
        req = urllib.request.Request(EXTERNAL_STATION_URL, headers={"User-Agent": "VigilAgent/1.0"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if isinstance(data, list) and len(data) > 0:
                st = data[0]
                return {
                    "station": st.get("cod_estacao", "G00001"),
                    "nome": st.get("nome", "Estacao G00001"),
                    "cultura": st.get("cultura", "Monitor de Campo"),
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
        "cultura": "Monitor de Campo",
        "status": "OFFLINE",
        "temp": 0.0,
        "umid": 0.0,
        "pressao": 0.0,
        "vpd": 0.0,
        "et0": 0.0,
        "itu": 0.0,
        "sec_ago": 9999
    }

HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Vigil // Monitor de Infraestrutura</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #0b0f19;
      --card-bg: rgba(18, 24, 39, 0.75);
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
      background: radial-gradient(circle at 15% 15%, #131c31 0%, #0b0f19 60%);
      color: var(--text);
      min-height: 100vh;
      padding: 24px 16px 40px;
    }
    .container { max-width: 1100px; margin: 0 auto; }
    
    header {
      display: flex; justify-content: space-between; align-items: center;
      margin-bottom: 24px; flex-wrap: wrap; gap: 16px;
      border-bottom: 1px solid var(--card-border); padding-bottom: 18px;
    }
    .logo-area { display: flex; align-items: center; gap: 14px; }
    .logo-icon {
      width: 44px; height: 44px; border-radius: 12px;
      background: linear-gradient(135deg, #10b981, #06b6d4);
      display: flex; align-items: center; justify-content: center;
      font-weight: 800; font-size: 24px; color: #fff;
      box-shadow: 0 0 22px var(--primary-glow);
      letter-spacing: -0.5px;
    }
    .title h1 { font-size: 22px; font-weight: 700; letter-spacing: -0.5px; }
    .title p { font-size: 13px; color: var(--text-muted); }
    .badge-status {
      display: inline-flex; align-items: center; gap: 8px;
      padding: 6px 14px; border-radius: 30px; font-size: 13px; font-weight: 600;
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

    .grid {
      display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 20px; margin-bottom: 24px;
    }
    
    .card {
      background: var(--card-bg); border: 1px solid var(--card-border);
      border-radius: 16px; padding: 22px; backdrop-filter: blur(12px);
      box-shadow: 0 10px 30px -10px rgba(0,0,0,0.5);
      transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .card:hover { border-color: rgba(255, 255, 255, 0.18); }
    .card-header {
      display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px;
    }
    .card-title {
      font-size: 15px; font-weight: 600; text-transform: uppercase;
      letter-spacing: 0.8px; color: var(--text-muted); display: flex; align-items: center; gap: 8px;
    }

    .metric-row { margin-bottom: 14px; }
    .metric-label-val { display: flex; justify-content: space-between; font-size: 14px; margin-bottom: 6px; }
    .metric-val { font-family: 'JetBrains Mono', monospace; font-weight: 600; }
    .progress-bar-bg {
      height: 8px; background: rgba(255,255,255,0.08); border-radius: 6px; overflow: hidden;
    }
    .progress-bar-fill {
      height: 100%; border-radius: 6px; transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .fill-cpu { background: linear-gradient(90deg, #10b981, #06b6d4); }
    .fill-ram { background: linear-gradient(90deg, #06b6d4, #8b5cf6); }
    .fill-disk { background: linear-gradient(90deg, #f59e0b, #ec4899); }

    .net-box {
      display: grid; grid-template-columns: 1fr 1fr; gap: 12px;
      margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--card-border);
    }
    .net-pill {
      background: rgba(255,255,255,0.03); border-radius: 10px; padding: 10px; text-align: center;
      border: 1px solid rgba(255,255,255,0.05);
    }
    .net-pill-label { font-size: 11px; color: var(--text-muted); text-transform: uppercase; }
    .net-pill-val { font-family: 'JetBrains Mono', monospace; font-size: 16px; font-weight: 700; margin-top: 2px; }
    .rx-color { color: #34d399; }
    .tx-color { color: #fbbf24; }

    .temp-badge {
      display: inline-flex; align-items: center; gap: 6px;
      font-family: 'JetBrains Mono', monospace; font-size: 14px; font-weight: 700;
      padding: 4px 10px; border-radius: 8px;
    }
    .temp-good { background: rgba(16, 185, 129, 0.15); color: #34d399; }
    .temp-warn { background: rgba(245, 158, 11, 0.15); color: #fbbf24; }
    .temp-crit { background: rgba(239, 68, 68, 0.15); color: #f87171; }

    .station-tiles { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
    .station-tile {
      background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06);
      border-radius: 12px; padding: 14px;
    }
    .station-tile-lbl { font-size: 12px; color: var(--text-muted); }
    .station-tile-val {
      font-family: 'JetBrains Mono', monospace; font-size: 22px; font-weight: 700; margin-top: 4px;
    }
    .station-tile-unit { font-size: 13px; font-weight: 400; color: var(--text-muted); }

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
          <p>Monitor de Infraestrutura &middot; Servidor &middot; Vigil Desk</p>
        </div>
      </div>
      <div>
        <div class="badge-status">
          <span class="pulse-dot"></span>
          <span id="conn-status">VIGIL ATIVO AO VIVO</span>
        </div>
      </div>
    </header>

    <div class="grid">
      <!-- Card Servidor -->
      <div class="card">
        <div class="card-header">
          <div class="card-title">
            <svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>
            Servidor Host
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

        <div class="metric-row">
          <div class="metric-label-val">
            <span>Mem&oacute;ria RAM</span>
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
          <span>Porta: <strong style="color:var(--text);">5000</strong></span>
        </div>
      </div>

      <!-- Card Estacao de Campo / Sensores Externos -->
      <div class="card">
        <div class="card-header">
          <div class="card-title">
            <svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/><circle cx="12" cy="12" r="4"/></svg>
            Monitor de Campo &middot; G00001
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
            <div class="station-tile-lbl">D&eacute;ficit Press&atilde;o Vapor (VPD)</div>
            <div class="station-tile-val" style="color: #10b981;" id="g-vpd">-.--<span class="station-tile-unit">kPa</span></div>
          </div>
          <div class="station-tile">
            <div class="station-tile-lbl">Press&atilde;o Atmosf&eacute;rica</div>
            <div class="station-tile-val" style="color: #fbbf24;" id="g-press">---.-<span class="station-tile-unit">hPa</span></div>
          </div>
        </div>

        <div style="margin-top: 16px; padding: 12px; background: rgba(255,255,255,0.02); border-radius: 10px; font-size: 13px; display:flex; justify-content:space-between; align-items:center;">
          <span>Origem: <strong id="g-cultura" style="color:#10b981;">Telemetria Externa</strong></span>
          <span style="font-size: 12px; color: var(--text-muted);" id="g-ago">&Uacute;ltimo envio: h&aacute; -- seg</span>
        </div>
      </div>
    </div>

    <footer>
      <div>
        Hardware de Bancada: <span class="tag-desk">Vigil Desk (ESP32)</span>
      </div>
      <div id="last-updated">
        Atualizado h&aacute; poucos segundos
      </div>
    </footer>
  </div>

  <script>
    async function updateDashboard() {
      try {
        const res = await fetch('/api/status');
        if (!res.ok) throw new Error('Status ' + res.status);
        const data = await res.json();
        
        const s = data.server || {};
        document.getElementById('val-cpu').innerText = s.cpu.toFixed(1) + '%';
        document.getElementById('bar-cpu').style.width = Math.min(100, Math.max(0, s.cpu)) + '%';

        document.getElementById('val-ram').innerText = s.ram.toFixed(1) + '%';
        document.getElementById('bar-ram').style.width = Math.min(100, Math.max(0, s.ram)) + '%';

        document.getElementById('val-disk').innerText = s.disk.toFixed(1) + '%';
        document.getElementById('bar-disk').style.width = Math.min(100, Math.max(0, s.disk)) + '%';

        document.getElementById('val-rx').innerText = (s.rx_kbps || 0).toFixed(1) + ' KB/s';
        document.getElementById('val-tx').innerText = (s.tx_kbps || 0).toFixed(1) + ' KB/s';

        const temp = s.cpu_temp || 0;
        const tempEl = document.getElementById('temp-badge');
        tempEl.innerHTML = (temp > 0 ? temp.toFixed(1) : '--.-') + ' &deg;C';
        tempEl.className = 'temp-badge ' + (temp > 75 ? 'temp-crit' : (temp > 60 ? 'temp-warn' : 'temp-good'));

        const up = s.uptime_sec || 0;
        const d = Math.floor(up / 86400);
        const h = Math.floor((up % 86400) / 3600);
        const m = Math.floor((up % 3600) / 60);
        document.getElementById('val-uptime').innerText = `${d}d ${h}h ${m}m`;

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
        global last_net, last_time
        
        if self.path in ['/api/status', '/status']:
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

            station = get_field_station_metrics()

            payload = {
                "server": {
                    "name": "Servidor Principal",
                    "status": "online",
                    "cpu": cpu,
                    "cpu_temp": cpu_temp,
                    "ram": ram,
                    "disk": disk,
                    "rx_kbps": rx_kbps,
                    "tx_kbps": tx_kbps,
                    "uptime_sec": uptime
                },
                "station": station
            }

            body = json.dumps(payload).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(body)

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

    def log_message(self, format, *args):
        return

if __name__ == '__main__':
    psutil.cpu_percent(interval=None)
    server_address = ('0.0.0.0', PORT)
    httpd = HTTPServer(server_address, MonitorHandler)
    print(f"Sistema Vigil - Agente ativo na porta {PORT}")
    httpd.serve_forever()
