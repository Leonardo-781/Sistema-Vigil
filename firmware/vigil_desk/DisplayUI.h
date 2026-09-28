/*
 * ============================================================================
 * SISTEMA VIGIL - VIGIL DESK DASHBOARD
 * ============================================================================
 * Renderizacao fluida (Anti-flicker) para display ILI9341 320x240 + EC11 Encoder.
 * Suporte a Alertas Térmicos, Monitor de Serviços Docker e Modo AP.
 * ============================================================================
 */

#ifndef DISPLAYUI_H
#define DISPLAYUI_H

#include <Arduino.h>
#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ILI9341.h>
#include "Config.h"

class DisplayUI {
private:
  Adafruit_ILI9341 tft;
  ScreenMode currentMode = MODE_SERVER_STATS;
  bool needFullRedraw = true;
  String lastAlertLevel = "normal";

public:
  DisplayUI() : tft(TFT_CS, TFT_DC, TFT_RST) {}

  void begin() {
    SPI.begin(18, 19, 23, TFT_CS);
    tft.begin();
    tft.setRotation(1); // Paisagem (320x240)
    tft.fillScreen(ILI9341_BLACK);
    needFullRedraw = true;
  }

  ScreenMode getMode() const { return currentMode; }

  void nextMode() {
    currentMode = static_cast<ScreenMode>((currentMode + 1) % NUM_MODES);
    needFullRedraw = true;
  }

  void prevMode() {
    currentMode = static_cast<ScreenMode>((currentMode + NUM_MODES - 1) % NUM_MODES);
    needFullRedraw = true;
  }

  void handleEncoderMove(int delta) {
    if (delta > 0) {
      nextMode();
    } else if (delta < 0) {
      prevMode();
    }
  }

  void renderAPMode(const String& apSSID, const String& apIP) {
    tft.fillScreen(ILI9341_BLACK);
    tft.fillRect(0, 0, 320, 28, ILI9341_NAVY);
    tft.drawFastHLine(0, 28, 320, ILI9341_BLUE);
    tft.setTextColor(ILI9341_WHITE, ILI9341_NAVY);
    tft.setTextSize(2);
    tft.setCursor(8, 6);
    tft.print("VIGIL // CONFIG WI-FI");

    tft.drawRoundRect(10, 38, 300, 192, 8, ILI9341_YELLOW);
    
    tft.setTextColor(ILI9341_YELLOW, ILI9341_BLACK);
    tft.setTextSize(2);
    tft.setCursor(24, 52);
    tft.print("MODO ACCESS POINT");

    tft.setTextSize(1);
    tft.setTextColor(ILI9341_LIGHTGREY, ILI9341_BLACK);
    tft.setCursor(24, 82);
    tft.print("1. Conecte seu celular na rede Wi-Fi:");
    
    tft.setTextSize(2);
    tft.setTextColor(ILI9341_CYAN, ILI9341_BLACK);
    tft.setCursor(24, 98);
    tft.print(apSSID);

    tft.setTextSize(1);
    tft.setTextColor(ILI9341_LIGHTGREY, ILI9341_BLACK);
    tft.setCursor(24, 128);
    tft.print("2. Abra o navegador e acesse:");
    
    tft.setTextSize(2);
    tft.setTextColor(ILI9341_GREEN, ILI9341_BLACK);
    tft.setCursor(24, 144);
    tft.print(apIP);

    tft.drawFastHLine(20, 175, 280, ILI9341_DARKGREY);
    tft.setTextSize(1);
    tft.setTextColor(ILI9341_LIGHTGREY, ILI9341_BLACK);
    tft.setCursor(24, 190);
    tft.print("Clique no encoder para sair");
  }

