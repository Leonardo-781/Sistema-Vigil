/*
 * ============================================================================
 * SISTEMA VIGIL - VIGIL DESK DASHBOARD (DisplayUI.h)
 * ============================================================================
 * Renderizacao Ultra-Rapida (SPI 40MHz + Anti-flicker) para ILI9341 320x240.
 * Inclui Tela 4 (Spotify + Volume Encoder) e Tela 5 (DevOps Command Deck).
 * ============================================================================
 */

#ifndef DISPLAYUI_H
#define DISPLAYUI_H

#include <Arduino.h>
#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ILI9341.h>
#include <TJpg_Decoder.h>
#include "Config.h"

#define COLOR_SPOTIFY_GREEN 0x1DCA
#define COLOR_DARK_CARD     0x10A2
#define COLOR_DECK_ORANGE   0xFD20

static Adafruit_ILI9341* g_tft_ptr = nullptr;

inline bool vigil_tft_output(int16_t x, int16_t y, uint16_t w, uint16_t h, uint16_t* bitmap) {
  if (!g_tft_ptr) return false;
  if (y >= g_tft_ptr->height()) return false;
  g_tft_ptr->drawRGBBitmap(x, y, bitmap, w, h);
  return true;
}

inline String cleanAscii(const String& in) {
  String s = in;
  s.replace("á", "a"); s.replace("à", "a"); s.replace("ã", "a"); s.replace("â", "a");
  s.replace("Á", "A"); s.replace("À", "A"); s.replace("Ã", "A"); s.replace("Â", "A");
  s.replace("é", "e"); s.replace("ê", "e"); s.replace("É", "E"); s.replace("Ê", "E");
  s.replace("í", "i"); s.replace("Í", "I");
  s.replace("ó", "o"); s.replace("õ", "o"); s.replace("ô", "o");
  s.replace("Ó", "O"); s.replace("Õ", "O"); s.replace("Ô", "O");
  s.replace("ú", "u"); s.replace("ü", "u"); s.replace("Ú", "U");
  s.replace("ç", "c"); s.replace("Ç", "C");
  s.replace("ñ", "n"); s.replace("Ñ", "N");
  String out = "";
  for (unsigned int i = 0; i < s.length(); i++) {
    uint8_t c = (uint8_t)s[i];
    if (c >= 32 && c <= 126) out += (char)c;
  }
  return out;
}

class DisplayUI {
private:
  Adafruit_ILI9341 tft;
  ScreenMode currentMode = MODE_SERVER_STATS;
  bool needFullRedraw = true;
  bool spotifyVolumeLocked = false; // Quando true na tela Spotify, girar o encoder controla o volume!
  String lastAlertLevel = "normal";
  String lastRenderedTrack = "";
  String lastRenderedArtId = "";
  int lastDeckSelected = -1;
  bool lastDeckConfirm = false;
  String lastDeckMsg = "";

public:
  DisplayUI() : tft(TFT_CS, TFT_DC, TFT_RST) {}

  void begin() {
    g_tft_ptr = &tft;
    SPI.begin(18, 19, 23, TFT_CS);
    tft.begin(40000000); // SPI em 40 MHz
    tft.setRotation(1);  // Paisagem (320x240)
    tft.fillScreen(ILI9341_BLACK);

    TJpgDec.setJpgScale(1);
    TJpgDec.setCallback(vigil_tft_output);

    needFullRedraw = true;
  }

  ScreenMode getMode() const { return currentMode; }
  bool isSpotifyVolumeLocked() const { return spotifyVolumeLocked; }
  void toggleSpotifyVolumeLock() { spotifyVolumeLocked = !spotifyVolumeLocked; }
  void setSpotifyVolumeLock(bool v) { spotifyVolumeLocked = v; }

  void forceRedraw() { needFullRedraw = true; }

  void nextMode() {
    spotifyVolumeLocked = false;
    currentMode = static_cast<ScreenMode>((currentMode + 1) % NUM_MODES);
    needFullRedraw = true;
  }

