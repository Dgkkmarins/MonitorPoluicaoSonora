// ==========================================
// ESP8266 + Sensor de Som Analogico
// Le o sensor, monta um JSON e envia via
// Wi-Fi (HTTP POST) para o gateway Python
// ==========================================

#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>
#include <ArduinoJson.h>

// ------------------------------------------
// CONFIGURACAO DE REDE
// ------------------------------------------
const char* WIFI_SSID   = "NOME_DA_SUA_REDE";
const char* WIFI_SENHA  = "SENHA_DA_SUA_REDE";

// IP da maquina onde o gateway Python (gateway.py) esta rodando
// Descubra com "ipconfig" (Windows) -> IPv4 Address
const char* SERVIDOR_URL = "http://192.168.0.10:5000/dados";

const int SENSOR = A0;
const unsigned long INTERVALO_ENVIO_MS = 5000; // envia a cada 5s

// Identificador deste dispositivo (util se houver mais de um sensor)
const char* DEVICE_ID = "esp8266_som_01";

unsigned long ultimoEnvio = 0;

// ==========================================
// CALIBRACAO DO SENSOR -> DECIBEIS
// ------------------------------------------
// O modulo de som analogico (ex: KY-038) nao entrega dB direto,
// apenas uma tensao proporcional a amplitude do som captado.
// Aqui fazemos uma conversao aproximada (0-1023 -> ~30-100 dB).
// Ajuste os valores MIN_DB/MAX_DB depois de calibrar com um
// decibelimetro de referencia (app de celular serve para estimar).
// ==========================================
const float MIN_DB = 30.0;
const float MAX_DB = 100.0;

float converterParaDecibeis(int valorSensor) {
  float percentual = valorSensor / 1023.0;
  return MIN_DB + percentual * (MAX_DB - MIN_DB);
}

String classificarNivel(float decibeis) {
  if (decibeis < 50.0) return "BAIXO";
  if (decibeis < 70.0) return "MODERADO";
  if (decibeis < 85.0) return "ALTO";
  return "CRITICO";
}

// ==========================================
// WI-FI
// ==========================================
void conectarWiFi() {
  Serial.print("Conectando ao WiFi: ");
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_SENHA);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.print("WiFi conectado! IP do ESP: ");
  Serial.println(WiFi.localIP());
}

// ==========================================
// ENVIO DO JSON PARA O GATEWAY PYTHON
// ==========================================
void enviarDados(int valorSensor, float decibeis, const String& nivel) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi desconectado, tentando reconectar...");
    conectarWiFi();
    return;
  }

  WiFiClient client;
  HTTPClient http;

  StaticJsonDocument<256> doc;
  doc["device_id"]     = DEVICE_ID;
  doc["valor_sensor"]  = valorSensor;
  doc["decibeis"]      = decibeis;
  doc["nivel"]         = nivel;
  doc["uptime_ms"]     = millis();

  String payload;
  serializeJson(doc, payload);

  http.begin(client, SERVIDOR_URL);
  http.addHeader("Content-Type", "application/json");

  int codigoResposta = http.POST(payload);

  Serial.print("Enviado: ");
  Serial.println(payload);
  Serial.print("Resposta do servidor: ");
  Serial.println(codigoResposta);

  http.end();
}

// ==========================================
// CONFIGURACAO
// ==========================================
void setup() {
  Serial.begin(115200);

  Serial.println();
  Serial.println("==================================");
  Serial.println("   MONITOR DE POLUICAO SONORA");
  Serial.println("==================================");

  conectarWiFi();

  Serial.println("Sistema iniciado!");
  Serial.println();
}

// ==========================================
// LOOP PRINCIPAL
// ==========================================
void loop() {
  unsigned long agora = millis();

  if (agora - ultimoEnvio >= INTERVALO_ENVIO_MS) {
    ultimoEnvio = agora;

    int valorSensor = analogRead(SENSOR);
    float decibeis = converterParaDecibeis(valorSensor);
    String nivelPoluicao = classificarNivel(decibeis);

    Serial.print("Sensor: ");
    Serial.print(valorSensor);
    Serial.print(" | dB: ");
    Serial.print(decibeis);
    Serial.print(" | Nivel: ");
    Serial.println(nivelPoluicao);

    enviarDados(valorSensor, decibeis, nivelPoluicao);
  }
}
