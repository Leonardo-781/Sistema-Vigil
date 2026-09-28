/*
 * ============================================================================
 * SISTEMA VIGIL - VIGIL DESK (Config.h)
 * ============================================================================
 * Monitor de Infraestrutura, Servidores e Bancada
 * ============================================================================
 */

#ifndef CONFIG_H
#define CONFIG_H

#include <Arduino.h>

// ----------------------------------------------------------------------------
// CONFIGURAÇÕES DE REDE E SERVIDOR (PADRÕES INICIAIS)
// DICA: Você não precisa colocar sua senha real aqui!
// Ao ligar o aparelho segurando o botão do encoder (ou caso o Wi-Fi falhe),
// o Vigil inicia a rede "Vigil-Setup" para você configurar tudo pelo celular!
// ----------------------------------------------------------------------------
#define DEFAULT_WIFI_SSID    "SUA_REDE_WIFI_2.4G"
#define DEFAULT_WIFI_PASS    "SUA_SENHA_WIFI"
#define DEFAULT_SERVER_URL   "http://IP_DO_SEU_SERVIDOR:5000/api/status"
#define AP_SSID_NAME         "Vigil-Setup"
#define PREF_NAMESPACE       "vigil_cfg"

// ----------------------------------------------------------------------------
// MAPEAMENTO DE PINOS (DISPLAY TFT ILI9341 SPI & CARTÃO SD)
// Pinos padrão compatíveis com placas ESP32 DevKit e PCBs dedicadas.
// ----------------------------------------------------------------------------
#define TFT_CS   5   // Chip Select do Display
#define TFT_DC   2   // Data / Command do Display
#define TFT_RST  4   // Reset do Display
#define SD_CS   15   // Chip Select do leitor de Cartão SD (Opcional)
#define TFT_BL  -1   // Luz de Fundo (Conectada direto no VCC 3V3)

// Pinos do Barramento SPI padrão do ESP32:
// MOSI = GPIO 23 | SCK = GPIO 18 | MISO = GPIO 19

// ----------------------------------------------------------------------------
// MAPEAMENTO DE PINOS DO ENCODER ROTATIVO (EC11 / KY-040)
// ----------------------------------------------------------------------------
#define ENCODER_CLK 25  // Sinal CLK (Fase A)
#define ENCODER_DT  26  // Sinal DT  (Fase B)
#define ENCODER_SW  27  // Botão de clique integrado (Switch)

// ----------------------------------------------------------------------------
// ESTRUTURAS DE DADOS DOS MONITORAMENTOS
// ----------------------------------------------------------------------------

enum ScreenMode {
  MODE_SERVER_STATS = 0,  // Tela 1: Servidor (CPU %, Temp, RAM, Disco, Rede)
  MODE_FIELD_STATION,    // Tela 2: Estação de Campo / Sensores Externos
  MODE_SERVICES_STATUS,  // Tela 3: Status dos Serviços Docker e Contêineres
  MODE_CLOCK_WIDGET,     // Tela 4: Relógio Digital NTP de Alta Precisão & Rede
  NUM_MODES
};

// Métricas de Servidor
struct ServerMetrics {
  String serverName = "Servidor Principal";
  bool serverOnline = false;
  float cpuUsage = 0.0;       // % Uso de CPU
  float cpuTemp = 0.0;        // Temperatura da CPU (°C)
  float ramUsage = 0.0;       // % Uso de RAM
  float diskUsage = 0.0;      // % Uso de Disco
  float netTxKBps = 0.0;      // Upload KB/s
  float netRxKBps = 0.0;      // Download KB/s
  uint32_t uptimeSec = 0;     // Uptime em segundos
};

// Métricas de Estação Remota / Sensores de Campo
struct FieldStationMetrics {
  String stationCode = "G00001";
  bool stationOnline = false;
  float temp = 0.0;           // Temperatura (°C)
  float humidity = 0.0;       // Umidade Relativa (%)
  float pressure = 0.0;       // Pressão Atmosférica (hPa)
  float vpd = 0.0;            // Déficit de Pressão de Vapor (kPa)
  float et0 = 0.0;            // Evapotranspiração (mm)
  int secondsAgo = 9999;      // Segundos desde a última transmissão
};

// Status dos Serviços
struct ServicesMetrics {
  bool serverApiOk = true;
  bool agentApiOk = true;
  bool postgresOk = true;
  bool mosquittoOk = true;
  int pingMs = 2;
};

#endif // CONFIG_H