  void prevMode() {
    spotifyVolumeLocked = false;
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

  void showSpotifyToast(const String& msg) {
    tft.fillRoundRect(40, 206, 240, 20, 4, COLOR_SPOTIFY_GREEN);
    tft.setTextColor(ILI9341_BLACK, COLOR_SPOTIFY_GREEN);
    tft.setTextSize(1);
    tft.setCursor(52, 212);
    tft.print(msg);
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

  void render(const ServerMetrics& srv, const FieldStationMetrics& st, const ServicesMetrics& srvc,
              const SpotifyMetrics& sp, const CommandDeckState& deck,
              const uint8_t* artBuf, size_t artLen,
              const String& timeStr, const String& dateStr, const String& wifiSsid, const String& ipStr) {
    if (srv.alertLevel != lastAlertLevel) {
      lastAlertLevel = srv.alertLevel;
      needFullRedraw = true;
    }

    if (needFullRedraw) {
      tft.fillScreen(ILI9341_BLACK);
      renderHeader(srv);
      renderStaticLayout();
      lastRenderedTrack = "";
      lastRenderedArtId = "";
      lastDeckSelected = -1;
      lastDeckMsg = "";
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
      case MODE_SPOTIFY:
        updateSpotifyScreen(sp, artBuf, artLen);
        break;
      case MODE_COMMAND_DECK:
        updateCommandDeck(deck);
        break;
      case MODE_CLOCK_WIDGET:
        updateClockWidget(srv, sp, timeStr, dateStr, wifiSsid, ipStr);
        break;
      default:
        break;
    }
  }

private:
  void renderHeader(const ServerMetrics& srv) {
    bool isCrit = (srv.alertLevel == "critical" || srv.cpuTemp >= 75.0);
    bool isWarn = (srv.alertLevel == "warning" || srv.cpuTemp >= 65.0);

    uint16_t bg = isCrit ? ILI9341_RED : (isWarn ? 0x9B20 : (currentMode == MODE_SPOTIFY ? 0x0B88 : (currentMode == MODE_COMMAND_DECK ? 0x3906 : ILI9341_NAVY)));
    uint16_t border = isCrit ? ILI9341_MAROON : (isWarn ? ILI9341_YELLOW : (currentMode == MODE_SPOTIFY ? COLOR_SPOTIFY_GREEN : (currentMode == MODE_COMMAND_DECK ? COLOR_DECK_ORANGE : ILI9341_BLUE)));

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
        case MODE_SPOTIFY:        tft.print("VIGIL // SPOTIFY"); break;
        case MODE_COMMAND_DECK:   tft.print("VIGIL // COMANDOS"); break;
        case MODE_CLOCK_WIDGET:   tft.print("VIGIL // DESK CLOCK"); break;
        default: break;
      }
    }

    for (int i = 0; i < NUM_MODES; i++) {
      uint16_t color = (i == currentMode) ? (isCrit ? ILI9341_WHITE : ILI9341_YELLOW) : ILI9341_DARKGREY;
      tft.fillCircle(248 + (i * 11), 13, 3, color);
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

        tft.setTextColor(ILI9341_DARKGREY, ILI9341_BLACK);
        tft.setCursor(16, 208);
        tft.print("Botoes: [Prev] [Play] [Next] | Gire: Telas");
        break;

      case MODE_FIELD_STATION:
        tft.drawRoundRect(8, 32, 304, 202, 6, ILI9341_GREEN);
        tft.setTextColor(ILI9341_LIGHTGREY, ILI9341_BLACK);
        tft.setTextSize(1);
        tft.setCursor(18, 44);
        tft.print("MONITOR DE TELEMETRIA G00001 (Monte Carmelo)");

        tft.drawRoundRect(16, 60, 140, 64, 4, ILI9341_DARKGREY);
        tft.drawRoundRect(164, 60, 140, 64, 4, ILI9341_DARKGREY);
        tft.drawRoundRect(16, 130, 140, 64, 4, ILI9341_DARKGREY);
        tft.drawRoundRect(164, 130, 140, 64, 4, ILI9341_DARKGREY);

        tft.setCursor(24, 66);  tft.print("TEMPERATURA");
        tft.setCursor(172, 66); tft.print("UMIDADE RELATIVA");
        tft.setCursor(24, 136); tft.print("PRESSAO ATM.");
        tft.setCursor(172, 136);tft.print("DEFICIT VAPOR (VPD)");

        tft.setTextColor(ILI9341_DARKGREY, ILI9341_BLACK);
        tft.setCursor(16, 208);
        tft.print("Ultimo pacote recebido via WiFi/HTTPS");
        break;

      case MODE_SERVICES_STATUS:
        tft.drawRoundRect(8, 32, 304, 202, 6, ILI9341_MAGENTA);
        tft.setTextColor(ILI9341_WHITE, ILI9341_BLACK);
        tft.setTextSize(1);
        tft.setCursor(18, 44);
        tft.print("STATUS DOS SERVICOS & DOCKER LOCAL");
        break;

      case MODE_SPOTIFY:
        tft.drawRoundRect(8, 32, 304, 202, 6, COLOR_SPOTIFY_GREEN);
        tft.drawRect(17, 45, 82, 82, COLOR_SPOTIFY_GREEN);
        // Barra de Progresso da Faixa
        tft.drawRect(18, 138, 284, 9, ILI9341_DARKGREY);
        // Barra de Volume
        tft.setTextColor(ILI9341_LIGHTGREY, ILI9341_BLACK);
        tft.setTextSize(1);
        tft.setCursor(18, 174);
        tft.print("VOL:");
        tft.drawRect(48, 173, 130, 9, ILI9341_DARKGREY);
        tft.drawFastHLine(16, 194, 288, ILI9341_DARKGREY);
        break;

      case MODE_COMMAND_DECK:
        tft.drawRoundRect(8, 32, 304, 202, 6, COLOR_DECK_ORANGE);
        tft.setTextColor(COLOR_DECK_ORANGE, ILI9341_BLACK);
        tft.setTextSize(1);
        tft.setCursor(18, 40);
        tft.print("DEVOPS COMMAND DECK (CONTROLE DE SERVIDOR)");
        tft.drawFastHLine(16, 196, 288, ILI9341_DARKGREY);
        break;

      case MODE_CLOCK_WIDGET:
        tft.drawRoundRect(8, 32, 304, 202, 6, ILI9341_YELLOW);
        break;

      default: break;
    }
  }

