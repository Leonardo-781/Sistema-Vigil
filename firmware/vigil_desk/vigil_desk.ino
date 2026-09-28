/*
 * ============================================================================
 * SISTEMA VIGIL - VIGIL DESK
 * ============================================================================
 * Placa Alvo: ESP32 + TFT ILI9341 2.8" + EC11 Encoder
 * Modos: Normal (Wi-Fi Station) + Modo AP com Scanner de Redes & Suporte HTTPS
 * ============================================================================
 */

#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <Preferences.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>
#include <vector>
#include <time.h>
#include "Config.h"
#include "DisplayUI.h"

// Instâncias Globais
DisplayUI displayUI;
Preferences preferences;
WebServer apServer(80);

ServerMetrics serverMetrics;
FieldStationMetrics stationMetrics;
ServicesMetrics servicesMetrics;

// URLs Padrão
#define CLOUDFLARE_URL_PRESET "https://SEU_TUNEL.trycloudflare.com/api/status"
#define LOCAL_URL_PRESET      "http://IP_DO_SEU_SERVIDOR:5000/api/status"

// Configurações Dinâmicas da NVS
String wifiSSID = DEFAULT_WIFI_SSID;
String wifiPASS = DEFAULT_WIFI_PASS;
String serverURL = DEFAULT_SERVER_URL;

// Modo de Operação
bool isAPMode = false;

// Controle do Encoder EC11
volatile int encoderPos = 0;
volatile unsigned long lastEncoderInterrupt = 0;
int lastEncoderPos = 0;
unsigned long lastButtonPress = 0;

// Temporizadores
unsigned long lastHttpFetch = 0;
unsigned long lastClockRender = 0;

// Interrupção de descida (FALLING) no pino CLK (GPIO 25)
void IRAM_ATTR handleEncoderInterrupt() {
  unsigned long now = millis();
  if (now - lastEncoderInterrupt > 40) { // Debounce de software
    if (digitalRead(ENCODER_DT) == HIGH) {
      encoderPos++;
    } else {
      encoderPos--;
    }
    lastEncoderInterrupt = now;
  }
}