  void render(const ServerMetrics& srv, const FieldStationMetrics& st, const ServicesMetrics& srvc, const String& timeStr, const String& dateStr, const String& wifiSsid, const String& ipStr) {
    // Se o estado de alerta mudou de normal para critico ou vice-versa, redesenha o cabecalho
    if (srv.alertLevel != lastAlertLevel) {
      lastAlertLevel = srv.alertLevel;
      needFullRedraw = true;
    }

    if (needFullRedraw) {
      tft.fillScreen(ILI9341_BLACK);
      renderHeader(srv);
      renderStaticLayout();
      needFullRedraw = false;
    }

    switch (currentMode) {
      case MODE_SERVER_STATS:
        updateServerStats(srv);
        break;
      case MODE_FIELD_STATION:
        updateFieldStation(st);
        break;
      case MODE_SERVICES_STATUS:
        updateServicesStatus(srvc);
        break;
      case MODE_CLOCK_WIDGET:
        updateClockWidget(srv, timeStr, dateStr, wifiSsid, ipStr);
        break;
      default:
        break;
    }
  }

private:
  void renderHeader(const ServerMetrics& srv) {
    bool isCrit = (srv.alertLevel == "critical" || srv.cpuTemp >= 75.0);
    bool isWarn = (srv.alertLevel == "warning" || srv.cpuTemp >= 65.0);

    uint16_t bg = isCrit ? ILI9341_RED : (isWarn ? 0x9B20 /* Dark Orange */ : ILI9341_NAVY);
    uint16_t border = isCrit ? ILI9341_MAROON : (isWarn ? ILI9341_YELLOW : ILI9341_BLUE);

    tft.fillRect(0, 0, 320, 26, bg);
    tft.drawFastHLine(0, 26, 320, border);
    tft.setTextColor(ILI9341_WHITE, bg);
    tft.setTextSize(2);
    tft.setCursor(8, 5);

    if (isCrit) {
      tft.print("! ALERTA TERMICO !");
    } else {
      switch (currentMode) {
        case MODE_SERVER_STATS:   tft.print("VIGIL // SERVIDOR"); break;
        case MODE_FIELD_STATION:  tft.print("VIGIL // CAMPO"); break;
        case MODE_SERVICES_STATUS:tft.print("VIGIL // SERVICOS"); break;
        case MODE_CLOCK_WIDGET:   tft.print("VIGIL // DESK CLOCK"); break;
        default: break;
      }
    }

    // Indicador de Telas (Pontos no canto direito)
    for (int i = 0; i < NUM_MODES; i++) {
      uint16_t color = (i == currentMode) ? (isCrit ? ILI9341_WHITE : ILI9341_YELLOW) : ILI9341_DARKGREY;
      tft.fillCircle(265 + (i * 13), 13, 4, color);
    }
  }

  void renderStaticLayout() {
    switch (currentMode) {
      case MODE_SERVER_STATS:
        tft.drawRoundRect(8, 32, 304, 202, 6, ILI9341_CYAN);
        tft.setTextColor(ILI9341_LIGHTGREY, ILI9341_BLACK);
        tft.setTextSize(1);
        tft.setCursor(18, 70);  tft.print("CPU:");
        tft.setCursor(18, 95);  tft.print("RAM:");
        tft.setCursor(18, 120); tft.print("DISCO:");
        
        tft.drawRect(80, 68, 170, 11, ILI9341_DARKGREY);
        tft.drawRect(80, 93, 170, 11, ILI9341_DARKGREY);
        tft.drawRect(80, 118, 170, 11, ILI9341_DARKGREY);

        // Caixa de Rede
        tft.drawRoundRect(16, 140, 288, 54, 4, ILI9341_DARKGREY);
        tft.setCursor(24, 146);
        tft.setTextColor(ILI9341_CYAN, ILI9341_BLACK);
        tft.print("TRAFEGO DE REDE (ETH)");
        tft.setCursor(24, 161);
        tft.setTextColor(ILI9341_GREEN, ILI9341_BLACK);
        tft.print("DOWNLOAD (RX):");
        tft.setCursor(24, 176);
        tft.setTextColor(ILI9341_YELLOW, ILI9341_BLACK);
        tft.print("UPLOAD   (TX):");

        // Rodape
        tft.setTextColor(ILI9341_DARKGREY, ILI9341_BLACK);
        tft.setCursor(16, 208);
        tft.print("Gire o Encoder para alternar telas");
        break;

      case MODE_FIELD_STATION:
        tft.drawRoundRect(8, 32, 304, 202, 6, ILI9341_GREEN);
        tft.setTextColor(ILI9341_LIGHTGREY, ILI9341_BLACK);
        tft.setTextSize(1);
        tft.setCursor(18, 44);
        tft.print("MONITOR DE TELEMETRIA G00001 (Monte Carmelo)");

        // 4 Caixas de Sensores
        tft.drawRoundRect(16, 60, 140, 64, 4, ILI9341_DARKGREY);
        tft.drawRoundRect(164, 60, 140, 64, 4, ILI9341_DARKGREY);
        tft.drawRoundRect(16, 130, 140, 64, 4, ILI9341_DARKGREY);
        tft.drawRoundRect(164, 130, 140, 64, 4, ILI9341_DARKGREY);

        tft.setCursor(24, 66);  tft.print("TEMPERATURA");
        tft.setCursor(172, 66); tft.print("UMIDADE RELATIVA");
        tft.setCursor(24, 136); tft.print("PRESSAO ATM.");
        tft.setCursor(172, 136);tft.print("DEFICIT VAPOR (VPD)");

        // Rodape
        tft.setTextColor(ILI9341_DARKGREY, ILI9341_BLACK);
        tft.setCursor(16, 208);
        tft.print("Ultimo pacote recebido via WiFi/HTTP");
        break;

      case MODE_SERVICES_STATUS:
        tft.drawRoundRect(8, 32, 304, 202, 6, ILI9341_MAGENTA);
        tft.setTextColor(ILI9341_WHITE, ILI9341_BLACK);
        tft.setTextSize(1);
        tft.setCursor(18, 44);
        tft.print("STATUS DOS SERVICOS & DOCKER LOCAL");
        break;

      case MODE_CLOCK_WIDGET:
        tft.drawRoundRect(8, 32, 304, 202, 6, ILI9341_YELLOW);
        break;

      default: break;
    }
  }

