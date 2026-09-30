# 🛡️ Sistema Vigil

> **Ecossistema Inteligente de Observabilidade, Controle DevOps e Media Hub Físico & Remoto**

O **Sistema Vigil** é uma solução completa para monitoramento de infraestrutura, servidores (CPU, RAM, Disco, Rede e **Temperatura da CPU em tempo real**), telemetria de dispositivos IoT/sensores externos, **Media Hub Spotify com capa de álbum** e **Deck Físico de Comandos DevOps**.

O projeto é composto por dois elementos principais:
1. **Vigil Desk (Hardware de Mesa Dual-Core):** Aparelho físico de bancada baseado em **ESP32 (Arquitetura FreeRTOS Dual-Core)** com display TFT colorido de 2.8" (SPI 40 MHz), **Rotary Encoder** (decodificador de quadratura de 16 estados em `IRAM_ATTR`) e **3 Botões Físicos Dedicados** para controle de mídia e execução de comandos remotos no servidor.
2. **Vigil Agent & Web (Servidor):** Agente ultraleve em Python que roda como serviço em segundo plano no servidor (Linux/Windows) e serve um painel web responsivo em tempo real, integração OAuth2 com Spotify e APIs REST de telemetria e ações DevOps para o dispositivo de mesa.

---

## 🖥️ Telas do Vigil Desk (6 Modos Interativos)

Gire o **Rotary Encoder** para navegar entre as 6 telas ou clique no botão do Encoder (`SW`) em telas interativas para travar o foco:

1. **Tela 1 — Telemetria do Servidor (`MODE_SERVER_STATS`):** Barras de uso de CPU, RAM, Disco SSD, temperatura térmica do processador (°C), tráfego de rede em tempo real (Download/Upload) e alertas.
2. **Tela 2 — Estação de Campo (`MODE_FIELD_STATION`):** Temperatura, umidade relativa, pressão atmosférica, VPD (Déficit de Pressão de Vapor) e ET0 da estação remota GAIA.
3. **Tela 3 — Status de Serviços Docker (`MODE_SERVICES_STATUS`):** Saúde em tempo real dos containers (`Gaia Server :3000`, `Agroclima :3001`, `PostgreSQL :5432`, `Mosquitto MQTT :1883`) e latência de rede (`ping ms`).
4. **Tela 4 — Spotify Media Hub (`MODE_SPOTIFY`):**
   - Exibe **capa do álbum 80x80 em cores reais** (decodificada via `TJpg_Decoder`), título da faixa, artista, álbum, barra de progresso e volume atual (`%`).
   - **Modo Volume (Foco do Encoder):** Clique no botão do Encoder (`GPIO 27`) na tela do Spotify para alternar entre navegar telas (`[ENC:TELA]`) e o modo **`ENC:VOL`**, onde girar o encoder ajusta o volume do Spotify de `0%` a `100%` em passos de `5%`.
   - **Botões Físicos Dedicados (`GPIO 32, 33, 14`):** Controlam `⏮ Anterior`, `⏯ Play/Pause` e `⏭ Próxima` de qualquer tela (exceto quando na tela de Comandos).
5. **Tela 5 — DevOps Command Deck (`MODE_COMMAND_DECK`):**
   - Deck físico de operações rápidas do servidor com 6 ações:
     1. `1. Restart Gaia Server (:3000)`
     2. `2. Restart Agroclima (:3001)`
     3. `3. Restart Mosquitto MQTT (:1883)`
     4. `4. Wake-on-LAN (Ligar PC na Rede)`
     5. `5. Sincronizar / Limpar Cache RAM`
     6. `6. Testar Tunel Publico HTTPS`
   - **Trava de Segurança (Safety Lock de 3s):** Navegue com `BTN1 (GPIO 32)` / `BTN3 (GPIO 14)` (ou travando o Encoder com `SW`). Pressionar `BTN2 (GPIO 33)` arma o comando selecionado em vermelho/amarelo (`[CONFIRME]`). Somente um segundo clique dentro de 3 segundos dispara o `POST /api/command` para o servidor e exibe o resultado na tela.
6. **Tela 6 — Relógio Digital NTP & Rede (`MODE_CLOCK_WIDGET`):** Relógio digital de mesa sincronizado via NTP (`pool.ntp.org`), data completa, RSSI do Wi-Fi e IP local.

---

## 📸 Painel Web (Vigil Web v2.5)

Painel responsivo (*Dark Mode Glassmorphism*) com sincronização automática a cada 1.5s via AJAX e suporte a PWA (Progressive Web App):