  void drawVinylPlaceholder() {
    tft.fillRect(18, 46, 80, 80, COLOR_DARK_CARD);
    tft.drawCircle(58, 86, 30, COLOR_SPOTIFY_GREEN);
    tft.drawCircle(58, 86, 20, ILI9341_DARKGREY);
    tft.fillCircle(58, 86, 8, COLOR_SPOTIFY_GREEN);
    tft.fillCircle(58, 86, 3, ILI9341_BLACK);
  }

  void updateSpotifyScreen(const SpotifyMetrics& sp, const uint8_t* artBuf, size_t artLen) {
    if (sp.artValid && artBuf != nullptr && artLen > 64) {
      if (sp.artId != lastRenderedArtId) {
        TJpgDec.drawJpg(18, 46, artBuf, artLen);
        lastRenderedArtId = sp.artId;
      }
    } else if (lastRenderedArtId != "__none__") {
      drawVinylPlaceholder();
      lastRenderedArtId = "__none__";
    }

    tft.setTextSize(1);
    tft.setCursor(108, 46);
    if (sp.isPlaying) {
      tft.setTextColor(COLOR_SPOTIFY_GREEN, ILI9341_BLACK);
      tft.print("[ > TOCANDO AGORA ]    ");
    } else if (sp.active) {
      tft.setTextColor(ILI9341_YELLOW, ILI9341_BLACK);
      tft.print("[ || PAUSADO ]         ");
    } else {
      tft.setTextColor(ILI9341_DARKGREY, ILI9341_BLACK);
      tft.print("[ SPOTIFY OCIOSO ]     ");
    }

    String cleanTrack = cleanAscii(sp.trackName);
    String cleanArtist = cleanAscii(sp.artistName);
    String cleanAlbum = cleanAscii(sp.albumName);
    String combinedKey = cleanTrack + "|" + cleanArtist;

    if (combinedKey != lastRenderedTrack) {
      lastRenderedTrack = combinedKey;
      tft.fillRect(108, 60, 198, 66, ILI9341_BLACK);

      tft.setTextColor(ILI9341_WHITE, ILI9341_BLACK);
      if (cleanTrack.length() <= 15) {
        tft.setTextSize(2);
        tft.setCursor(108, 62);
        tft.print(cleanTrack);
      } else {
        tft.setTextSize(1);
        tft.setCursor(108, 62);
        tft.print(cleanTrack.substring(0, 30));
        if (cleanTrack.length() > 30) {
          tft.setCursor(108, 74);
          tft.print(cleanTrack.substring(30, 58));
        }
      }

      tft.setTextSize(1);
      tft.setTextColor(COLOR_SPOTIFY_GREEN, ILI9341_BLACK);
      tft.setCursor(108, 92);
      tft.print(cleanArtist.substring(0, 30));

      tft.setTextColor(ILI9341_LIGHTGREY, ILI9341_BLACK);
      tft.setCursor(108, 108);
      tft.print(cleanAlbum.substring(0, 30));
    }

    // Barra de Progresso
    float pct = (sp.durationMs > 0) ? ((float)sp.progressMs * 100.0f / (float)sp.durationMs) : 0.0f;
    drawBar(19, 139, 282, 7, pct, COLOR_SPOTIFY_GREEN, COLOR_SPOTIFY_GREEN);

    uint32_t curSec = sp.progressMs / 1000;
    uint32_t totSec = sp.durationMs / 1000;
    tft.setTextSize(1);
    tft.setTextColor(ILI9341_WHITE, ILI9341_BLACK);
    tft.setCursor(18, 152);
    tft.printf("%02u:%02u", curSec / 60, curSec % 60);
    tft.setCursor(268, 152);
    tft.printf("%02u:%02u", totSec / 60, totSec % 60);

    // Barra de Volume + Indicador de Foco do Encoder (Volume vs Telas)
    drawBar(49, 174, 128, 7, (float)sp.volumePct, spotifyVolumeLocked ? ILI9341_YELLOW : COLOR_SPOTIFY_GREEN, ILI9341_RED);
    tft.setTextColor(ILI9341_WHITE, ILI9341_BLACK);
    tft.setCursor(182, 174);
    tft.printf("%3d%%", sp.volumePct);

    tft.setCursor(216, 174);
    if (spotifyVolumeLocked) {
      tft.setTextColor(ILI9341_BLACK, ILI9341_YELLOW);
      tft.print(" ENC:VOL ");
    } else {
      tft.setTextColor(ILI9341_LIGHTGREY, ILI9341_BLACK);
      tft.print("[ENC:TELA]");
    }

    tft.setTextColor(ILI9341_LIGHTGREY, ILI9341_BLACK);
    tft.setCursor(18, 202);
    if (spotifyVolumeLocked) {
      tft.print("Gire: Volume +/- 5% | Clique Enc: Destravar ");
    } else {
      tft.print("Clique Enc: Ajustar Volume | Botoes: Midia  ");
    }
  }

