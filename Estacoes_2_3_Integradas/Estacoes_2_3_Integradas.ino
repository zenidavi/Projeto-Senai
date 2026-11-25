/*
  SENAI / VOLKSWAGEN - ESTACOES 2 E 3 - PROTOTIPO DE BANCADA
  Arduino Uno R3 (ATmega328P, 5 V).

  Estacao 2: A0 = tensao de pilha via divisor 10k/10k (referencia 1,1 V).
  Estacao 3: D2 = TCRT5000 com fototransistor + pull-up EXTERNO.
  Saida:   D8 = pulso de liberacao para o mestre (5 V, max. 1 pulso/ciclo).
  USB: Serial 9600 baud; nao use D0/D1 para outros sinais.

  ATENCAO:
  - Este firmware requer atualizacao do Python para receber START/INICIO e
    enviar RESULTADO tambem em INCONCLUSIVO. O Python atual nao faz isso.
  - Nenhum movimento deve ser conectado durante o primeiro teste.
  - HIGH em D8 so ocorre depois de RESULTADO aceito para o ID do ciclo ativo.
  - Se o PC falhar / der timeout, D8 permanece LOW (nao libera a mesa).
  - Definir duracao de pulso de acordo com o codigo do mestre antes da mesa.
*/

#include <Arduino.h>
#include <string.h>
#include <stdlib.h>

// ===== PINOS =====
const byte PINO_TENSAO = A0;
const byte PINO_SENSOR = 2;
const byte PINO_LIBERAR = 8;

// ===== ESTACAO 2 =====
const float R1_OHMS = 10000.0f;
const float R2_OHMS = 10000.0f;
const float VREF_INTERNA = 1.10f;  // CALIBRAR com multimetro
const float TENSAO_MINIMA_V = 1.10f;
const byte NUM_AMOSTRAS = 20;
const unsigned long ENTRE_AMOSTRAS_MS = 5UL;
const unsigned long ENTRE_MEDICOES_MS = 1000UL;
unsigned long ultimaMedicaoInicio = 0;
unsigned long ultimaAmostra = 0;
unsigned long somaADC = 0;
byte amostras = 0;
bool amostrando = false;

// ===== ESTACAO 3 =====
const unsigned long DEBOUNCE_SENSOR_MS = 60UL;
const unsigned long TIMEOUT_INICIO_MS = 5000UL;
const unsigned long TIMEOUT_INSPECAO_MS = 20000UL;
const unsigned long DURACAO_PULSO_MS = 300UL; // AJUSTAR com grupo do mestre

// TCRT5000 bare: fototransistor coletor com resistor pull-up 10k a 5V,
// emissor no GND. Refletancia suficiente tende a produzir nivel LOW em D2.
const byte NIVEL_DETECTADO = LOW;

bool leituraBrutaAnterior = false;
bool sensorEstavel = false;
unsigned long alterouSensorEm = 0;

enum Estado { LIVRE, AGUARDA_INICIO, INSPECIONANDO, PULSANDO, AGUARDA_RETIRADA };
Estado estado = LIVRE;
unsigned long estadoDesde = 0;
unsigned long pulsoDesde = 0;
unsigned long sequencia = 0;
char idCiclo[33] = "";
char resultadoCiclo[14] = "";

char linha[100];
byte posicao = 0;
bool linhaLonga = false;

bool idValido(const char *s) {
  if (strlen(s) != 32) return false;
  for (byte i = 0; i < 32; ++i) {
    char c = s[i];
    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
  }
  return true;
}

void irPara(Estado proximo, unsigned long agora) {
  estado = proximo;
  estadoDesde = agora;
}

void atualizarSensor(unsigned long agora) {
  bool leitura = (digitalRead(PINO_SENSOR) == NIVEL_DETECTADO);
  if (leitura != leituraBrutaAnterior) {
    leituraBrutaAnterior = leitura;
    alterouSensorEm = agora;
  }
  if (agora - alterouSensorEm >= DEBOUNCE_SENSOR_MS) {
    sensorEstavel = leitura;
  }
}

void iniciarPedido(unsigned long agora) {
  ++sequencia;
  if (sequencia == 0) ++sequencia;
  idCiclo[0] = '\0';
  resultadoCiclo[0] = '\0';
  Serial.print(F("START;"));
  Serial.println(sequencia);
  irPara(AGUARDA_INICIO, agora);
}

void abortarCiclo(const __FlashStringHelper* motivo, unsigned long agora) {
  digitalWrite(PINO_LIBERAR, LOW);
  Serial.print(F("ERRO;"));
  Serial.println(motivo);
  irPara(AGUARDA_RETIRADA, agora);
}

