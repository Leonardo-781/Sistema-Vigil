# 🛡️ Sistema Vigil

> **Ecossistema Inteligente de Observabilidade e Monitoramento Físico & Remoto**

O **Sistema Vigil** é uma solução completa e de baixo custo para monitoramento de infraestrutura, servidores (CPU, RAM, Disco, Rede e **Temperatura da CPU em tempo real**) e telemetria de dispositivos IoT/sensores externos.

O projeto é composto por dois elementos principais:
1. **Vigil Desk (Hardware de Mesa):** Aparelho físico de bancada baseado em **ESP32** com display TFT colorido de 2.8" e **Rotary Encoder** para alternância tátil e fluida de telas sem toques acidentais.
2. **Vigil Agent & Web (Servidor):** Agente ultraleve em Python que roda como serviço em segundo plano no servidor (Linux/Windows) e serve um painel web responsivo em tempo real e APIs REST para o dispositivo de mesa.

---

## 📸 Painel Web (Vigil Web)

Painel responsivo (*Dark Mode Glassmorphism*) com sincronização automática a cada 1.5s via AJAX:

- 🌡️ **Temperatura Térmica da CPU** com indicador dinâmico de cores (Verde < 60°C, Amarelo 60-75°C, Vermelho > 75°C);
- 📊 **Barras de Gradiente:** % de CPU, Memória RAM e Espaço em Disco SSD;
- ⚡ **Velocímetros de Rede:** Taxa real de Download (RX) e Upload (TX) em KB/s;
- 📡 **Monitor de Campo:** Temperatura, Umidade, VPD (Déficit de Pressão de Vapor) e Pressão Atmosférica de sensores remotos;
- 🌐 **Acesso Local ou Remoto:** Acessível na LAN (`http://IP_LOCAL:5000`) ou via **Cloudflare Tunnel** seguro (HTTPS) sem abrir portas no roteador.

---

## 🔌 Diagrama de Pinagem do Hardware (Vigil Desk)

O dispositivo utiliza a pinagem padrão do barramento SPI e interrupções GPIO do ESP32:

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
            |          GPIO 27 |<-----------| SW   (Botão integrado) |
            |              GND |----------->| GND                    |
            |              3V3 |----------->| +    (Pull-up / VCC)   |
            +------------------+            +------------------------+
```

### Tabela de Ligações

| Componente | Pino do Módulo | Pino ESP32 | Função |
| :--- | :--- | :--- | :--- |
| **Display TFT 2.8" (ILI9341)** | CS | GPIO 5 | Seleção do chip SPI |
| | DC / RS | GPIO 2 | Seleção de Comando / Dado |
| | RST | GPIO 4 | Linha de Reset |
| | MOSI / SDI | GPIO 23 | Linha de Dados SPI |
| | SCK / CLK | GPIO 18 | Linha de Clock SPI |
| | MISO / SDO | GPIO 19 | Linha de Leitura SPI |
| | VCC / LED | 3V3 / 5V | Alimentação e Backlight |
| **Rotary Encoder (EC11 / KY-040)** | CLK | GPIO 25 | Interrupção por descida (Rotação) |
| | DT | GPIO 26 | Detecção de direção (Horário / Anti-horário) |
| | SW | GPIO 27 | Botão de clique (Troca de Modo / Seleção) |
| | GND | GND | Terra comum |

---

## 📱 Modo AP (Troca Fácil de Rede Wi-Fi)

O Sistema Vigil conta com um **portal web embutido de configuração** gravado na memória Flash NVS (`Preferences`), eliminando a necessidade de regravar o firmware para mudar de Wi-Fi:

1. **Como Ativar:**
   - **No Boot:** Ligue a placa segurando o botão do Encoder por 1 segundo; **OU**
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
# 1. Instalar dependências (apenas psutil)
pip install psutil

# 2. Executar o agente
python server/server_agent.py
```

* O painel estará disponível em: `http://localhost:5000`
* A API JSON estará em: `http://localhost:5000/api/status`

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
   - `ArduinoJson` (v7 ou v6)
3. Selecione a placa **ESP32 Dev Module** e grave via USB;
4. Ao ligar pela primeira vez, configure seu Wi-Fi pelo portal **`Vigil-Setup`** ou edite os padrões no arquivo [`Config.h`](firmware/vigil_desk/Config.h).

---

## 🛠️ Tecnologias Utilizadas

- **Microcontrolador:** ESP32 Dual-Core (Wi-Fi 802.11 b/g/n, SPI Hardware).
- **Linguagens:** C++ (Arduino Framework), Python 3 (Backend/Agent), HTML5 / CSS3 / Vanilla JS (Dashboard Web).
- **Display Driver:** Adafruit_ILI9341 com buffer dinâmico anti-flicker.
- **Rede & Acesso Remoto:** HTTP REST, NTP.br (Sincronização atômica de relógio), Cloudflare Tunnels (HTTPS).

---

## 📄 Licença

Distribuído sob a licença MIT. Veja `LICENSE` para mais informações.