  void updateCommandDeck(const CommandDeckState& deck) {
    static const char* CMD_LABELS[NUM_DECK_COMMANDS] = {
      "1. Restart Gaia Server (:3000)",
      "2. Restart Agroclima (:3001)",
      "3. Restart Mosquitto MQTT (:1883)",
      "4. Wake-on-LAN (Ligar PC na Rede)",
      "5. Sincronizar / Limpar Cache RAM",
      "6. Testar Tunel Publico HTTPS"
    };

    if (deck.selectedIndex != lastDeckSelected || deck.confirmPending != lastDeckConfirm) {
      lastDeckSelected = deck.selectedIndex;
      lastDeckConfirm = deck.confirmPending;

      for (int i = 0; i < NUM_DECK_COMMANDS; i++) {
        int y = 54 + (i * 23);
        bool isSel = (i == deck.selectedIndex);
        uint16_t bg = isSel ? (deck.confirmPending ? ILI9341_RED : 0x194A) : ILI9341_BLACK;
        uint16_t border = isSel ? (deck.confirmPending ? ILI9341_YELLOW : ILI9341_CYAN) : ILI9341_DARKGREY;

        tft.fillRoundRect(16, y, 288, 20, 4, bg);
        tft.drawRoundRect(16, y, 288, 20, 4, border);

        tft.setTextSize(1);
        tft.setTextColor(isSel ? ILI9341_WHITE : ILI9341_LIGHTGREY, bg);
        tft.setCursor(24, y + 6);
        tft.print(CMD_LABELS[i]);

        if (isSel) {
          tft.setCursor(246, y + 6);
          tft.setTextColor( ILI9341_YELLOW, bg);
          tft.print(deck.confirmPending ? "[CONFIRME]" : "  < SEL > ");
        }
      }
    }

    if (deck.lastStatusMsg != lastDeckMsg) {
      lastDeckMsg = deck.lastStatusMsg;
      tft.fillRect(16, 200, 288, 26, ILI9341_BLACK);
      tft.setTextSize(1);
      tft.setTextColor(deck.confirmPending ? ILI9341_YELLOW : ILI9341_GREEN, ILI9341_BLACK);
      tft.setCursor(18, 203);
      tft.print(cleanAscii(deck.lastStatusMsg).substring(0, 46));

      tft.setTextColor(ILI9341_DARKGREY, ILI9341_BLACK);
      tft.setCursor(18, 215);
      if (deck.encoderNavLock) {
        tft.print("[ENC: MENU] Gire p/ escolher | Clique: Executar");
      } else {
        tft.print("Clique Enc ou Botoes [Prev/Next] p/ escolher");
      }
    }
  }