void processarLinha(char *texto, unsigned long agora) {
  // Protocolo PC -> Uno:
  // INICIO;<sequencia>; <uuid 32 hex minusculos>   (SEM ESPACOS)
  // RESULTADO;<uuid 32 hex minusculos>;<OK|NOK|INCONCLUSIVO>
  char *tipo = strtok(texto, ";");
  char *campo1 = strtok(NULL, ";");
  char *campo2 = strtok(NULL, ";");
  char *extra = strtok(NULL, ";");
  if (!tipo || !campo1 || !campo2 || extra) return;

  if (strcmp(tipo, "INICIO") == 0 && estado == AGUARDA_INICIO) {
    char *fim = NULL;
    unsigned long seq = strtoul(campo1, &fim, 10);
    if (*campo1 == '\0' || *fim != '\0' || seq != sequencia || !idValido(campo2)) {
      Serial.println(F("ERRO;INICIO_INVALIDO"));
      return;
    }
    strcpy(idCiclo, campo2);
    irPara(INSPECIONANDO, agora);
    Serial.print(F("PRONTO;"));
    Serial.println(idCiclo);
    return;
  }

  if (strcmp(tipo, "RESULTADO") == 0 && estado == INSPECIONANDO) {
    if (strcmp(campo1, idCiclo) != 0) {
      Serial.println(F("ERRO;ID_DIFERENTE"));
      return;
    }
    if (strcmp(campo2, "OK") != 0 && strcmp(campo2, "NOK") != 0 &&
        strcmp(campo2, "INCONCLUSIVO") != 0) {
      Serial.println(F("ERRO;RESULTADO_INVALIDO"));
      return;
    }
    strcpy(resultadoCiclo, campo2);
    // O ACK confirma aceite pelo Uno; o pulso ainda sera concluido.
    Serial.print(F("ACK;"));
    Serial.print(idCiclo);
    Serial.print(';');
    Serial.println(resultadoCiclo);
    digitalWrite(PINO_LIBERAR, HIGH);
    digitalWrite(LED_BUILTIN, HIGH);
    pulsoDesde = agora;
    irPara(PULSANDO, agora);
  }
}

void atualizarSerial(unsigned long agora) {
  while (Serial.available() > 0) {
    char c = char(Serial.read());
    if (c == '\r') continue;
    if (c == '\n') {
      linha[posicao] = '\0';
      if (!linhaLonga && posicao > 0) processarLinha(linha, agora);
      else if (linhaLonga) Serial.println(F("ERRO;LINHA_MUITO_LONGA"));
      posicao = 0;
      linhaLonga = false;
    } else if (posicao < sizeof(linha) - 1 && !linhaLonga) {
      linha[posicao++] = c;
    } else {
      linhaLonga = true;
    }
  }
}

void atualizarTensao(unsigned long agora) {
  if (!amostrando) {
    if (agora - ultimaMedicaoInicio < ENTRE_MEDICOES_MS) return;
    ultimaMedicaoInicio = agora;
    analogRead(PINO_TENSAO); // descarta a primeira conversao
    somaADC = 0;
    amostras = 0;
    ultimaAmostra = agora;
    amostrando = true;
    return;
  }
  if (agora - ultimaAmostra < ENTRE_AMOSTRAS_MS) return;
  ultimaAmostra = agora;
  somaADC += analogRead(PINO_TENSAO);
  ++amostras;
  if (amostras == NUM_AMOSTRAS) {
    float mediaADC = float(somaADC) / NUM_AMOSTRAS;
    float tensaoPilha = (mediaADC * VREF_INTERNA / 1024.0f)
                        * (R1_OHMS + R2_OHMS) / R2_OHMS;
    Serial.print(F("TENSAO;"));
    Serial.print(tensaoPilha, 2);
    Serial.print(';');
    Serial.println(tensaoPilha >= TENSAO_MINIMA_V ? F("APROVADO") : F("REPROVADO"));
    amostrando = false;
  }
}

void atualizarCiclo(unsigned long agora) {
  switch (estado) {
    case LIVRE:
      if (sensorEstavel) iniciarPedido(agora);
      break;
    case AGUARDA_INICIO:
      if (agora - estadoDesde >= TIMEOUT_INICIO_MS) {
        abortarCiclo(F("SEM_RESPOSTA_PC"), agora);
      }
      break;
    case INSPECIONANDO:
      if (agora - estadoDesde >= TIMEOUT_INSPECAO_MS) {
        abortarCiclo(F("TIMEOUT_INSPECAO"), agora);
      }
      break;
    case PULSANDO:
      if (agora - pulsoDesde >= DURACAO_PULSO_MS) {
        digitalWrite(PINO_LIBERAR, LOW);
        digitalWrite(LED_BUILTIN, LOW);
        Serial.print(F("PULSO_CONCLUIDO;"));
        Serial.println(idCiclo);
        irPara(AGUARDA_RETIRADA, agora);
      }
      break;
    case AGUARDA_RETIRADA:
      if (!sensorEstavel) {
        Serial.println(F("REARMADO"));
        irPara(LIVRE, agora);
      }
      break;
  }
}

void setup() {
  pinMode(PINO_SENSOR, INPUT_PULLUP); // pull-up interno + externo 10k recomendado
  pinMode(PINO_LIBERAR, OUTPUT);
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(PINO_LIBERAR, LOW);
  digitalWrite(LED_BUILTIN, LOW);
  analogReference(INTERNAL);
  delay(15); // estabiliza apenas na inicializacao
  analogRead(PINO_TENSAO);
  Serial.begin(9600);
  ultimaMedicaoInicio = millis() - ENTRE_MEDICOES_MS;
  alterouSensorEm = millis();
  Serial.println(F("ESTACOES_2_3;INICIADO"));
}

void loop() {
  unsigned long agora = millis();
  atualizarSensor(agora);
  atualizarSerial(agora);
  atualizarTensao(agora);
  atualizarCiclo(agora);
}