- 🌡️ **Temperatura Térmica da CPU** com indicador dinâmico de cores (Verde < 60°C, Amarelo 60-75°C, Vermelho > 75°C) e sparkline histórica;
- 📊 **Barras de Gradiente & Histórico:** % de CPU, Memória RAM e Espaço em Disco SSD com curvas ao vivo;
- ⚡ **DevOps Command Deck na Web:** Botões táteis com confirmação de segurança para executar ações no servidor (`Restart Gaia`, `Restart Agroclima`, `Restart Mosquitto`, `Wake-on-LAN`, `Limpar Buffers`, `Testar Túnel HTTPS`) com feedback de latência;
- 🎛️ **Controle de Volume do Spotify Deslizante:** Slider contínuo (`0% a 100%`) com ícones dinâmicos (`🔇`, `🔉`, `🔊`) sincronizado com o display físico do Vigil Desk;
- 📈 **Top 5 Processos em Tempo Real (Mini `htop`):** Tabela compacta com PID, nome do processo, micro-barra de CPU e consumo de memória RAM;
- 🌐 **Barra de Atalhos do Ecossistema:** Acesso direto a Gaia (`:3000`), Agroclima (`:3001`), Portainer (`:9000`), Adminer (`:8080`) e Túnel Tailscale;
- 📜 **Console / Drawer de Logs ao Vivo:** Gaveta retrátil na base da tela exibindo stream de eventos em tempo real (`[INFO]`, `[CMD]`, `[WARN]`, `[ALERT]`) com timestamps;
- ⚡ **Velocímetros de Rede:** Taxa real de Download (RX) e Upload (TX) em KB/s;
- 📡 **Telemetria de Campo:** Temperatura, umidade, VPD e pressão atmosférica da estação GAIA remota;
- 📱 **Modo PWA:** Suporte a "Adicionar à tela de início" no Android/iOS para rodar como aplicativo em tela cheia.

---

## 🔌 Diagrama de Pinagem do Hardware (Vigil Desk)

O dispositivo utiliza o barramento SPI de hardware (40 MHz), interrupções GPIO para o Encoder e 3 botões físicos com `INPUT_PULLUP` interno:

```
               +--------------------------------------------+
               |        PINAGEM DE CONEXÃO DO HARDWARE      |
               +--------------------------------------------+

               ESP32 DevKit                  Display TFT 2.8" ILI9341
            +------------------+            +------------------------+
            |                  |            |                        |
            |           GPIO 5 |----------->| CS   (Chip Select)     |
            |           GPIO 2 |----------->| DC   (Data/Command)    |
            |           GPIO 4 |----------->| RST  (Reset)           |
            |          GPIO 23 |----------->| MOSI (SPI Data)        |
            |          GPIO 18 |----------->| SCK  (SPI Clock)       |
            |          GPIO 19 |<-----------| MISO (SPI Retorno)     |
            |          GPIO 15 |----------->| SD_CS (Opcional Leitor)|
            |          3V3 / 5V|----------->| VCC / LED              |
            |              GND |----------->| GND                    |
            |                  |            +------------------------+
            |                  |
            |                  |             Rotary Encoder EC11
            |                  |            +------------------------+
            |          GPIO 25 |<-----------| CLK  (Phase A)         |
            |          GPIO 26 |<-----------| DT   (Phase B)         |
            |          GPIO 27 |<-----------| SW   (Foco / Seleção)  |
            |              GND |----------->| GND                    |
            |              3V3 |----------->| +    (Pull-up / VCC)   |
            |                  |            +------------------------+
            |                  |
            |                  |             Deck de 3 Botões Físicos
            |                  |            +------------------------+
            |          GPIO 32 |<-----------| BTN 1 (Prev / ▲ Cmd)   |
            |          GPIO 33 |<-----------| BTN 2 (Play / ⚡ Exec)  |
            |          GPIO 14 |<-----------| BTN 3 (Next / ▼ Cmd)   |
            |              GND |----------->| GND Comum dos 3 Botões |
            +------------------+            +------------------------+
```

### Tabela de Ligações

| Componente | Pino do Módulo | Pino ESP32 | Função |
| :--- | :--- | :--- | :--- |
| **Display TFT 2.8" (ILI9341)** | CS | GPIO 5 | Seleção do chip SPI |
| | DC / RS | GPIO 2 | Seleção de Comando / Dado |
| | RST | GPIO 4 | Linha de Reset |
| | MOSI / SDI | GPIO 23 | Linha de Dados SPI |
| | SCK / CLK | GPIO 18 | Linha de Clock SPI (40 MHz) |
| | MISO / SDO | GPIO 19 | Linha de Leitura SPI |
| | VCC / LED | 3V3 / 5V | Alimentação e Backlight |
| **Rotary Encoder (EC11 / KY-040)** | CLK | GPIO 25 | Interrupção quadratura (`CHANGE`) |
| | DT | GPIO 26 | Interrupção quadratura (`CHANGE`) |
| | SW | GPIO 27 | Botão de clique (Trava Volume / Comando) |
| | GND | GND | Terra comum |
| **Deck de Botões Táteis (Push Buttons)** | BTN 1 (`PREV`) | GPIO 32 | Faixa Anterior (`⏮`) / Subir Comando (`▲`) |
| | BTN 2 (`PLAY/EXEC`) | GPIO 33 | Play/Pause (`⏯`) / Confirmar Comando (`⚡`) |
| | BTN 3 (`NEXT`) | GPIO 14 | Próxima Faixa (`⏭`) / Descer Comando (`▼`) |
| | Terminal 2 | GND | Conectado ao GND (usa `INPUT_PULLUP` interno) |