// ----------------------------------------------------------------------------
// PORTAL WEB DO MODO AP COM SCANNER DE REDES WI-FI E PRESETS DE SERVIDOR
// ----------------------------------------------------------------------------
void handleAPRoot() {
  // Realiza varredura de redes próximas
  int n = WiFi.scanNetworks(false, false, false, 300);

  String html = "<!DOCTYPE html><html lang='pt-BR'><head><meta charset='UTF-8'>";
  html += "<meta name='viewport' content='width=device-width,initial-scale=1.0'>";
  html += "<title>Sistema Vigil - Configuração</title><style>";
  html += ":root{--bg:#0b0f19;--card:#131c31;--border:#1e293b;--primary:#10b981;--text:#f8fafc;--muted:#94a3b8;}";
  html += "* {box-sizing:border-box;margin:0;padding:0;}";
  html += "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--text);padding:16px;}";
  html += ".card{max-width:420px;margin:10px auto;background:var(--card);border:1px solid var(--border);border-radius:18px;padding:24px;box-shadow:0 12px 30px rgba(0,0,0,0.6);}";
  html += ".logo{display:flex;align-items:center;gap:12px;margin-bottom:18px;}";
  html += ".logo-icon{width:38px;height:38px;border-radius:10px;background:linear-gradient(135deg,#10b981,#06b6d4);display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:20px;color:#fff;}";
  html += "h2{font-size:20px;color:var(--text);font-weight:700;}";
  html += "p.subtitle{font-size:13px;color:var(--muted);line-height:1.4;margin-bottom:20px;}";
  html += ".section-title{font-size:12px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:0.8px;margin:18px 0 8px;}";
  html += "label{display:block;margin:10px 0 5px;font-size:13px;font-weight:600;}";
  html += "input,select{width:100%;box-sizing:border-box;padding:12px 14px;border-radius:10px;border:1px solid #334155;background:#0b1120;color:var(--text);font-size:14px;outline:none;transition:border-color 0.2s;}";
  html += "input:focus,select:focus{border-color:var(--primary);}";
  html += ".btn-rescan{display:inline-flex;align-items:center;gap:6px;background:#1e293b;color:#38bdf8;padding:8px 12px;border-radius:8px;border:1px solid #334155;font-size:12px;font-weight:600;text-decoration:none;margin-bottom:10px;cursor:pointer;}";
  html += ".btn-rescan:hover{background:#334155;}";
  html += ".presets{display:flex;gap:8px;margin:8px 0 12px;}";
  html += ".btn-preset{flex:1;background:#1e293b;border:1px solid #334155;color:#e2e8f0;padding:8px;border-radius:8px;font-size:11px;font-weight:600;cursor:pointer;text-align:center;}";
  html += ".btn-preset:hover{background:#334155;border-color:#64748b;}";
  html += ".btn-submit{width:100%;padding:14px;border-radius:10px;border:none;background:linear-gradient(135deg,#10b981,#059669);color:#fff;font-size:15px;font-weight:700;cursor:pointer;margin-top:22px;box-shadow:0 4px 14px rgba(16,185,129,0.3);}";
  html += ".btn-submit:hover{opacity:0.95;}";
  html += ".footer-note{text-align:center;font-size:12px;color:var(--muted);margin-top:16px;}";
  html += "</style></head><body><div class='card'>";

  html += "<div class='logo'><div class='logo-icon'>V</div><div><h2>Sistema Vigil</h2><div style='font-size:12px;color:#34d399;'>Painel de Configuração Wi-Fi</div></div></div>";
  html += "<p class='subtitle'>Selecione uma rede detectada ao redor ou digite as credenciais para conectar o Vigil Desk.</p>";

  html += "<form method='POST' action='/salvar'>";

  html += "<div class='section-title'>1. Rede Wi-Fi (2.4 GHz)</div>";
  html += "<div style='display:flex;justify-content:space-between;align-items:center;'>";
  html += "<label style='margin:0;'>Redes Encontradas:</label>";
  html += "<a href='/' class='btn-rescan'>🔄 Atualizar Lista</a>";
  html += "</div>";

  html += "<select id='wifi_list' onchange='pickSSID(this)'>";
  if (n <= 0) {
    html += "<option value=''>Nenhuma rede encontrada (ou escaneando...)</option>";
  } else {
    html += "<option value=''>-- Selecione a rede desejada (" + String(n) + " encontradas) --</option>";
    
    // Lista redes sem duplicadas
    std::vector<String> seen;
    for (int i = 0; i < n; i++) {
      String ssidFound = WiFi.SSID(i);
      ssidFound.trim();
      if (ssidFound.length() == 0) continue;

      bool exists = false;
      for (const auto& s : seen) {
        if (s == ssidFound) { exists = true; break; }
      }
      if (exists) continue;
      seen.push_back(ssidFound);

      int rssi = WiFi.RSSI(i);
      String qual = (rssi > -60) ? "🟢 Excelente" : ((rssi > -75) ? "🟡 Bom" : "🟠 Fraco");
      String enc = (WiFi.encryptionType(i) == WIFI_AUTH_OPEN) ? "🔓 Aberta" : "🔒 Protegida";

      html += "<option value='" + ssidFound + "'>" + ssidFound + " (" + qual + " · " + enc + ")</option>";
    }
  }
  html += "<option value='__manual__'>➕ Digitar outra rede manualmente...</option>";
  html += "</select>";

  html += "<label style='margin-top:12px;'>Nome da Rede (SSID):</label>";
  html += "<input type='text' id='ssid_input' name='ssid' value='" + wifiSSID + "' placeholder='Nome do Wi-Fi' required>";

  html += "<label>Senha do Wi-Fi:</label>";
  html += "<input type='password' id='pass_input' name='pass' value='" + wifiPASS + "' placeholder='Senha (deixe em branco se for aberta)'>";
  html += "<div style='margin-top:4px;'><label style='font-size:12px;font-weight:normal;color:var(--muted);cursor:pointer;'><input type='checkbox' style='width:auto;margin-right:6px;' onclick='togglePass()'>Mostrar senha</label></div>";

  html += "<div class='section-title'>2. Endpoint do Servidor Vigil</div>";
  html += "<div class='presets'>";
  html += "<button type='button' class='btn-preset' onclick='setPreset(\"" + String(LOCAL_URL_PRESET) + "\")'>🏠 Rede Local (Casa)</button>";
  html += "<button type='button' class='btn-preset' onclick='setPreset(\"" + String(CLOUDFLARE_URL_PRESET) + "\")'>☁️ Remoto (Cloudflare)</button>";
  html += "</div>";

  html += "<label>URL da API (HTTP ou HTTPS):</label>";
  html += "<input type='text' id='url_input' name='url' value='" + serverURL + "' placeholder='https://.../api/status' required>";

  html += "<button type='submit' class='btn-submit'>💾 Salvar e Conectar</button>";
  html += "</form>";

  html += "<div class='footer-note'>Após salvar, o ESP32 reiniciará e tentará se conectar imediatamente.</div>";
  html += "</div>";

  html += "<script>";
  html += "function pickSSID(el){";
  html += "  if(el.value === '__manual__'){ document.getElementById('ssid_input').value = ''; document.getElementById('ssid_input').focus(); }";
  html += "  else if(el.value){ document.getElementById('ssid_input').value = el.value; document.getElementById('pass_input').focus(); }";
  html += "}";
  html += "function togglePass(){";
  html += "  var p = document.getElementById('pass_input');";
  html += "  p.type = (p.type === 'password') ? 'text' : 'password';";
  html += "}";
  html += "function setPreset(url){";
  html += "  document.getElementById('url_input').value = url;";
  html += "}";
  html += "</script></body></html>";

  apServer.send(200, "text/html", html);
}

