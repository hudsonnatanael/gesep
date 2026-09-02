#include <WiFi.h>
#include <HTTPClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <time.h>

// ============================================================
// CONFIGURAÇÕES DO WI-FI
// ============================================================

const char* ssid = "AP-GESEP02";
const char* password = "g3s3pufv";

// ============================================================
// CONFIGURAÇÕES DA API
// ============================================================

const char* serverURL = "http://192.168.0.14:8000/api/sensors/";
const char* healthURL = "http://192.168.0.14:8000/api/health";

const char* DEVICE_ID = "ESP32_SENSOR_01";

// ============================================================
// PINOS
// ============================================================

#define PINO_IRRADCELL 34
#define PINO_RAD       35
#define PINO_TEMP      32

// ============================================================
// DS18B20
// ============================================================

OneWire oneWire(PINO_TEMP);
DallasTemperature sensors(&oneWire);

// Endereço do sensor de temperatura do módulo FV
DeviceAddress sensorPV = {
  0x28, 0xF8, 0x5C, 0x34,
  0x00, 0x00, 0x00, 0x3F
};

// Endereço do sensor de temperatura ambiente
DeviceAddress sensorAmbiente = {
  0x28, 0x3E, 0x0E, 0xBE,
  0x00, 0x00, 0x00, 0xC6
};

// ============================================================
// ADC
// ============================================================

const float VREF = 3.3;
const int ADC_MAX = 4095;

// ============================================================
// FATORES DE CALIBRAÇÃO
// ============================================================

// Célula FV
// A célula já está calibrada. O valor de irradiância em W/m² é obtido
// diretamente a partir do ADC bruto do pino 34, usando a escala de calibração.
const float FATOR_IRRADCELL = 1000.0 / 3602.79;

// Pyranômetro
const float FATOR_IRRADIANCIA = 803.86;

// Relação de calibração da tensão do pyranômetro
const float ADC_OFFSET_RAD = 0.146235;
const float ADC_GAIN_RAD = 0.000808;

// ============================================================
// SHUNT
// ============================================================

const float SHUNT = 0.22;

// ============================================================
// CONFIGURAÇÃO DAS LEITURAS
// ============================================================

const unsigned long intervaloLeitura = 60000; // 60 segundos

const int NUM_LEITURAS = 10;

float tensoesShunt[NUM_LEITURAS];
float irradiancias[NUM_LEITURAS];
float irradianciasCell[NUM_LEITURAS];
float temperaturasPV[NUM_LEITURAS];
float temperaturasAmbiente[NUM_LEITURAS];

String timestamps[NUM_LEITURAS];

int indiceLeitura = 0;

unsigned long tempoUltimaLeitura = 0;

// ============================================================
// FUNÇÃO PARA OBTER DATA/HORA
// ============================================================

String getBrazilIsoTimestamp() {

  struct tm timeinfo;

  if (!getLocalTime(&timeinfo, 2000)) {
    return "";
  }

  char buffer[30];

  strftime(
    buffer,
    sizeof(buffer),
    "%Y-%m-%dT%H:%M:%S",
    &timeinfo
  );

  return String(buffer) + "-03:00";
}

// ============================================================
// SINCRONIZAÇÃO DO HORÁRIO
// ============================================================

bool sincronizarHorario() {

  Serial.println();
  Serial.println("========================================");
  Serial.println("SINCRONIZANDO HORARIO");
  Serial.println("========================================");

  // Horário de Brasília = UTC-3
  configTime(
    -3 * 3600,
    0,
    "pool.ntp.org",
    "a.st1.ntp.br",
    "br.pool.ntp.org"
  );

  struct tm timeinfo;

  for (int i = 0; i < 20; i++) {

    if (getLocalTime(&timeinfo, 1000)) {

      Serial.println();
      Serial.println("Horario sincronizado!");

      Serial.print("Data/Hora: ");
      Serial.println(getBrazilIsoTimestamp());

      return true;
    }

    Serial.print(".");
  }

  Serial.println();
  Serial.println("ERRO: nao foi possivel sincronizar o horario.");

  return false;
}

