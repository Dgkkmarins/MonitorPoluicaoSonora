# Monitor de Poluição Sonora — Entrega 4/5

Arquitetura (igual ao diagrama da Entrega 4):

```
Sensor de som --> ESP8266 --> Wi-Fi --> Python (gateway.py) --> ThingSpeak (Cloud) --> Dashboard (dashboard.py)
                                              |
                                              v
                                     SQLite local (monitor.db)
```

## 1. ThingSpeak (Cloud)

1. Crie uma conta em https://thingspeak.com e um novo **Channel**.
2. Adicione 3 fields: `field1` (valor bruto do sensor), `field2` (decibéis), `field3` (nível, código numérico).
3. Copie a **Write API Key** e a **Read API Key** e o **Channel ID** (aba "API Keys").

## 2. Gateway Python (`python/gateway.py`)

1. `pip install -r python/requirements.txt`
2. Edite `THINGSPEAK_WRITE_API_KEY` em `gateway.py`.
3. Rode: `python gateway.py` — ele sobe um servidor Flask em `http://0.0.0.0:5000`.
4. Descubra o IP da sua máquina na rede local (Windows: `ipconfig`, veja "IPv4 Address").

## 3. ESP8266 (`esp8266/monitor_poluicao_sonora.ino`)

1. Instale as libs no Arduino IDE: `ArduinoJson` (via Library Manager).
2. Edite `WIFI_SSID`, `WIFI_SENHA` e `SERVIDOR_URL` (use o IP do passo 2, ex: `http://192.168.0.10:5000/dados`).
3. Grave no ESP8266 e abra o Serial Monitor (115200) para conferir os envios.

## 4. Dashboard (`python/dashboard.py`)

1. Edite `THINGSPEAK_CHANNEL_ID` e `THINGSPEAK_READ_API_KEY`.
2. Rode: `streamlit run python/dashboard.py`
3. Abre no navegador (`localhost:8501`) e atualiza sozinho a cada 3s.

## Evidência de dados chegando na nuvem

Depois do gateway rodando e o ESP enviando, acesse:
`https://thingspeak.com/channels/<CHANNEL_ID>` — os gráficos nativos do ThingSpeak
já mostram os pontos chegando, e servem como print de evidência para a entrega.