  void updateServerStats(const ServerMetrics& srv) {
    tft.setTextSize(1);
    tft.setCursor(18, 44);
    tft.setTextColor(ILI9341_WHITE, ILI9341_BLACK);
    tft.print("Host: Servidor1");

    uint16_t tempCol = (srv.cpuTemp >= 75.0) ? ILI9341_RED : ((srv.cpuTemp >= 65.0) ? ILI9341_YELLOW : ILI9341_GREEN);
    tft.drawRoundRect(126, 38, 96, 18, 3, tempCol);
    tft.setTextColor(tempCol, ILI9341_BLACK);
    tft.setCursor(132, 43);
    tft.printf("Temp: %4.1f C", srv.cpuTemp);

    tft.setCursor(232, 44);
    if (srv.serverOnline) {
      tft.setTextColor(ILI9341_GREEN, ILI9341_BLACK);
      tft.print("[ONLINE] ");
    } else {
      tft.setTextColor(ILI9341_RED, ILI9341_BLACK);
      tft.print("[OFFLINE]");
    }

    drawBar(81, 69, 168, 9, srv.cpuUsage, ILI9341_CYAN, ILI9341_RED);
    tft.setTextColor(ILI9341_WHITE, ILI9341_BLACK);
    tft.setCursor(256, 70);
    tft.printf("%5.1f%%", srv.cpuUsage);

    drawBar(81, 94, 168, 9, srv.ramUsage, ILI9341_MAGENTA, ILI9341_RED);
    tft.setTextColor(ILI9341_WHITE, ILI9341_BLACK);
    tft.setCursor(256, 95);
    tft.printf("%5.1f%%", srv.ramUsage);

    drawBar(81, 119, 168, 9, srv.diskUsage, ILI9341_YELLOW, ILI9341_RED);
    tft.setTextColor(ILI9341_WHITE, ILI9341_BLACK);
    tft.setCursor(256, 120);
    tft.printf("%5.1f%%", srv.diskUsage);

    tft.setTextColor(ILI9341_WHITE, ILI9341_BLACK);
    tft.setCursor(120, 161);
    tft.printf("%7.1f KB/s   ", srv.netRxKBps);
    tft.setCursor(120, 176);
    tft.printf("%7.1f KB/s   ", srv.netTxKBps);

    uint32_t d = srv.uptimeSec / 86400;
    uint32_t h = (srv.uptimeSec % 86400) / 3600;
    uint32_t m = (srv.uptimeSec % 3600) / 60;
    tft.setTextColor(ILI9341_LIGHTGREY, ILI9341_BLACK);
    tft.setCursor(210, 208);
    tft.printf("Up: %ud %02uh %02um", d, h, m);
  }

  void updateFieldStation(const FieldStationMetrics& st) {
    tft.setTextSize(2);
    tft.setTextColor(ILI9341_CYAN, ILI9341_BLACK);
    tft.setCursor(28, 84);
    tft.printf("%5.1f C ", st.temp);

    tft.setTextColor(ILI9341_GREEN, ILI9341_BLACK);
    tft.setCursor(176, 84);
    tft.printf("%5.1f %% ", st.humidity);

    tft.setTextColor(ILI9341_YELLOW, ILI9341_BLACK);
    tft.setCursor(24, 154);
    tft.printf("%6.1f hPa", st.pressure);

    tft.setTextColor(ILI9341_MAGENTA, ILI9341_BLACK);
    tft.setCursor(176, 154);
    tft.printf("%5.2f kPa", st.vpd);

    tft.setTextSize(1);
    tft.setCursor(220, 208);
    if (st.stationOnline) {
      tft.setTextColor(ILI9341_GREEN, ILI9341_BLACK);
      tft.printf("Ha %4d seg ", st.secondsAgo);
    } else {
      tft.setTextColor(ILI9341_RED, ILI9341_BLACK);
      tft.print("SEM SINAL   ");
    }
  }