void handleAPSave() {
  String novoSSID = apServer.arg("ssid");
  String novaPASS = apServer.arg("pass");
  String novaURL  = apServer.arg("url");

  novoSSID.trim();
  novaURL.trim();

  if (novoSSID.length() > 0) {
    preferences.begin(PREF_NAMESPACE, false);
    preferences.putString("ssid", novoSSID);
    preferences.putString("pass", novaPASS);
    if (novaURL.length() > 0) preferences.putString("server_url", novaURL);
    preferences.end();

    String msg = "<!DOCTYPE html><html lang='pt-BR'><head><meta charset='UTF-8'>";
    msg += "<meta name='viewport' content='width=device-width,initial-scale=1.0'><style>";
    msg += "body{font-family:-apple-system,sans-serif;background:#0b0f19;color:#fff;text-align:center;padding:40px 20px;}";
    msg += ".card{max-width:380px;margin:0 auto;background:#131c31;border-radius:18px;padding:30px;border:1px solid #1e293b;}";
    msg += "h2{color:#10b981;margin-bottom:12px;}p{color:#94a3b8;font-size:14px;line-height:1.5;}";
    msg += ".badge{display:inline-block;padding:8px 16px;background:rgba(16,185,129,0.15);color:#34d399;border-radius:20px;font-size:13px;font-weight:600;margin-top:16px;}";
    msg += "</style></head><body><div class='card'>";
    msg += "<h2>Configurações Gravadas!</h2>";
    msg += "<p>O <strong>Vigil Desk</strong> está reiniciando para conectar na rede:</p>";
    msg += "<div class='badge'>" + novoSSID + "</div>";
    msg += "<p style='margin-top:20px;font-size:12px;'>Se as credenciais estiverem corretas, o display iniciará a exibição em instantes.</p>";
    msg += "</div></body></html>";
    apServer.send(200, "text/html", msg);

    delay(2000);
    ESP.restart();
  } else {
    apServer.send(400, "text/plain", "O SSID nao pode ficar vazio!");
  }
}

void iniciarModoAP() {
  isAPMode = true;
  Serial.println("\n[MODO AP] Ativando Access Point com Scanner do Sistema Vigil...");
  
  WiFi.disconnect(true);
  // Modo Dual (AP + STA) permite criar a rede de setup e escanear redes vizinhas ao mesmo tempo!
  WiFi.mode(WIFI_AP_STA);
  WiFi.softAP(AP_SSID_NAME);

  IPAddress apIP = WiFi.softAPIP();
  Serial.printf("[MODO AP] Rede Setup: %s | IP: %s\n", AP_SSID_NAME, apIP.toString().c_str());

  displayUI.renderAPMode(String(AP_SSID_NAME), apIP.toString());

  apServer.on("/", HTTP_GET, handleAPRoot);
  apServer.on("/salvar", HTTP_POST, handleAPSave);
  apServer.begin();

  Serial.println("[MODO AP] Portal Web Vigil com Scanner iniciado em http://" + apIP.toString());
}

