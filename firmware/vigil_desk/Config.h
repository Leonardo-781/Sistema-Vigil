/*
 * ============================================================================
 * SISTEMA VIGIL - VIGIL DESK (Config.h)
 * ============================================================================
 * Monitor de Infraestrutura, Servidores, Bancada, Spotify & DevOps Command Deck
 * ============================================================================
 */

#ifndef CONFIG_H
#define CONFIG_H

#include <Arduino.h>

// ----------------------------------------------------------------------------
// CONFIGURAÇÕES PADRÃO DE REDE E SERVIDOR (ARMAZENADAS NA FLASH NVS)
// ----------------------------------------------------------------------------
#define DEFAULT_WIFI_SSID    "SUA_REDE_WIFI"
#define DEFAULT_WIFI_PASS    "SUA_SENHA_WIFI"
#define DEFAULT_SERVER_URL   "https://server1.taila7d06b.ts.net:10000/api/status"
#define AP_SSID_NAME         "Vigil-Setup"
#define PREF_NAMESPACE       "vigil_cfg"

// ----------------------------------------------------------------------------
// PINOS DA PCB (DISPLAY TFT ILI9341 SPI & CARTÃO SD)
// ----------------------------------------------------------------------------
#define TFT_CS   5   // Chip Select Display
#define TFT_DC   2   // Data / Command Display
#define TFT_RST  4   // Reset Display
#define SD_CS   15   // Chip Select Cartao SD
#define TFT_BL  -1   // Luz de Fundo (VCC 3V3)

// Pinos SPI Padrao no ESP32: MOSI=GPIO 23, SCK=GPIO 18, MISO=GPIO 19

// ----------------------------------------------------------------------------
// PINOS DO ENCODER ROTATIVO EC11
// ----------------------------------------------------------------------------
#define ENCODER_CLK 25  // Pino CLK / Phase A
#define ENCODER_DT  26  // Pino DT / Phase B
#define ENCODER_SW  27  // Pino SW / Botao integrado

// ----------------------------------------------------------------------------
// PINOS DOS 3 BOTÕES FÍSICOS DEDICADOS (INPUT_PULLUP -> GND)
// ----------------------------------------------------------------------------
#define BTN_PREV_PIN 32 // Botao 1: Faixa Anterior (Spotify) / Subir (Menu Comandos)
#define BTN_PLAY_PIN 33 // Botao 2: Play/Pause (Spotify)     / Executar (Menu Comandos)
#define BTN_NEXT_PIN 14 // Botao 3: Proxima Faixa (Spotify)  / Descer (Menu Comandos)

// ----------------------------------------------------------------------------
// ESTRUTURAS DE DADOS DOS MONITORAMENTOS (6 MODOS DE TELA)
// ----------------------------------------------------------------------------

enum ScreenMode {
  MODE_SERVER_STATS = 0,  // Tela 1: Servidor Ubuntu (CPU, Temp, RAM, Disco, Rede)
  MODE_FIELD_STATION,     // Tela 2: Estacao de Campo (Temperatura, Umidade, VPD)
  MODE_SERVICES_STATUS,   // Tela 3: Status dos Servicos Docker (Server, DB, MQTT)
  MODE_SPOTIFY,           // Tela 4: Spotify Player, Capa & Controle de Volume no Encoder
  MODE_COMMAND_DECK,      // Tela 5: DevOps Command Deck (Restart Containers, WOL, Tunnel)
  MODE_CLOCK_WIDGET,      // Tela 6: Relogio Digital de Mesa NTP & Rede
  NUM_MODES
};

// Dados do Servidor
struct ServerMetrics {
  String serverName = "Ubuntu Server1";
  bool serverOnline = false;
  float cpuUsage = 0.0;       // % Uso de CPU
  float cpuTemp = 0.0;        // Temperatura da CPU (C)
  float ramUsage = 0.0;       // % Uso de RAM
  float diskUsage = 0.0;      // % Uso de Disco
  float netTxKBps = 0.0;      // Upload KB/s
  float netRxKBps = 0.0;      // Download KB/s
  uint32_t uptimeSec = 0;     // Uptime em segundos
  String alertLevel = "normal"; // "normal", "warning", "critical"
  String alertMsg = "Sistema normal";
};

// Dados da Estacao de Campo
struct FieldStationMetrics {
  String stationCode = "G00001";
  bool stationOnline = false;
  float temp = 0.0;           // Temperatura (C)
  float humidity = 0.0;       // Umidade (%)
  float pressure = 0.0;       // Pressao (hPa)
  float vpd = 0.0;            // VPD (kPa)
  float et0 = 0.0;            // ET0 (mm)
  int secondsAgo = 9999;      // Segundos desde ultima leitura
};

// Status dos Servicos
struct ServicesMetrics {
  bool serverApiOk = true;   // Gaia 3000
  bool agroclimaOk = true;   // Agroclima 3001
  bool postgresOk = true;    // Postgres 5432
  bool mosquittoOk = true;   // Mosquitto 1883
  int pingMs = 2;
};

// Dados do Spotify
struct SpotifyMetrics {
  bool active = false;
  bool isPlaying = false;
  String trackName = "Nenhuma musica";
  String artistName = "Spotify Ocioso";
  String albumName = "";
  uint32_t progressMs = 0;
  uint32_t durationMs = 0;
  int volumePct = 75;
  String artId = "";
  bool artValid = false;
};

// Estado da Tela 5 (DevOps Command Deck)
#define NUM_DECK_COMMANDS 6

struct CommandDeckState {
  int selectedIndex = 0;          // 0 a 5
  bool encoderNavLock = false;    // true = girar encoder navega nos comandos
  bool confirmPending = false;    // Safety Lock: aguarda segundo clique em ate 3s
  unsigned long confirmTimestamp = 0;
  String lastStatusMsg = "Selecione e pressione PLAY ou Encoder";
};

#endif // CONFIG_H
