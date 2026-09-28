/*
 * ============================================================================
 * SISTEMA VIGIL - VIGIL DESK
 * ============================================================================
 * Placa Alvo: ESP32 + TFT ILI9341 2.8" + EC11 Encoder
 * Modos: Normal (Wi-Fi Station) + Modo AP com Portal Web para Troca de Rede
 * ============================================================================
 */

#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <Preferences.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <time.h>
#include "Config.h"
#include "DisplayUI.h"

// Instancias Globais
DisplayUI displayUI;
Preferences preferences;
WebServer apServer(80);

ServerMetrics serverMetrics;
FieldStationMetrics stationMetrics;
ServicesMetrics servicesMetrics;

// Configuracoes Dinamicas da NVS
String wifiSSID = DEFAULT_WIFI_SSID;
String wifiPASS = DEFAULT_WIFI_PASS;
String serverURL = DEFAULT_SERVER_URL;

// Modo de Operacao
bool isAPMode = false;

// Controle do Encoder EC11
volatile int encoderPos = 0;
volatile unsigned long lastEncoderInterrupt = 0;
int lastEncoderPos = 0;
unsigned long lastButtonPress = 0;

// Temporizadores
unsigned long lastHttpFetch = 0;
unsigned long lastClockRender = 0;

// Interrupcao de descida (FALLING) no pino CLK (GPIO 25)
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
// PORTAL WEB DO MODO AP (CONFIGURACAO DE WI-FI)
// ----------------------------------------------------------------------------
void handleAPRoot() {
  String html = "<!DOCTYPE html><html lang='pt-BR'><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1.0'>";
  html += "<title>Sistema Vigil - Wi-Fi</title><style>";
  html += "body{font-family:-apple-system,sans-serif;background:#0f172a;color:#f8fafc;padding:20px;margin:0;}";
  html += ".card{max-width:380px;margin:20px auto;background:#1e293b;border-radius:16px;padding:24px;box-shadow:0 10px 25px rgba(0,0,0,0.5);}";
  html += "h2{margin-top:0;font-size:20px;color:#10b981;}p{font-size:13px;color:#94a3b8;line-height:1.4;}";
  html += "label{display:block;margin:12px 0 6px;font-size:13px;font-weight:600;}";
  html += "input,select{width:100%;box-sizing:border-box;padding:12px;border-radius:8px;border:1px solid #334155;background:#0f172a;color:#f8fafc;font-size:14px;margin-bottom:8px;}";
  html += "button{width:100%;padding:14px;border-radius:8px;border:none;background:#10b981;color:#fff;font-size:15px;font-weight:700;cursor:pointer;margin-top:14px;}";
  html += "button:hover{background:#059669;}";
  html += "</style></head><body><div class='card'>";
  html += "<h2>Sistema Vigil</h2><p>Configure a rede Wi-Fi 2.4 GHz e o endpoint do servidor:</p>";
  html += "<form method='POST' action='/salvar'>";
  
  html += "<label>Rede Wi-Fi (SSID):</label>";
  html += "<input type='text' name='ssid' value='" + wifiSSID + "' placeholder='Nome do Wi-Fi' required>";
  
  html += "<label>Senha do Wi-Fi:</label>";
  html += "<input type='password' name='pass' value='" + wifiPASS + "' placeholder='Senha do Wi-Fi'>";

  html += "<label>URL da API do Servidor:</label>";
  html += "<input type='text' name='url' value='" + serverURL + "' placeholder='http://IP_DO_SERVIDOR:5000/api/status'>";

  html += "<button type='submit'>Salvar e Conectar</button>";
  html += "</form></div></body></html>";
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

    String msg = "<!DOCTYPE html><html><body style='font-family:sans-serif;background:#0f172a;color:#fff;text-align:center;padding:50px;'>";
    msg += "<h2 style='color:#10b981;'>Configuracoes Salvas no Vigil!</h2>";
    msg += "<p>O dispositivo esta reiniciando para conectar na nova rede...</p></body></html>";
    apServer.send(200, "text/html", msg);

    delay(2000);
    ESP.restart();
  } else {
    apServer.send(400, "text/plain", "SSID nao pode ser vazio!");
  }
}

void iniciarModoAP() {
  isAPMode = true;
  Serial.println("\n[MODO AP] Ativando Access Point do Sistema Vigil...");
  
  WiFi.disconnect(true);
  WiFi.mode(WIFI_AP);
  WiFi.softAP(AP_SSID_NAME);

  IPAddress apIP = WiFi.softAPIP();
  Serial.printf("[MODO AP] Rede: %s | IP: %s\n", AP_SSID_NAME, apIP.toString().c_str());

  displayUI.renderAPMode(String(AP_SSID_NAME), apIP.toString());

  apServer.on("/", HTTP_GET, handleAPRoot);
  apServer.on("/salvar", HTTP_POST, handleAPSave);
  apServer.begin();

  Serial.println("[MODO AP] Servidor web do Vigil iniciado na porta 80.");
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
  http.begin(serverURL);
  http.setTimeout(1800);
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
      // Metricas do Servidor
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

      // Metricas da Estacao
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

      // Status dos Servicos
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

  // 3. Carregar Configuracoes da NVS
  preferences.begin(PREF_NAMESPACE, false);
  wifiSSID  = preferences.getString("ssid", DEFAULT_WIFI_SSID);
  wifiPASS  = preferences.getString("pass", DEFAULT_WIFI_PASS);
  serverURL = preferences.getString("server_url", DEFAULT_SERVER_URL);
  preferences.end();

  Serial.printf("[CONFIG] WiFi SSID Salvo: %s\n", wifiSSID.c_str());
  Serial.printf("[CONFIG] Endpoint Salvo:  %s\n", serverURL.c_str());

  // 4. Checagem de Acionamento Manual do Modo AP no Boot (segurar botao por 1s)
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
    Serial.print("[WIFI] Endereco IP: ");
    Serial.println(WiFi.localIP());

    // Sincronizar Relogio NTP (Horario de Brasilia UTC-3)
    configTime(-3 * 3600, 0, "a.st1.ntp.br", "pool.ntp.org", "time.google.com");
    Serial.println("[NTP] Sincronizacao de horario UTC-3 iniciada.");

    // Primeira consulta a API
    fetchServerMetrics();
  } else {
    Serial.println("\n[WIFI] Falha ao conectar na rede configurada em 7s.");
    Serial.println("[WIFI] Acionando Modo AP automaticamente para reconfiguracao...");
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
    Serial.printf("[ENCODER] Mudanca de modo! Delta: %d\n", delta);
  }

  // 2. Tratar Clique do Botao do Encoder
  checkEncoderButton();

  // 3. Requisicao HTTP ao Servidor a cada 2 segundos
  if (millis() - lastHttpFetch > 2000) {
    lastHttpFetch = millis();
    fetchServerMetrics();
  }

  // 4. Renderizacao da Tela a cada 500ms
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