// ============================================================
// CONEXÃO WI-FI
// ============================================================

void conectarWiFi() {

  Serial.println();
  Serial.println("========================================");
  Serial.println("CONECTANDO AO WI-FI");
  Serial.println("========================================");

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  int tentativas = 0;

  while (WiFi.status() != WL_CONNECTED && tentativas < 30) {

    delay(500);

    Serial.print(".");

    tentativas++;
  }

  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {

    Serial.println("Wi-Fi conectado!");

    Serial.print("IP do ESP32: ");
    Serial.println(WiFi.localIP());

    Serial.print("RSSI: ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm");

  } else {

    Serial.println("ERRO: nao foi possivel conectar ao Wi-Fi.");
  }
}

// ============================================================
// VERIFICAÇÃO DA API
// ============================================================

void verificarAPI() {

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi desconectado.");
    return;
  }

  HTTPClient http;

  Serial.println();
  Serial.println("Verificando API...");

  http.begin(healthURL);

  int httpCode = http.GET();

  Serial.print("HTTP Code: ");
  Serial.println(httpCode);

  if (httpCode > 0) {

    String resposta = http.getString();

    Serial.print("Resposta: ");
    Serial.println(resposta);

  } else {

    Serial.print("Erro na API: ");
    Serial.println(http.errorToString(httpCode));
  }

  http.end();
}

// ============================================================
// LEITURA DO PYRANÔMETRO
// ============================================================

float lerPiranometro() {

  int adc_rad = analogRead(PINO_RAD);

  float tensao_rad =
    adc_rad * ADC_GAIN_RAD + ADC_OFFSET_RAD;

  float irradiancia =
    tensao_rad * FATOR_IRRADIANCIA;

  if (irradiancia < 0) {
    irradiancia = 0;
  }

  return irradiancia;
}

// ============================================================
// LEITURA DA CÉLULA FV
// ============================================================

float lerIrradianciaCell() {

  int adc_cell = analogRead(PINO_IRRADCELL);

  // A célula já foi calibrada; por isso a irradiância em W/m² é obtida
  // diretamente do valor lido do ADC do pino 34 multiplicado pela calibração.
  float irradiancia_cell =
    adc_cell * FATOR_IRRADCELL;

  if (irradiancia_cell < 0) {
    irradiancia_cell = 0;
  }

  if (adc_cell <= 0) {
    irradiancia_cell = 0.0;
  }

  return irradiancia_cell;
}

// ============================================================
// LEITURA DA TENSÃO DO SHUNT
// ============================================================

float lerTensaoShunt() {

  int adc_cell = analogRead(PINO_IRRADCELL);

  float tensao_esp32_celula =
    (adc_cell * VREF) / ADC_MAX;

  // Relação de calibração utilizada anteriormente
  float tensao_shunt =
    0.0021308331557639 * tensao_esp32_celula;

  return tensao_shunt;
}

// ============================================================
// LEITURA DA TEMPERATURA DO MÓDULO FV
// ============================================================

float lerTemperaturaPV() {

  sensors.requestTemperatures();

  float temperatura =
    sensors.getTempC(sensorPV);

  if (temperatura == DEVICE_DISCONNECTED_C) {

    Serial.println("ERRO: sensor PV desconectado.");

    return -127.0;
  }

  return temperatura;
}

// ============================================================
// LEITURA DA TEMPERATURA AMBIENTE
// ============================================================

float lerTemperaturaAmbiente() {

  sensors.requestTemperatures();

  float temperatura =
    sensors.getTempC(sensorAmbiente);

  if (temperatura == DEVICE_DISCONNECTED_C) {

    Serial.println("ERRO: sensor ambiente desconectado.");

    return -127.0;
  }

  return temperatura;
}

