#include <WiFi.h>
#include <HTTPClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// =========================
// 🌐 WIFI
// =========================
const char* ssid = "AP-GESEP02";
const char* password = "g3s3pufv";
  
const char* serverName = "http://192.168.0.19:8000/api/sensors/";

// =========================
// 🔌 PINOS
// =========================
#define PINO_CELULA   34
#define PINO_RAD      35
#define PINO_TEMP     32  // DS18B20 Signal Pin (com resistor 4,7k pull-up para VDD)

// =========================
// 📐 FATORES
// =========================
#define FATOR_CELULA 0.0021308331557639
#define FATOR_IRRADIANCIA 803.86

// =========================
// 🌡️  SENSOR DS18B20
// =========================
OneWire oneWire(PINO_TEMP);
DallasTemperature sensorTemp(&oneWire);

// Endereços dos sensores de temperatura
uint8_t sensor_pv[8] = { 0x28, 0xF8, 0x5C, 0x34, 0x00, 0x00, 0x00, 0x3F };
uint8_t sensor_ambiente[8] = { 0x28, 0x3E, 0x0E, 0xBE, 0x00, 0x00, 0x00, 0xC6 };

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

  // Inicializar sensor de temperatura DS18B20
  sensorTemp.begin();
  Serial.println("🌡️  Sensor DS18B20 inicializado");
  
  // Configurar resolução do sensor (9-12 bits)
  sensorTemp.setResolution(12);  // 0,0625°C de precisão
  
  // Verificar se sensor foi detectado
  if (sensorTemp.getDeviceCount() == 0) {
    Serial.println("❌ Nenhum sensor DS18B20 encontrado!");
  } else {
    Serial.print("✅ ");
    Serial.print(sensorTemp.getDeviceCount());
    Serial.println(" sensor(es) encontrado(s)");
    
    // Validar se consegue ler os sensores pelos endereços
    float temp_pv_test = sensorTemp.getTempC(sensor_pv);
    float temp_amb_test = sensorTemp.getTempC(sensor_ambiente);
    
    if (temp_pv_test == -127.0) {
      Serial.println("⚠️  AVISO: Sensor PV não respondendo ao endereço fornecido!");
    } else {
      Serial.print("✅ Sensor PV detectado: ");
      Serial.print(temp_pv_test);
      Serial.println("°C");
    }
    
    if (temp_amb_test == -127.0) {
      Serial.println("⚠️  AVISO: Sensor Ambiente não respondendo ao endereço fornecido!");
    } else {
      Serial.print("✅ Sensor Ambiente detectado: ");
      Serial.print(temp_amb_test);
      Serial.println("°C");
    }
  }

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
    String healthUrl = "http://192.168.0.19:8000/health";
    
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
    // 🌡️  LEITURA TEMPERATURA (2 SENSORES)
    // =========================
    sensorTemp.requestTemperatures();
    delay(750);  // ⏱️ CRÍTICO: DS18B20 precisa de 750ms para conversão com 12 bits!
    
 
    float temperatura_pv = sensorTemp.getTempC(sensor_pv);
    float temperatura_ambiente = sensorTemp.getTempC(sensor_ambiente);
    
    // Validar se os valores são válidos (DS18B20 retorna -127 em caso de erro)
    if (temperatura_pv == -127.0 || isnan(temperatura_pv)) {
      Serial.println("⚠️  Leitura de temperatura PV inválida! Sensor pode estar desconectado.");
      temperatura_pv = 0.0;
    }
    
    if (temperatura_ambiente == -127.0 || isnan(temperatura_ambiente)) {
      Serial.println("⚠️  Leitura de temperatura ambiente inválida! Sensor pode estar desconectado.");
      temperatura_ambiente = 0.0;
    }

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
      httpRequestData += "\"irradiance\":" + String(irradiancia, 2) + ",";
      httpRequestData += "\"temperatura_pv\":" + String(temperatura_pv, 2) + ",";
      httpRequestData += "\"temperatura_ambiente\":" + String(temperatura_ambiente, 2);
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
        Serial.println("  - Servidor não está rodando em 192.168.0.23:8000");
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
    Serial.print(" W/m² || 🌡️  Temp PV: ");
    Serial.print(temperatura_pv, 2);
    Serial.print(" °C | Temp Ambiente: ");
    Serial.print(temperatura_ambiente, 2);
    Serial.println(" °C");
  }
}