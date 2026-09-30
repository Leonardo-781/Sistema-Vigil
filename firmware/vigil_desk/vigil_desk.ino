/*
 * ============================================================================
 * SISTEMA VIGIL - VIGIL DESK (desk_assistant.ino)
 * ============================================================================
 * Arquitetura Dual-Core FreeRTOS:
 *   - Core 1 (UI @ 200Hz): Encoder Quadratura + 3 Botoes Fisicos + Display SPI 40MHz
 *   - Core 0 (Network Task): Telemetria + Spotify Volume/Midia + DevOps Command Deck
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

DisplayUI displayUI;
Preferences preferences;
WebServer apServer(80);

ServerMetrics serverMetrics;
FieldStationMetrics stationMetrics;
ServicesMetrics servicesMetrics;
SpotifyMetrics spotifyMetrics;
CommandDeckState deckState;

// Buffer em RAM para Capa do Album (80x80 JPEG)
uint8_t spotifyArtBuffer[10240];
size_t spotifyArtLen = 0;
String loadedArtId = "";

// Filas de comandos assincronos para o Core 0
volatile bool pendingSpotifyCmd = false;
String pendingSpotifyAction = "";

volatile bool pendingDeckCmd = false;
String pendingDeckAction = "";

#define REMOTE_URL_PRESET "https://server1.taila7d06b.ts.net:10000/api/status"
#define LOCAL_URL_PRESET  "http://192.168.0.105:5000/api/status"

String wifiSSID = DEFAULT_WIFI_SSID;
String wifiPASS = DEFAULT_WIFI_PASS;
String serverURL = DEFAULT_SERVER_URL;
String activeBaseUrl = "http://192.168.0.105:5000";
bool lanAvailable = true;
bool isAPMode = false;

// ----------------------------------------------------------------------------
// DECODIFICADOR QUADRATURA DE ALTA PRECISAO PARA ENCODER EC11
// ----------------------------------------------------------------------------
volatile int32_t encoderSteps = 0;
volatile uint8_t prevEncState = 0x03;
volatile int8_t  encSubStep = 0;
volatile unsigned long lastStepMs = 0;
int32_t lastHandledSteps = 0;

static const int8_t ENC_TABLE[16] DRAM_ATTR = {
   0, -1,  1,  0,
   1,  0,  0, -1,
  -1,  0,  0,  1,
   0,  1, -1,  0
};

void IRAM_ATTR handleEncoderISR() {
  uint8_t clk = digitalRead(ENCODER_CLK);
  uint8_t dt  = digitalRead(ENCODER_DT);
  uint8_t curState = (clk << 1) | dt;
  if (curState == prevEncState) return;

  uint8_t idx = (prevEncState << 2) | curState;
  prevEncState = curState;
  int8_t dir = ENC_TABLE[idx];

  if (dir != 0) {
    encSubStep += dir;
    if (curState == 0x03) {
      unsigned long now = millis();
      if (encSubStep >= 2 && (now - lastStepMs > 35)) {
        encoderSteps++;
        lastStepMs = now;
      } else if (encSubStep <= -2 && (now - lastStepMs > 35)) {
        encoderSteps--;
        lastStepMs = now;
      }
      encSubStep = 0;
    }
  }
}

unsigned long buttonDownTime = 0;
bool buttonWasDown = false;
bool longPressHandled = false;
unsigned long lastClockRender = 0;

// Debounce dos 3 botoes fisicos dedicados (GPIO 32, 33, 14)
unsigned long lastBtnPrevMs = 0;
unsigned long lastBtnPlayMs = 0;
unsigned long lastBtnNextMs = 0;
bool prevBtnState[3] = {HIGH, HIGH, HIGH};

static const char* DECK_CMD_SLUGS[NUM_DECK_COMMANDS] = {
  "restart_gaia",
  "restart_agro",
  "restart_mqtt",
  "wol",
  "clear_cache",
  "test_tunnel"
};

String extractBaseUrl(const String& fullUrl) {
  int idx = fullUrl.indexOf("/api/");
  if (idx > 0) return fullUrl.substring(0, idx);
  return fullUrl;
}

// ----------------------------------------------------------------------------
// PORTAL WEB DO MODO AP COM SCANNER DE REDES WI-FI E PRESETS DE SERVIDOR
// ----------------------------------------------------------------------------
void handleAPRoot() {
  int n = WiFi.scanNetworks(false, false, false, 300);

  String html = "<!DOCTYPE html><html lang='pt-BR'><head><meta charset='UTF-8'>";
  html += "<meta name='viewport' content='width=device-width,initial-scale=1.0'>";
  html += "<title>Sistema Vigil - Configuracao</title><style>";
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
  html += "input,select{width:100%;box-sizing:border-box;padding:12px 14px;border-radius:10px;border:1px solid #334155;background:#0b1120;color:var(--text);font-size:14px;outline:none;}";
  html += ".btn-rescan{display:inline-flex;align-items:center;gap:6px;background:#1e293b;color:#38bdf8;padding:8px 12px;border-radius:8px;border:1px solid #334155;font-size:12px;font-weight:600;text-decoration:none;margin-bottom:10px;}";
  html += ".presets{display:flex;gap:8px;margin:8px 0 12px;}";
  html += ".btn-preset{flex:1;background:#1e293b;border:1px solid #334155;color:#e2e8f0;padding:8px;border-radius:8px;font-size:11px;font-weight:600;cursor:pointer;text-align:center;}";
  html += ".btn-submit{width:100%;padding:14px;border-radius:10px;border:none;background:linear-gradient(135deg,#10b981,#059669);color:#fff;font-size:15px;font-weight:700;cursor:pointer;margin-top:22px;}";
  html += "</style></head><body><div class='card'>";

  html += "<div class='logo'><div class='logo-icon'>V</div><div><h2>Sistema Vigil</h2><div style='font-size:12px;color:#34d399;'>Painel de Configuracao Wi-Fi</div></div></div>";
  html += "<p class='subtitle'>Selecione uma rede detectada ao redor ou digite as credenciais para conectar o Vigil Desk.</p>";

  html += "<form method='POST' action='/salvar'>";
  html += "<div class='section-title'>1. Rede Wi-Fi (2.4 GHz)</div>";
  html += "<div style='display:flex;justify-content:space-between;align-items:center;'>";
  html += "<label style='margin:0;'>Redes Encontradas:</label>";
  html += "<a href='/' class='btn-rescan'>Atualizar Lista</a>";
  html += "</div>";

  html += "<select id='wifi_list' onchange='pickSSID(this)'>";
  if (n <= 0) {
    html += "<option value=''>Nenhuma rede encontrada</option>";
  } else {
    html += "<option value=''>-- Selecione a rede desejada (" + String(n) + " encontradas) --</option>";
    std::vector<String> seen;
    for (int i = 0; i < n; i++) {
      String ssidFound = WiFi.SSID(i);
      ssidFound.trim();
      if (ssidFound.length() == 0) continue;
      bool exists = false;
      for (const auto& s : seen) { if (s == ssidFound) { exists = true; break; } }
      if (exists) continue;
      seen.push_back(ssidFound);
      int rssi = WiFi.RSSI(i);
      String qual = (rssi > -60) ? "Excelente" : ((rssi > -75) ? "Bom" : "Fraco");
      html += "<option value='" + ssidFound + "'>" + ssidFound + " (" + qual + ")</option>";
    }
  }
  html += "<option value='__manual__'>+ Digitar outra rede manualmente...</option>";
  html += "</select>";

  html += "<label style='margin-top:12px;'>Nome da Rede (SSID):</label>";
  html += "<input type='text' id='ssid_input' name='ssid' value='" + wifiSSID + "' required>";

  html += "<label>Senha do Wi-Fi:</label>";
  html += "<input type='password' id='pass_input' name='pass' value='" + wifiPASS + "'>";
  html += "<div style='margin-top:4px;'><label style='font-size:12px;font-weight:normal;color:var(--muted);cursor:pointer;'><input type='checkbox' style='width:auto;margin-right:6px;' onclick='togglePass()'>Mostrar senha</label></div>";

  html += "<div class='section-title'>2. Endpoint do Servidor Vigil</div>";
  html += "<div class='presets'>";
  html += "<button type='button' class='btn-preset' onclick='setPreset(\"" + String(LOCAL_URL_PRESET) + "\")'>Rede Local (Casa)</button>";
  html += "<button type='button' class='btn-preset' onclick='setPreset(\"" + String(REMOTE_URL_PRESET) + "\")'>Remoto Fixo (HTTPS)</button>";
  html += "</div>";

  html += "<label>URL da API (HTTP ou HTTPS com Fallback Automatico):</label>";
  html += "<input type='text' id='url_input' name='url' value='" + serverURL + "' required>";

  html += "<button type='submit' class='btn-submit'>Salvar e Conectar</button>";
  html += "</form></div>";

  html += "<script>";
  html += "function pickSSID(el){ if(el.value==='__manual__'){document.getElementById('ssid_input').value='';} else if(el.value){document.getElementById('ssid_input').value=el.value;} }";
  html += "function togglePass(){ var p=document.getElementById('pass_input'); p.type=(p.type==='password')?'text':'password'; }";
  html += "function setPreset(url){ document.getElementById('url_input').value=url; }";
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

    apServer.send(200, "text/html", "<html><body style='background:#0b0f19;color:#10b981;text-align:center;padding:40px;font-family:sans-serif;'><h2>Configuracoes Salvas! Reiniciando...</h2></body></html>");
    delay(1500);
    ESP.restart();
  } else {
    apServer.send(400, "text/plain", "O SSID nao pode ficar vazio!");
  }
}

void iniciarModoAP() {
  isAPMode = true;
  Serial.println("\n[MODO AP] Ativando Access Point com Scanner do Sistema Vigil...");
  
  WiFi.setAutoReconnect(false);
  WiFi.disconnect(true, true);
  delay(100);
  WiFi.mode(WIFI_AP_STA);
  WiFi.softAP(AP_SSID_NAME, NULL, 1, 0, 4);

  IPAddress apIP = WiFi.softAPIP();
  displayUI.renderAPMode(String(AP_SSID_NAME), apIP.toString());

  apServer.on("/", HTTP_GET, handleAPRoot);
  apServer.on("/salvar", HTTP_POST, handleAPSave);
  apServer.begin();
}

// ----------------------------------------------------------------------------
// COMANDOS SPOTIFY E DEVOPS COMMAND DECK (EXECUTADOS NO CORE 0)
// ----------------------------------------------------------------------------
bool sendSpotifyCommandNow(const String& action) {
  if (WiFi.status() != WL_CONNECTED) return false;
  String cmdUrl = activeBaseUrl + "/api/spotify/" + action;
  Serial.printf("[SPOTIFY] Comando (Core 0): %s\n", cmdUrl.c_str());

  HTTPClient http;
  WiFiClient client;
  WiFiClientSecure secureClient;

  if (cmdUrl.startsWith("https://")) {
    secureClient.setInsecure();
    http.begin(secureClient, cmdUrl);
  } else {
    http.begin(client, cmdUrl);
  }
  http.setTimeout(2500);
  int code = http.POST("");
  http.end();
  return (code >= 200 && code < 300);
}

bool sendDeckCommandNow(const String& slug) {
  if (WiFi.status() != WL_CONNECTED) {
    deckState.lastStatusMsg = "Erro: Sem conexao Wi-Fi";
    return false;
  }
  String cmdUrl = activeBaseUrl + "/api/cmd/" + slug;
  Serial.printf("[DECK] Executando comando (Core 0): %s\n", cmdUrl.c_str());

  HTTPClient http;
  WiFiClient client;
  WiFiClientSecure secureClient;

  if (cmdUrl.startsWith("https://")) {
    secureClient.setInsecure();
    http.begin(secureClient, cmdUrl);
  } else {
    http.begin(client, cmdUrl);
  }
  http.setTimeout(4000);
  int code = http.POST("");
  if (code >= 200 && code < 300) {
    String resp = http.getString();
    http.end();
    #if ARDUINOJSON_VERSION_MAJOR >= 7
      JsonDocument doc;
    #else
      StaticJsonDocument<512> doc;
    #endif
    if (!deserializeJson(doc, resp)) {
      deckState.lastStatusMsg = String("OK: ") + (doc["message"] | "Comando executado!");
    } else {
      deckState.lastStatusMsg = "OK: Comando executado com sucesso!";
    }
    return true;
  }
  http.end();
  deckState.lastStatusMsg = "Falha HTTP (" + String(code) + ") ao executar";
  return false;
}

bool fetchSpotifyAlbumArt(const String& artId) {
  if (WiFi.status() != WL_CONNECTED || artId.length() == 0) return false;
  if (artId == loadedArtId && spotifyArtLen > 64) return true;

  String artUrl = activeBaseUrl + "/api/spotify/art.jpg?id=" + artId;
  HTTPClient http;
  WiFiClient client;
  WiFiClientSecure secureClient;

  if (artUrl.startsWith("https://")) {
    secureClient.setInsecure();
    http.begin(secureClient, artUrl);
  } else {
    http.begin(client, artUrl);
  }
  http.setTimeout(2500);
  int code = http.GET();
  bool ok = false;

  if (code == HTTP_CODE_OK) {
    int total = http.getSize();
    if (total > 64 && total < (int)sizeof(spotifyArtBuffer)) {
      WiFiClient* stream = http.getStreamPtr();
      size_t readBytes = 0;
      unsigned long t0 = millis();
      while (http.connected() && readBytes < (size_t)total && (millis() - t0 < 2000)) {
        size_t avail = stream->available();
        if (avail > 0) {
          int r = stream->readBytes(spotifyArtBuffer + readBytes, min(avail, sizeof(spotifyArtBuffer) - readBytes));
          if (r > 0) readBytes += r;
        } else {
          vTaskDelay(pdMS_TO_TICKS(5));
        }
      }
      if (readBytes == (size_t)total) {
        spotifyArtLen = readBytes;
        loadedArtId = artId;
        ok = true;
      }
    }
  }
  http.end();
  return ok;
}

bool tryFetchEndpoint(const String& targetUrl, int timeoutMs) {
  HTTPClient http;
  WiFiClient client;
  WiFiClientSecure secureClient;

  bool isHttps = targetUrl.startsWith("https://");
  if (isHttps) {
    secureClient.setInsecure();
    http.begin(secureClient, targetUrl);
    http.setTimeout(timeoutMs);
  } else {
    http.setConnectTimeout(450);
    http.begin(client, targetUrl);
    http.setTimeout(timeoutMs);
  }

  int httpCode = http.GET();
  if (httpCode != HTTP_CODE_OK) {
    http.end();
    return false;
  }

  String payload = http.getString();
  http.end();

  #if ARDUINOJSON_VERSION_MAJOR >= 7
    JsonDocument doc;
  #else
    StaticJsonDocument<4096> doc;
  #endif

  DeserializationError error = deserializeJson(doc, payload);
  if (error) return false;

  activeBaseUrl = extractBaseUrl(targetUrl);

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

  JsonObject sMap = doc["services_status"];
  if (!sMap.isNull()) {
    servicesMetrics.serverApiOk  = sMap["serverApiOk"] | true;
    servicesMetrics.agroclimaOk  = sMap["agroclimaOk"] | true;
    servicesMetrics.postgresOk   = sMap["postgresOk"] | true;
    servicesMetrics.mosquittoOk  = sMap["mosquittoOk"] | true;
    servicesMetrics.pingMs       = sMap["pingMs"] | 2;
  }

  JsonObject spObj = doc["spotify"];
  if (!spObj.isNull()) {
    spotifyMetrics.active     = spObj["active"] | false;
    spotifyMetrics.isPlaying  = spObj["is_playing"] | false;
    spotifyMetrics.trackName  = spObj["track"] | "Nenhuma musica";
    spotifyMetrics.artistName = spObj["artist"] | "Spotify Ocioso";
    spotifyMetrics.albumName  = spObj["album"] | "";
    spotifyMetrics.progressMs = spObj["progress_ms"] | 0;
    spotifyMetrics.durationMs = spObj["duration_ms"] | 0;
    if (!pendingSpotifyCmd) {
      spotifyMetrics.volumePct = spObj["volume"] | spotifyMetrics.volumePct;
    }
    String newArtId           = spObj["art_id"] | "";
    spotifyMetrics.artId      = newArtId;

    if (newArtId.length() > 0) {
      spotifyMetrics.artValid = fetchSpotifyAlbumArt(newArtId);
    } else {
      spotifyMetrics.artValid = false;
    }
  }

  return true;
}

void fetchServerMetrics() {
  if (WiFi.status() != WL_CONNECTED) {
    serverMetrics.serverOnline = false;
    stationMetrics.stationOnline = false;
    servicesMetrics.serverApiOk = false;
    return;
  }

  if (lanAvailable) {
    if (tryFetchEndpoint(LOCAL_URL_PRESET, 800)) return;
    lanAvailable = false;
  }

  if (tryFetchEndpoint(serverURL, 3500)) return;

  if (tryFetchEndpoint(LOCAL_URL_PRESET, 800)) {
    lanAvailable = true;
    return;
  }

  serverMetrics.serverOnline = false;
  servicesMetrics.serverApiOk = false;
}

// Task dedicada no Core 0 para Rede/HTTP/HTTPS
void networkTaskCode(void* parameter) {
  unsigned long lastFetch = 0;
  for (;;) {
    if (!isAPMode && WiFi.status() == WL_CONNECTED) {
      if (pendingSpotifyCmd) {
        String act = pendingSpotifyAction;
        pendingSpotifyCmd = false;
        sendSpotifyCommandNow(act);
        fetchServerMetrics();
        lastFetch = millis();
      } else if (pendingDeckCmd) {
        String slug = pendingDeckAction;
        pendingDeckCmd = false;
        sendDeckCommandNow(slug);
        fetchServerMetrics();
        lastFetch = millis();
      } else if (millis() - lastFetch >= 1800) {
        fetchServerMetrics();
        lastFetch = millis();
      }
    }
    vTaskDelay(pdMS_TO_TICKS(30));
  }
}

// Aciona ou confirma a execucao de um comando na Tela 5 (Safety Lock de 3s)
void triggerDeckExecution() {
  unsigned long now = millis();
  if (!deckState.confirmPending) {
    deckState.confirmPending = true;
    deckState.confirmTimestamp = now;
    deckState.lastStatusMsg = "CONFIRMAR? Clique PLAY/Encoder em ate 3s!";
    lastClockRender = 0;
  } else {
    deckState.confirmPending = false;
    deckState.lastStatusMsg = "Executando comando no servidor...";
    pendingDeckAction = String(DECK_CMD_SLUGS[deckState.selectedIndex]);
    pendingDeckCmd = true;
    lastClockRender = 0;
  }
}

// ----------------------------------------------------------------------------
// LEITURA DOS 3 BOTOES FISICOS DEDICADOS (PREV=32, PLAY=33, NEXT=14)
// ----------------------------------------------------------------------------
void checkDedicatedButtons() {
  unsigned long now = millis();

  // expiracao automatica do Safety Lock apos 3.5 segundos
  if (deckState.confirmPending && (now - deckState.confirmTimestamp > 3500)) {
    deckState.confirmPending = false;
    deckState.lastStatusMsg = "Cancelado (tempo expirado).";
    lastClockRender = 0;
  }

  // 1. Botao PREV (GPIO 32)
  bool bPrev = digitalRead(BTN_PREV_PIN);
  if (bPrev == LOW && prevBtnState[0] == HIGH && (now - lastBtnPrevMs > 180)) {
    lastBtnPrevMs = now;
    if (displayUI.getMode() == MODE_COMMAND_DECK) {
      deckState.selectedIndex = (deckState.selectedIndex + NUM_DECK_COMMANDS - 1) % NUM_DECK_COMMANDS;
      deckState.confirmPending = false;
      lastClockRender = 0;
    } else {
      displayUI.showSpotifyToast("   << Faixa Anterior <<   ");
      pendingSpotifyAction = "prev";
      pendingSpotifyCmd = true;
    }
  }
  prevBtnState[0] = bPrev;

  // 2. Botao PLAY/PAUSE / EXECUTAR (GPIO 33)
  bool bPlay = digitalRead(BTN_PLAY_PIN);
  if (bPlay == LOW && prevBtnState[1] == HIGH && (now - lastBtnPlayMs > 180)) {
    lastBtnPlayMs = now;
    if (displayUI.getMode() == MODE_COMMAND_DECK) {
      triggerDeckExecution();
    } else {
      spotifyMetrics.isPlaying = !spotifyMetrics.isPlaying;
      displayUI.showSpotifyToast(spotifyMetrics.isPlaying ? "      > Tocando...       " : "      || Pausando...     ");
      pendingSpotifyAction = "toggle";
      pendingSpotifyCmd = true;
      lastClockRender = 0;
    }
  }
  prevBtnState[1] = bPlay;

  // 3. Botao NEXT (GPIO 14)
  bool bNext = digitalRead(BTN_NEXT_PIN);
  if (bNext == LOW && prevBtnState[2] == HIGH && (now - lastBtnNextMs > 180)) {
    lastBtnNextMs = now;
    if (displayUI.getMode() == MODE_COMMAND_DECK) {
      deckState.selectedIndex = (deckState.selectedIndex + 1) % NUM_DECK_COMMANDS;
      deckState.confirmPending = false;
      lastClockRender = 0;
    } else {
      displayUI.showSpotifyToast("   >> Proxima Faixa >>   ");
      pendingSpotifyAction = "next";
      pendingSpotifyCmd = true;
    }
  }
  prevBtnState[2] = bNext;
}

// ----------------------------------------------------------------------------
// BOTAO DO ENCODER (SW = GPIO 27)
// ----------------------------------------------------------------------------
void checkEncoderButton() {
  bool isDown = (digitalRead(ENCODER_SW) == LOW);
  unsigned long now = millis();

  if (isDown && !buttonWasDown) {
    buttonWasDown = true;
    buttonDownTime = now;
    longPressHandled = false;
  } else if (isDown && buttonWasDown) {
    if (!longPressHandled && (now - buttonDownTime > 750)) {
      longPressHandled = true;
      if (isAPMode) {
        ESP.restart();
      } else if (displayUI.getMode() == MODE_SPOTIFY) {
        // Segurar 0.8s na tela Spotify: Play/Pause (caso esteja sem os botoes extras soldados)
        spotifyMetrics.isPlaying = !spotifyMetrics.isPlaying;
        displayUI.showSpotifyToast(spotifyMetrics.isPlaying ? "      > Tocando...       " : "      || Pausando...     ");
        pendingSpotifyAction = "toggle";
        pendingSpotifyCmd = true;
      } else if (displayUI.getMode() == MODE_COMMAND_DECK) {
        // Segurar 0.8s na tela Comandos: Executa o comando selecionado
        triggerDeckExecution();
      } else {
        displayUI.nextMode();
        lastClockRender = 0;
      }
    }
  } else if (!isDown && buttonWasDown) {
    unsigned long held = now - buttonDownTime;
    buttonWasDown = false;
    if (!longPressHandled && held > 35) {
      if (isAPMode) {
        ESP.restart();
      } else if (displayUI.getMode() == MODE_SPOTIFY) {
        // 1 Clique no Encoder na tela Spotify: Alterna Modo Volume (Girar = Volume) vs Modo Telas!
        displayUI.toggleSpotifyVolumeLock();
        lastClockRender = 0;
      } else if (displayUI.getMode() == MODE_COMMAND_DECK) {
        if (deckState.confirmPending) {
          triggerDeckExecution();
        } else {
          deckState.encoderNavLock = !deckState.encoderNavLock;
          deckState.lastStatusMsg = deckState.encoderNavLock ? "Gire p/ escolher comando | Segure: Executar" : "Modo Telas ativo (Gire p/ sair da tela)";
          lastClockRender = 0;
        }
      } else {
        displayUI.nextMode();
        lastClockRender = 0;
      }
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\n=============================================");
  Serial.println("   SISTEMA VIGIL - DUAL-CORE TURBO EDITION   ");
  Serial.println("=============================================");

  pinMode(ENCODER_CLK, INPUT_PULLUP);
  pinMode(ENCODER_DT,  INPUT_PULLUP);
  pinMode(ENCODER_SW,  INPUT_PULLUP);
  pinMode(BTN_PREV_PIN, INPUT_PULLUP);
  pinMode(BTN_PLAY_PIN, INPUT_PULLUP);
  pinMode(BTN_NEXT_PIN, INPUT_PULLUP);

  prevEncState = (digitalRead(ENCODER_CLK) << 1) | digitalRead(ENCODER_DT);
  attachInterrupt(digitalPinToInterrupt(ENCODER_CLK), handleEncoderISR, CHANGE);
  attachInterrupt(digitalPinToInterrupt(ENCODER_DT),  handleEncoderISR, CHANGE);
  Serial.println("[HARDWARE] Encoder Quadratura + 3 Botoes Dedicados (GPIO 32, 33, 14) prontos.");

  displayUI.begin();
  Serial.println("[HARDWARE] Display ILI9341 (SPI 40MHz) + TJpg_Decoder inicializados.");

  preferences.begin(PREF_NAMESPACE, false);
  wifiSSID  = preferences.getString("ssid", DEFAULT_WIFI_SSID);
  wifiPASS  = preferences.getString("pass", DEFAULT_WIFI_PASS);
  serverURL = preferences.getString("server_url", DEFAULT_SERVER_URL);
  if (serverURL.indexOf("trycloudflare.com") >= 0 || serverURL.length() == 0) {
    serverURL = REMOTE_URL_PRESET;
    preferences.putString("server_url", serverURL);
  }
  preferences.end();

  if (digitalRead(ENCODER_SW) == LOW) {
    iniciarModoAP();
    return;
  }

  Serial.printf("[WIFI] Conectando a %s...", wifiSSID.c_str());
  WiFi.mode(WIFI_STA);
  WiFi.begin(wifiSSID.c_str(), wifiPASS.c_str());

  unsigned long startWifi = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - startWifi < 8000)) {
    delay(200);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WIFI] Conectado! IP: " + WiFi.localIP().toString());
    configTime(-3 * 3600, 0, "a.st1.ntp.br", "pool.ntp.org", "time.google.com");

    xTaskCreatePinnedToCore(
      networkTaskCode,
      "VigilNetTask",
      10240,
      NULL,
      1,
      NULL,
      0
    );
    Serial.println("[RTOS] VigilNetTask iniciada no Core 0 (UI 100% livre no Core 1).");
  } else {
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

  // 1. Tratar Giro do Encoder (Volume no Spotify, Menu de Comandos ou Troca de Tela)
  int32_t curSteps = encoderSteps;
  if (curSteps != lastHandledSteps) {
    int delta = (int)(curSteps - lastHandledSteps);
    lastHandledSteps = curSteps;

    if (displayUI.getMode() == MODE_SPOTIFY && displayUI.isSpotifyVolumeLocked()) {
      // Ajusta o Volume do Spotify em passos de 5%!
      int newVol = constrain(spotifyMetrics.volumePct + (delta > 0 ? 5 : -5), 0, 100);
      spotifyMetrics.volumePct = newVol;
      pendingSpotifyAction = "volume?val=" + String(newVol);
      pendingSpotifyCmd = true;
      lastClockRender = 0;
    } else if (displayUI.getMode() == MODE_COMMAND_DECK && deckState.encoderNavLock) {
      // Navega entre os 6 comandos do DevOps Command Deck
      if (delta > 0) {
        deckState.selectedIndex = (deckState.selectedIndex + 1) % NUM_DECK_COMMANDS;
      } else {
        deckState.selectedIndex = (deckState.selectedIndex + NUM_DECK_COMMANDS - 1) % NUM_DECK_COMMANDS;
      }
      deckState.confirmPending = false;
      lastClockRender = 0;
    } else {
      displayUI.handleEncoderMove(delta);
      deckState.encoderNavLock = false;
      deckState.confirmPending = false;
      lastClockRender = 0;
    }
  }

  // 2. Tratar Botoes Fisicos Dedicados (GPIO 32, 33, 14) e Clique do Encoder
  checkDedicatedButtons();
  checkEncoderButton();

  // 3. Renderizacao Fluida da Tela
  if (millis() - lastClockRender >= 400) {
    lastClockRender = millis();

    if (spotifyMetrics.isPlaying && spotifyMetrics.durationMs > 0 && spotifyMetrics.progressMs + 400 <= spotifyMetrics.durationMs) {
      spotifyMetrics.progressMs += 400;
    }

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
    displayUI.render(serverMetrics, stationMetrics, servicesMetrics, spotifyMetrics, deckState,
                     spotifyArtBuffer, spotifyArtLen, String(timeBuf), String(dateBuf), wifiSSID, ipStr);
  }

  delay(5);
}