// ============================================================
// MOSTRAR UMA LEITURA NO SERIAL
// ============================================================

void mostrarLeitura(
  float tensaoShunt,
  float irradiancia,
  float irradianciaCell,
  float temperaturaPV,
  float temperaturaAmbiente,
  String timestamp
) {

  Serial.println();
  Serial.println("----------------------------------------");
  Serial.println("NOVA LEITURA");
  Serial.println("----------------------------------------");

  Serial.print("Timestamp: ");
  Serial.println(timestamp);

  Serial.print("Irradiancia Celula: ");
  Serial.print(irradianciaCell, 2);
  Serial.println(" W/m2");

  Serial.print("Irradiancia Pyranometro: ");
  Serial.print(irradiancia, 2);
  Serial.println(" W/m2");

  Serial.print("Temperatura PV: ");
  Serial.print(temperaturaPV, 2);
  Serial.println(" °C");

  Serial.print("Temperatura Ambiente: ");
  Serial.print(temperaturaAmbiente, 2);
  Serial.println(" °C");

  Serial.println("----------------------------------------");
}

// ============================================================
// ENVIO DOS DADOS PARA A API
// ============================================================

bool enviarDadosAPI() {

  if (WiFi.status() != WL_CONNECTED) {

    Serial.println();
    Serial.println("Wi-Fi desconectado. Tentando reconectar...");

    conectarWiFi();

    if (WiFi.status() != WL_CONNECTED) {
      return false;
    }
  }

  HTTPClient http;

  http.begin(serverURL);

  http.addHeader(
    "Content-Type",
    "application/json"
  );

  // ========================================================
  // MONTA JSON
  // ========================================================

  String json = "[";

  for (int i = 0; i < NUM_LEITURAS; i++) {

    json += "{";

    json += "\"device_id\":\"";
    json += DEVICE_ID;
    json += "\",";

    json += "\"tensao_shunt\":";
    json += String(tensoesShunt[i], 6);
    json += ",";

    json += "\"irradiance\":";
    json += String(irradiancias[i], 2);
    json += ",";

    json += "\"irradiance_cell\":";
    json += String(irradianciasCell[i], 2);
    json += ",";

    json += "\"temperatura_pv\":";
    json += String(temperaturasPV[i], 2);
    json += ",";

    json += "\"temperatura_ambiente\":";
    json += String(temperaturasAmbiente[i], 2);
    json += ",";

    json += "\"timestamp\":\"";
    json += timestamps[i];
    json += "\"";

    json += "}";

    if (i < NUM_LEITURAS - 1) {
      json += ",";
    }
  }

  json += "]";

  // ========================================================
  // MOSTRA JSON NO SERIAL
  // ========================================================

  Serial.println();
  Serial.println("========================================");
  Serial.println("ENVIANDO DADOS PARA API");
  Serial.println("========================================");

  for (int i = 0; i < NUM_LEITURAS; i++) {
    Serial.print("Item ");
    Serial.print(i + 1);
    Serial.print(" => ");
    Serial.println(timestamps[i]);
  }

  Serial.println(json);

  // ========================================================
  // ENVIA POST
  // ========================================================

  int httpCode = http.POST(json);

  Serial.print("HTTP Code: ");
  Serial.println(httpCode);

  if (httpCode > 0) {

    String resposta = http.getString();

    Serial.println("Resposta da API:");
    Serial.println(resposta);

    http.end();

    return true;

  } else {

    Serial.print("Erro no envio: ");
    Serial.println(http.errorToString(httpCode));

    http.end();

    return false;
  }
}

// ============================================================
// SETUP
// ============================================================

