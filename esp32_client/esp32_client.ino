#include <WiFi.h>
#include <HTTPClient.h>

// =========================
// 🌐 WIFI
// =========================
const char* ssid = "AP-GESEP02";
const char* password = "g3s3pufv";
  
const char* serverName = "http://192.168.0.7:8000/api/sensors/";
.
// =========================
// 🔌 PINOS
// =========================
#define PINO_CELULA   34
#define PINO_RAD      35

// =========================
// 📐 FATORES
// =========================
#define FATOR_CELULA 0.0021308331557639
#define FATOR_IRRADIANCIA 803.86

// =========================
// ⏱ TEMPO
// =========================
unsigned long tempoAnterior = 0;
const unsigned long intervalo = 10000; // 10 segundos

void setup() {
  Serial.begin(115200);
  delay(1000); // Dar tempo para Serial iniciar

  Serial.println("\n\n=== ESP32 INICIALIZANDO ===");
  Serial.print("📡 Servidor esperado: ");
  Serial.println(serverName);
  Serial.print("🌐 WiFi: ");
  Serial.println(ssid);

  analogReadResolution(12);
  analogSetPinAttenuation(PINO_CELULA, ADC_11db);
  analogSetPinAttenuation(PINO_RAD, ADC_11db);

  // Conectar WiFi
  WiFi.begin(ssid, password);
  Serial.println("🔌 Conectando ao WiFi...");

  int tentativas = 0;
  while (WiFi.status() != WL_CONNECTED && tentativas < 20) {
    delay(500);
    Serial.print(".");
    tentativas++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n✅ WiFi conectado!");
    Serial.print("📍 IP da ESP32: ");
    Serial.println(WiFi.localIP());
    Serial.print("🔗 Sinal: ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm");
    
    // 🏥 Teste de conexão com o servidor
    Serial.println("\n🔍 Testando conexão com servidor...");
    testarServidor();
  } else {
    Serial.println("\n❌ Falha ao conectar WiFi!");
    Serial.print("Status: ");
    Serial.println(WiFi.status());
  }
}

// =========================
// 🏥 TESTE DE CONEXÃO
// =========================
void testarServidor() {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    String healthUrl = String(serverName) + "../health";
    
    http.begin(healthUrl);
    http.setTimeout(5000);
    
    int httpResponseCode = http.GET();
    
    if (httpResponseCode == 200) {
      Serial.println("✅ SERVIDOR RESPONDENDO - Tudo OK!");
      Serial.println("📊 Iniciando envio de dados...\n");
    } else {
      Serial.print("❌ Servidor não respondeu. Status: ");
      Serial.println(httpResponseCode);
    }
    
    http.end();
  }
}

// =========================
// 🔁 LOOP
// =========================
void loop() {

  if (millis() - tempoAnterior >= intervalo) {
    tempoAnterior = millis();

    // =========================
    // 🔵 LEITURA CÉLULA
    // =========================
    int adc_celula = analogRead(PINO_CELULA);

    float tensao_esp32_celula = (0.000808 * adc_celula) + 0.146421;
    float tensao_shunt = FATOR_CELULA * tensao_esp32_celula;

    // =========================
    // 🟡 LEITURA PIRANÔMETRO
    // =========================
    int adc_rad = analogRead(PINO_RAD);

    float tensao_rad = (adc_rad * 0.000808) + 0.146235;
    float irradiancia = tensao_rad * FATOR_IRRADIANCIA;

    // =========================
    // 📡 ENVIO PARA API
    // =========================
    if (WiFi.status() == WL_CONNECTED) {

      HTTPClient http;
      http.begin(serverName);
      http.addHeader("Content-Type", "application/json");

      String deviceId = "ESP32_PRODUCAO";

      // 🔥 JSON com dados reais
      String httpRequestData = "{";
      httpRequestData += "\"device_id\":\"" + deviceId + "\",";
      httpRequestData += "\"tensao_shunt\":" + String(tensao_shunt, 6) + ",";
      httpRequestData += "\"irradiance\":" + String(irradiancia, 2);
      httpRequestData += "}";

      Serial.println("\n📤 Enviando dados para: " + String(serverName));
      Serial.println("Payload: " + httpRequestData);

      // ⏱ Configurar timeout (10 segundos)
      http.setTimeout(10000);

      int httpResponseCode = http.POST(httpRequestData);

      if (httpResponseCode == 201 || httpResponseCode == 200) {
        Serial.print("✅ Status HTTP: ");
        Serial.println(httpResponseCode);

        String payload = http.getString();
        Serial.println("Resposta: " + payload);
      } else if (httpResponseCode > 0) {
        Serial.print("⚠️  Status HTTP inesperado: ");
        Serial.println(httpResponseCode);
        String payload = http.getString();
        Serial.println("Resposta: " + payload);
      } else {
        Serial.print("❌ Erro de conexão: ");
        Serial.println(httpResponseCode);
        Serial.println("Possíveis causas:");
        Serial.println("  - Servidor não está rodando em 192.168.0.100:8000");
        Serial.println("  - ESP32 não consegue alcançar o servidor");
        Serial.println("  - Problema na rede WiFi");
      }

      http.end();

    } else {
      Serial.println("WiFi desconectado!");
    }

    // =========================
    // 📊 DEBUG SERIAL
    // =========================
    Serial.print("ADC Celula: ");
    Serial.print(adc_celula);
    Serial.print(" | Vshunt: ");
    Serial.print(tensao_shunt, 6);

    Serial.print(" || ADC Rad: ");
    Serial.print(adc_rad);
    Serial.print(" | Irradiancia: ");
    Serial.print(irradiancia, 2);
    Serial.println(" W/m²");
  }
}