---

## 📱 Modo AP (Troca Fácil de Rede Wi-Fi)

O Sistema Vigil conta com um **portal web embutido de configuração** gravado na memória Flash NVS (`Preferences`), eliminando a necessidade de regravar o firmware para mudar de Wi-Fi:

1. **Como Ativar:**
   - **No Boot:** Ligue a placa segurando o botão do Encoder (`GPIO 27`) por 1 segundo; **OU**
   - **Automático:** Se o aparelho for levado para outro local e a rede antiga não existir, ele ativa o modo AP automaticamente após 7 segundos.
2. **Configuração pelo Celular:**
   - Conecte no Wi-Fi gerado: **`Vigil-Setup`** (rede aberta);
   - Abra o navegador em **`http://192.168.4.1`**;
   - Insira o nome (SSID) da nova rede, a senha e a URL do servidor;
   - Clique em **Salvar e Conectar** — o dispositivo reinicia imediatamente conectado na nova rede.

---

## 🚀 Como Executar o Projeto

### 1. Servidor (Vigil Agent)
No seu servidor Linux (Ubuntu, Debian, Raspberry Pi) ou Windows:

```bash
# 1. Instalar dependências
pip install psutil pillow

# 2. Executar o agente
python server/server_agent.py
```

* O painel estará disponível em: `http://localhost:5000`
* A API JSON estará em: `http://localhost:5000/api/status`
* Endpoints de controle: `POST /api/spotify/<play|pause|next|prev|volume>` e `POST /api/cmd/<comando>`

#### (Opcional) Configurar Integração Spotify:
Crie um arquivo `spotify_config.json` no mesmo diretório do `server_agent.py` (nunca versionado no Git) contendo:
```json
{
  "client_id": "SEU_SPOTIFY_CLIENT_ID",
  "client_secret": "SEU_SPOTIFY_CLIENT_SECRET",
  "refresh_token": "SEU_SPOTIFY_REFRESH_TOKEN"
}
```

#### (Opcional) Executar como serviço permanente no Linux (systemd):
```bash
sudo cp server/server_agent.py /opt/vigil/
sudo cp server/vigil-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vigil-agent
```

### 2. Dispositivo de Mesa (Vigil Desk)
1. Abra a pasta `firmware/vigil_desk` no **Arduino IDE** ou **VS Code**;
2. Instale as bibliotecas necessárias pelo Gerenciador de Bibliotecas:
   - `Adafruit ILI9341`
   - `Adafruit GFX Library`
   - `ArduinoJson`
   - `TJpg_Decoder` (para renderização da capa do álbum do Spotify)
3. Selecione a placa **ESP32 Dev Module** e o esquema de partição **`Huge APP (3MB No OTA/1MB SPIFFS)`** (`esp32:esp32:esp32:PartitionScheme=huge_app`);
4. Grave via USB e configure seu Wi-Fi pelo portal **`Vigil-Setup`** ou edite os padrões no arquivo [`Config.h`](firmware/vigil_desk/Config.h).

---

## 🛠️ Arquitetura Dual-Core & Tecnologias Utilizadas

- **Microcontrolador:** ESP32 Dual-Core com separação estrita de tarefas FreeRTOS:
  - **Core 0 (`VigilNetTask`):** Gerencia conexões HTTP/HTTPS, handshake TLS, download de capas JPEG, envio de comandos Spotify/DevOps e consulta meteorológica sem bloquear a interface.
  - **Core 1 (`loop()` a 200 Hz):** Dedicado exclusivamente à leitura instantânea do Rotary Encoder, debounce dos 3 botões físicos e renderização gráfica a 40 MHz SPI.
- **Linguagens:** C++ (Arduino / FreeRTOS), Python 3 (Backend/Agent), HTML5 / CSS3 / Vanilla JS (Dashboard Web).
- **Display Driver:** `Adafruit_ILI9341` + `TJpg_Decoder` com renderização incremental anti-flicker.

---

---

## 📘 Documentação Técnica Detalhada

Para consultar a arquitetura interna completa (FreeRTOS Dual-Core, protocolo Safety Lock de 3s, matriz de quadratura do Encoder, referência de rotas da API REST e processamento de capas JPEG), acesse o documento completo:

👉 **[`DOCUMENTACAO.md` — Documentação Técnica Completa do Sistema Vigil](DOCUMENTACAO.md)**

---

## 📄 Licença

Distribuído sob a licença MIT. Veja `LICENSE` para mais informações.