void setup() {

  Serial.begin(115200);

  delay(1000);

  Serial.println();
  Serial.println("========================================");
  Serial.println("ESP32 - SENSOR DE IRRADIANCIA");
  Serial.println("========================================");

  // ========================================================
  // CONFIGURA ADC
  // ========================================================

  analogReadResolution(12);

  analogSetPinAttenuation(
    PINO_IRRADCELL,
    ADC_11db
  );

  analogSetPinAttenuation(
    PINO_RAD,
    ADC_11db
  );

  // ========================================================
  // INICIA DS18B20
  // ========================================================

  sensors.begin();

  Serial.print("Sensores DS18B20 encontrados: ");
  Serial.println(sensors.getDeviceCount());

  // ========================================================
  // CONECTA WI-FI
  // ========================================================

  conectarWiFi();

  // ========================================================
  // SINCRONIZA HORÁRIO
  // ========================================================

  if (WiFi.status() == WL_CONNECTED) {

    sincronizarHorario();

    verificarAPI();
  }

  // ========================================================
  // PRIMEIRA LEITURA IMEDIATA
  // ========================================================

  tempoUltimaLeitura =
    millis() - intervaloLeitura;

  Serial.println();
  Serial.println("Sistema pronto.");
}

// ============================================================
// LOOP
// ============================================================

void loop() {

  // ========================================================
  // VERIFICA SE ESTÁ NA HORA DE FAZER UMA LEITURA
  // ========================================================

  if (millis() - tempoUltimaLeitura >= intervaloLeitura) {

    tempoUltimaLeitura = millis();

    // ======================================================
    // LÊ OS SENSORES
    // ======================================================

    float tensaoShunt =
      lerTensaoShunt();

    float irradiancia =
      lerPiranometro();

    float irradianciaCell =
      lerIrradianciaCell();

    float temperaturaPV =
      lerTemperaturaPV();

    float temperaturaAmbiente =
      lerTemperaturaAmbiente();

    String timestamp =
      getBrazilIsoTimestamp();

    if (timestamp.length() == 0) {
      timestamp = "1970-01-01T00:00:00-03:00";
    }

    // ======================================================
    // GUARDA A LEITURA
    // ======================================================

    if (indiceLeitura < NUM_LEITURAS) {

      tensoesShunt[indiceLeitura] =
        tensaoShunt;

      irradiancias[indiceLeitura] =
        irradiancia;

      irradianciasCell[indiceLeitura] =
        irradianciaCell;

      temperaturasPV[indiceLeitura] =
        temperaturaPV;

      temperaturasAmbiente[indiceLeitura] =
        temperaturaAmbiente;

      timestamps[indiceLeitura] =
        timestamp;

      Serial.print("Leitura ");
      Serial.print(indiceLeitura + 1);
      Serial.print("/10 gravada em: ");
      Serial.println(timestamp);

      // ====================================================
      // MOSTRA NO SERIAL
      // ====================================================

      mostrarLeitura(
        tensaoShunt,
        irradiancia,
        irradianciaCell,
        temperaturaPV,
        temperaturaAmbiente,
        timestamp
      );

      indiceLeitura++;

      Serial.print("Leituras armazenadas: ");
      Serial.print(indiceLeitura);
      Serial.print("/");
      Serial.println(NUM_LEITURAS);
    }

    // ======================================================
    // QUANDO CHEGAR A 10 LEITURAS, ENVIA PARA API
    // ======================================================

    if (indiceLeitura >= NUM_LEITURAS) {

      bool sucesso =
        enviarDadosAPI();

      if (sucesso) {

        Serial.println();
        Serial.println("========================================");
        Serial.println("10 LEITURAS ENVIADAS COM SUCESSO!");
        Serial.println("========================================");

        // Zera o índice para começar novo lote
        indiceLeitura = 0;

      } else {

        Serial.println();
        Serial.println("ERRO: falha ao enviar lote para API.");

        // Mantém as leituras na memória.
        // O índice NÃO é zerado.
      }
    }
  }

  // ========================================================
  // PEQUENO DELAY
  // ========================================================

  delay(100);
}