  void updateServicesStatus(const ServicesMetrics& s) {
    struct Row { const char* name; bool ok; int y; };
    Row rows[4] = {
      {"1. Gaia Server (:3000)",      s.serverApiOk, 70},
      {"2. Agroclima Web (:3001)",    s.agroclimaOk, 102},
      {"3. PostgreSQL DB (:5432)",    s.postgresOk,  134},
      {"4. Mosquitto MQTT (:1883)",   s.mosquittoOk, 166}
    };

    for (int i = 0; i < 4; i++) {
      tft.drawRoundRect(18, rows[i].y - 6, 284, 24, 4, ILI9341_DARKGREY);
      tft.setTextSize(1);
      tft.setTextColor(ILI9341_WHITE, ILI9341_BLACK);
      tft.setCursor(28, rows[i].y + 2);
      tft.print(rows[i].name);

      tft.setCursor(235, rows[i].y + 2);
      if (rows[i].ok) {
        tft.setTextColor(ILI9341_GREEN, ILI9341_BLACK);
        tft.print("[ ATIVO ] ");
      } else {
        tft.setTextColor(ILI9341_RED, ILI9341_BLACK);
        tft.print("[OFFLINE] ");
      }
    }

    tft.setTextColor(ILI9341_CYAN, ILI9341_BLACK);
    tft.setCursor(20, 206);
    tft.printf("Latencia da Rede: ~%d ms   ", s.pingMs);
  }

  void updateClockWidget(const ServerMetrics& srv, const SpotifyMetrics& sp, const String& timeStr, const String& dateStr, const String& wifiSsid, const String& ipStr) {
    tft.setTextSize(5);
    tft.setTextColor(ILI9341_GREEN, ILI9341_BLACK);
    tft.setCursor(35, 50);
    tft.print(timeStr);

    tft.setTextSize(2);
    tft.setTextColor(ILI9341_WHITE, ILI9341_BLACK);
    tft.setCursor(35, 102);
    tft.print(dateStr);

    tft.setTextSize(1);
    if (srv.alertLevel == "critical") {
      tft.fillRect(16, 132, 288, 20, ILI9341_RED);
      tft.setTextColor(ILI9341_WHITE, ILI9341_RED);
      tft.setCursor(24, 138);
      tft.print("! ALERTA: " + srv.alertMsg);
    } else {
      uint16_t tempCol = (srv.cpuTemp > 65.0) ? ILI9341_YELLOW : ILI9341_GREEN;
      tft.setTextColor(tempCol, ILI9341_BLACK);
      tft.setCursor(20, 138);
      tft.printf("Servidor: %4.1f C  |  CPU: %4.1f%%  |  RAM: %4.1f%%", srv.cpuTemp, srv.cpuUsage, srv.ramUsage);
    }

    tft.setCursor(20, 162);
    if (sp.isPlaying) {
      tft.setTextColor(COLOR_SPOTIFY_GREEN, ILI9341_BLACK);
      String miniSp = "Spotify: " + cleanAscii(sp.trackName) + " - " + cleanAscii(sp.artistName);
      tft.printf("%-46s", miniSp.substring(0, 46).c_str());
    } else {
      tft.setTextColor(ILI9341_DARKGREY, ILI9341_BLACK);
      tft.print("Spotify: Pausado / Ocioso                     ");
    }

    tft.setTextColor(ILI9341_YELLOW, ILI9341_BLACK);
    tft.setCursor(20, 184);
    tft.printf("WiFi: %-16s | IP: %s", wifiSsid.c_str(), ipStr.c_str());

    tft.setTextColor(ILI9341_CYAN, ILI9341_BLACK);
    tft.setCursor(20, 206);
    tft.print("Vigil Web: server1.taila7d06b.ts.net:10000");
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