  void updateServerStats(const ServerMetrics& srv) {
    tft.setTextSize(1);
    tft.setCursor(18, 44);
    tft.setTextColor(ILI9341_WHITE, ILI9341_BLACK);
    tft.print("Host: Servidor1");

    // Destaque Termico
    uint16_t tempCol = (srv.cpuTemp >= 75.0) ? ILI9341_RED : ((srv.cpuTemp >= 65.0) ? ILI9341_YELLOW : ILI9341_GREEN);
    tft.drawRoundRect(126, 38, 96, 18, 3, tempCol);
    tft.setTextColor(tempCol, ILI9341_BLACK);
    tft.setCursor(132, 43);
    tft.printf("Temp: %4.1f C", srv.cpuTemp);

    tft.setCursor(232, 44);
    if (srv.serverOnline) {
      tft.setTextColor(ILI9341_GREEN, ILI9341_BLACK);
      tft.print("[ ONLINE ]");
    } else {
      tft.setTextColor(ILI9341_RED, ILI9341_BLACK);
      tft.print("[ OFFLINE]");
    }

    // CPU
    drawBar(82, 70, 166, 7, srv.cpuUsage, ILI9341_GREEN, ILI9341_RED);
    tft.setTextSize(1);
    tft.setTextColor(ILI9341_WHITE, ILI9341_BLACK);
    tft.setCursor(256, 70);
    tft.printf("%5.1f%%", srv.cpuUsage);

    // RAM
    drawBar(82, 95, 166, 7, srv.ramUsage, ILI9341_CYAN, ILI9341_RED);
    tft.setCursor(256, 95);
    tft.printf("%5.1f%%", srv.ramUsage);

    // DISK
    drawBar(82, 120, 166, 7, srv.diskUsage, ILI9341_YELLOW, ILI9341_RED);
    tft.setCursor(256, 120);
    tft.printf("%5.1f%%", srv.diskUsage);

    // Rede RX / TX
    tft.setTextSize(2);
    tft.setTextColor(ILI9341_GREEN, ILI9341_BLACK);
    tft.setCursor(150, 158);
    tft.printf("%7.1f KB/s", srv.netRxKBps);

    tft.setTextColor(ILI9341_YELLOW, ILI9341_BLACK);
    tft.setCursor(150, 174);
    tft.printf("%7.1f KB/s", srv.netTxKBps);

    // Uptime
    uint32_t up = srv.uptimeSec;
    int dias = up / 86400;
    int horas = (up % 86400) / 3600;
    int mins = (up % 3600) / 60;
    tft.setTextSize(1);
    tft.setTextColor(ILI9341_LIGHTGREY, ILI9341_BLACK);
    tft.setCursor(215, 208);
    tft.printf("Up: %dd %02dh %02dm", dias, horas, mins);
  }

  void updateFieldStation(const FieldStationMetrics& st) {
    tft.setTextSize(1);
    tft.setCursor(230, 44);
    tft.setTextColor(st.stationOnline ? ILI9341_GREEN : ILI9341_RED, ILI9341_BLACK);
    tft.printf("[%s]", st.stationOnline ? "ONLINE " : "OFFLINE");

    // Temp
    tft.setTextSize(3);
    tft.setTextColor(ILI9341_WHITE, ILI9341_BLACK);
    tft.setCursor(30, 85);
    tft.printf("%5.1f C", st.temp);

    // Umid
    tft.setTextColor(ILI9341_CYAN, ILI9341_BLACK);
    tft.setCursor(178, 85);
    tft.printf("%5.1f %%", st.humidity);

    // Pressao
    tft.setTextColor(ILI9341_YELLOW, ILI9341_BLACK);
    tft.setCursor(24, 155);
    tft.printf("%6.1f hPa", st.pressure);

    // VPD
    tft.setTextColor(ILI9341_GREEN, ILI9341_BLACK);
    tft.setCursor(174, 155);
    tft.printf("%5.2f kPa", st.vpd);

    // Rodape
    tft.setTextSize(1);
    tft.setTextColor(ILI9341_LIGHTGREY, ILI9341_BLACK);
    tft.setCursor(210, 208);
    tft.printf("Envio: ha %3ds", st.secondsAgo);
  }

