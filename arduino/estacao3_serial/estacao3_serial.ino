// Estação 3: apenas Serial USB. LED é provisório; sem I2C ou atuadores.
#include <string.h>

enum Estado { AGUARDANDO, OK, NOK };
Estado ultimoEstado = AGUARDANDO;
char comando[64];
byte tamanho = 0;
bool excedeu = false;
char ultimoCiclo[33] = "";

void aplicar(const char* resultado, const char* ciclo) {
  if (strcmp(resultado, "OK") != 0 && strcmp(resultado, "NOK") != 0) return;
  ultimoEstado = strcmp(resultado, "OK") == 0 ? OK : NOK;
  digitalWrite(LED_BUILTIN, ultimoEstado == OK ? HIGH : LOW);
  strncpy(ultimoCiclo, ciclo, sizeof(ultimoCiclo)-1);
  ultimoCiclo[sizeof(ultimoCiclo)-1] = '\0';
  Serial.print("ACK;"); Serial.print(ciclo); Serial.print(';'); Serial.println(resultado);
}

void processar() {
  // Compatibilidade com teste manual OK/NOK, terminados por nova linha.
  if (strcmp(comando, "OK") == 0 || strcmp(comando, "NOK") == 0) {
    aplicar(comando, "MANUAL");
    return;
  }
  // Protocolo só PC ↔ Uno: RESULTADO;<id hexadecimal de 32 caracteres>;<OK|NOK>
  char* tipo = strtok(comando, ";");
  char* ciclo = strtok(NULL, ";");
  char* resultado = strtok(NULL, ";");
  char* extra = strtok(NULL, ";");
  if (!tipo || !ciclo || !resultado || extra || strcmp(tipo,"RESULTADO") != 0) return;
  if (strlen(ciclo) != 32) return;
  for (byte i=0; i<32; i++) {
    char c = ciclo[i];
    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return;
  }
  aplicar(resultado, ciclo);
}

void setup() {
  Serial.begin(9600);
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);
}

void loop() {
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      comando[tamanho] = '\0';
      if (!excedeu) processar();
      tamanho = 0;
      excedeu = false;
    } else if (tamanho < sizeof(comando)-1) {
      comando[tamanho++] = c;
    } else {
      excedeu = true;
    }
  }
}