void checkEncoderButton() {
  if (digitalRead(ENCODER_SW) == LOW) {
    if (millis() - lastButtonPress > 300) { // Debounce 300ms
      lastButtonPress = millis();
      
      if (isAPMode) {
        Serial.println("[ENCODER] Saida do Modo AP solicitada. Reiniciando...");
        delay(500);
        ESP.restart();
      } else {
        Serial.println("[ENCODER] Botao Pressionado -> Proximo Modo");
        displayUI.nextMode();
      }
    }
  }
}

// ----------------------------------------------------------------------------
// REQUISIÇÃO HTTP / HTTPS AO SERVIDOR (SUPORTE NATIVO A CLOUDFLARE E LOCAL)
// ----------------------------------------------------------------------------
void fetchServerMetrics() {
  if (WiFi.status() != WL_CONNECTED) {
    serverMetrics.serverOnline = false;
    stationMetrics.stationOnline = false;
    servicesMetrics.serverApiOk = false;
    servicesMetrics.agroclimaOk = false;
    servicesMetrics.postgresOk = false;
    servicesMetrics.mosquittoOk = false;
    return;
  }

  HTTPClient http;
  WiFiClient client;
  WiFiClientSecure secureClient;

  bool isHttps = serverURL.startsWith("https://");

  if (isHttps) {
    secureClient.setInsecure(); // Permite conexões seguras HTTPS sem carregar cadeia de CA pesada
    http.begin(secureClient, serverURL);
    http.setTimeout(3000); // 3s para handshake TLS
  } else {
    http.begin(client, serverURL);
    http.setTimeout(1800);
  }

  int httpCode = http.GET();

  if (httpCode == HTTP_CODE_OK) {
    String payload = http.getString();

    #if ARDUINOJSON_VERSION_MAJOR >= 7
      JsonDocument doc;
    #else
      StaticJsonDocument<2048> doc;
    #endif

    DeserializationError error = deserializeJson(doc, payload);
    if (!error) {
      // Métricas do Servidor
      serverMetrics.serverOnline = true;
      serverMetrics.serverName   = doc["server"]["name"] | "Ubuntu Server1";
      serverMetrics.cpuUsage     = doc["server"]["cpu"] | 0.0f;
      serverMetrics.cpuTemp      = doc["server"]["cpu_temp"] | 0.0f;
      serverMetrics.ramUsage     = doc["server"]["ram"] | 0.0f;
      serverMetrics.diskUsage    = doc["server"]["disk"] | 0.0f;
      serverMetrics.netRxKBps    = doc["server"]["rx_kbps"] | 0.0f;
      serverMetrics.netTxKBps    = doc["server"]["tx_kbps"] | 0.0f;
      serverMetrics.uptimeSec    = doc["server"]["uptime_sec"] | 0;
      serverMetrics.alertLevel   = doc["server"]["alert_level"] | "normal";
      serverMetrics.alertMsg     = doc["server"]["alert_msg"] | "Sistema normal";

      // Métricas da Estação
      JsonObject stObj = doc["station"].is<JsonObject>() ? doc["station"] : doc["gaia"];
      stationMetrics.stationCode    = stObj["station"] | "G00001";
      String gStatus                = stObj["status"] | "OFFLINE";
      stationMetrics.stationOnline  = (gStatus == "ONLINE");
      stationMetrics.temp           = stObj["temp"] | 0.0f;
      stationMetrics.humidity       = stObj["umid"] | 0.0f;
      stationMetrics.pressure       = stObj["pressao"] | 0.0f;
      stationMetrics.vpd            = stObj["vpd"] | 0.0f;
      stationMetrics.et0            = stObj["et0"] | 0.0f;
      stationMetrics.secondsAgo     = stObj["sec_ago"] | 999;

      // Status dos Serviços
      JsonObject sMap = doc["services_status"];
      if (!sMap.isNull()) {
        servicesMetrics.serverApiOk  = sMap["serverApiOk"] | true;
        servicesMetrics.agroclimaOk  = sMap["agroclimaOk"] | true;
        servicesMetrics.postgresOk   = sMap["postgresOk"] | true;
        servicesMetrics.mosquittoOk  = sMap["mosquittoOk"] | true;
        servicesMetrics.pingMs       = sMap["pingMs"] | 2;
      }
    }
  } else {
    serverMetrics.serverOnline = false;
    servicesMetrics.serverApiOk = false;
  }
  http.end();
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("\n=============================================");
  Serial.println("         SISTEMA VIGIL - VIGIL DESK          ");
  Serial.println("=============================================");

  // 1. Configurar Pinos do Encoder
  pinMode(ENCODER_CLK, INPUT_PULLUP);
  pinMode(ENCODER_DT,  INPUT_PULLUP);
  pinMode(ENCODER_SW,  INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(ENCODER_CLK), handleEncoderInterrupt, FALLING);
  Serial.println("[HARDWARE] Encoder EC11 configurado (GPIO 25, 26, 27).");

  // 2. Inicializar Display ILI9341
  displayUI.begin();
  Serial.println("[HARDWARE] Display ILI9341 inicializado com sucesso.");

  // 3. Carregar Configurações da NVS
  preferences.begin(PREF_NAMESPACE, false);
  wifiSSID  = preferences.getString("ssid", DEFAULT_WIFI_SSID);
  wifiPASS  = preferences.getString("pass", DEFAULT_WIFI_PASS);
  serverURL = preferences.getString("server_url", DEFAULT_SERVER_URL);
  preferences.end();

  Serial.printf("[CONFIG] WiFi SSID Salvo: %s\n", wifiSSID.c_str());
  Serial.printf("[CONFIG] Endpoint Salvo:  %s\n", serverURL.c_str());

  // 4. Checagem de Acionamento Manual do Modo AP no Boot (segurar botão por 1s)
  if (digitalRead(ENCODER_SW) == LOW) {
    Serial.println("[BOOT] Botao do encoder pressionado no boot. Entrando no MODO AP...");
    iniciarModoAP();
    return;
  }

  // 5. Conectar ao Wi-Fi Station
  Serial.printf("[WIFI] Conectando a %s...", wifiSSID.c_str());
  WiFi.mode(WIFI_STA);
  WiFi.begin(wifiSSID.c_str(), wifiPASS.c_str());

  unsigned long startWifi = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - startWifi < 7000)) {
    delay(250);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WIFI] Conectado com sucesso!");
    Serial.print("[WIFI] Endereço IP: ");
    Serial.println(WiFi.localIP());

    // Sincronizar Relógio NTP (Horário de Brasília UTC-3)
    configTime(-3 * 3600, 0, "a.st1.ntp.br", "pool.ntp.org", "time.google.com");
    Serial.println("[NTP] Sincronização de horário UTC-3 iniciada.");

    // Primeira consulta à API
    fetchServerMetrics();
  } else {
    Serial.println("\n[WIFI] Falha ao conectar na rede configurada em 7s.");
    Serial.println("[WIFI] Acionando Modo AP automaticamente para reconfiguração...");
    iniciarModoAP();
  }
}