  void updateServicesStatus(const ServicesMetrics& s) {
    const char* names[4] = {"Gaia Server (:3000)", "Agroclima Server (:3001)", "PostgreSQL DB (:5432)", "Mosquitto MQTT (:1883)"};
    bool ok[4] = {s.serverApiOk, s.agroclimaOk, s.postgresOk, s.mosquittoOk};

    tft.setTextSize(1);
    for (int i = 0; i < 4; i++) {
      int y = 64 + (i * 34);
      tft.drawRoundRect(16, y, 288, 28, 4, ok[i] ? 0x2410 : 0x8000);
      tft.setTextColor(ILI9341_WHITE, ILI9341_BLACK);
      tft.setCursor(26, y + 10);
      tft.print(names[i]);

      tft.setCursor(226, y + 10);
      tft.setTextColor(ok[i] ? ILI9341_GREEN : ILI9341_RED, ILI9341_BLACK);
      tft.print(ok[i] ? "[ ATIVO ]" : "[OFFLINE]");
    }

    tft.setTextColor(ILI9341_CYAN, ILI9341_BLACK);
    tft.setCursor(18, 208);
    tft.printf("Latencia Local da LAN: ~%d ms", s.pingMs);
  }

  void updateClockWidget(const ServerMetrics& srv, const String& timeStr, const String& dateStr, const String& wifiSsid, const String& ipStr) {
    tft.setTextSize(5);
    tft.setTextColor(ILI9341_GREEN, ILI9341_BLACK);
    tft.setCursor(35, 55);
    tft.print(timeStr);

    tft.setTextSize(2);
    tft.setTextColor(ILI9341_WHITE, ILI9341_BLACK);
    tft.setCursor(35, 110);
    tft.print(dateStr);

    // Banner de Alerta / Status
    tft.setTextSize(1);
    if (srv.alertLevel == "critical") {
      tft.fillRect(16, 142, 288, 20, ILI9341_RED);
      tft.setTextColor(ILI9341_WHITE, ILI9341_RED);
      tft.setCursor(24, 148);
      tft.print("! ALERTA: " + srv.alertMsg);
    } else if (srv.alertLevel == "warning") {
      tft.fillRect(16, 142, 288, 20, 0x9B20);
      tft.setTextColor(ILI9341_WHITE, 0x9B20);
      tft.setCursor(24, 148);
      tft.print("! AVISO: " + srv.alertMsg);
    } else {
      uint16_t tempCol = (srv.cpuTemp > 65.0) ? ILI9341_YELLOW : ILI9341_GREEN;
      tft.setTextColor(tempCol, ILI9341_BLACK);
      tft.setCursor(20, 148);
      tft.printf("Servidor: %4.1f C  |  CPU: %4.1f%%  |  RAM: %4.1f%%", srv.cpuTemp, srv.cpuUsage, srv.ramUsage);
    }

    tft.setTextColor(ILI9341_YELLOW, ILI9341_BLACK);
    tft.setCursor(20, 178);
    tft.printf("WiFi: %-16s | IP: %s", wifiSsid.c_str(), ipStr.c_str());

    tft.setTextColor(ILI9341_CYAN, ILI9341_BLACK);
    tft.setCursor(20, 205);
    tft.print("Painel Vigil: http://192.168.0.105:5000");
  }

  void drawBar(int x, int y, int w, int h, float pct, uint16_t okColor, uint16_t alertColor) {
    if (pct < 0.0) pct = 0.0;
    if (pct > 100.0) pct = 100.0;

    int fillW = (int)((w * pct) / 100.0);
    uint16_t col = (pct > 85.0) ? alertColor : okColor;

    if (fillW > 0) {
      tft.fillRect(x, y, fillW, h, col);
    }
    if (w - fillW > 0) {
      tft.fillRect(x + fillW, y, w - fillW, h, ILI9341_BLACK);
    }
  }
};

#endif // DISPLAYUI_H