void loop() {
  if (isAPMode) {
    apServer.handleClient();
    checkEncoderButton();
    delay(10);
    return;
  }

  // 1. Tratar Giro do Encoder
  if (encoderPos != lastEncoderPos) {
    int delta = encoderPos - lastEncoderPos;
    lastEncoderPos = encoderPos;
    displayUI.handleEncoderMove(delta);
    Serial.printf("[ENCODER] Mudança de modo! Delta: %d\n", delta);
  }

  // 2. Tratar Clique do Botão do Encoder
  checkEncoderButton();

  // 3. Requisição HTTP / HTTPS ao Servidor a cada 2 segundos
  if (millis() - lastHttpFetch > 2000) {
    lastHttpFetch = millis();
    fetchServerMetrics();
  }

  // 4. Renderização da Tela a cada 500ms
  if (millis() - lastClockRender > 500) {
    lastClockRender = millis();

    // Formata Hora e Data Atual
    time_t rawtime = time(NULL);
    struct tm* ti = localtime(&rawtime);
    char timeBuf[16];
    char dateBuf[32];

    if (rawtime > 1700000000) {
      strftime(timeBuf, sizeof(timeBuf), "%H:%M:%S", ti);
      strftime(dateBuf, sizeof(dateBuf), "%d/%m/%Y", ti);
    } else {
      snprintf(timeBuf, sizeof(timeBuf), "--:--:--");
      snprintf(dateBuf, sizeof(dateBuf), "Aguardando NTP");
    }

    String ipStr = (WiFi.status() == WL_CONNECTED) ? WiFi.localIP().toString() : "Desconectado";
    displayUI.render(serverMetrics, stationMetrics, servicesMetrics, String(timeBuf), String(dateBuf), wifiSSID, ipStr);
  }

  delay(10);
}
