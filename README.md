# SENAI Volkswagen | Mesa giratória — Estações 2 e 3

Projeto acadêmico de inspeção visual e monitoramento elétrico, com supervisório local Flask, Python, OpenCV, YOLOv8, SQLite e Arduino Uno.

## Estado em 25/11/2026

| Recurso | Estado |
|---|---|
| Estação 3: webcam, YOLOv8, histórico e supervisório | Testado localmente no SENAI |
| Interface Codex: operação, ocorrências, análises e comparação | Restaurada a partir da branch estacao-03-supervisorio |
| Estação 2: Arduino Uno compartilhado, leitura Serial e aba Tensão | Testados em bancada; dados reais exibidos no painel |
| Bateria nominal de 3 V | Medição ainda não calibrada: circuito original satura perto de 2,20 V |
| Sensor TCRT5000, início automático, pulso D8 e mestre | A validar; não conecte o motor durante os testes de bancada |
| Comunicação Serial unificada no Python | Pendente: leitor de tensão e inferência ainda são processos separados |

## Instalação (Windows)

Na raiz, com Python e uma webcam USB (opcional para o painel):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe supervisorio\app.py
```

Abra http://127.0.0.1:5000/. A aba de tensão fica em http://127.0.0.1:5000/tensao.

Para a câmera, configure CAM_INDEX em config.py com listar_cameras.py. Forneça o arquivo de pesos treinado em runs/estacao3/tampa/weights/best.pt e, em outro terminal:

```powershell
.\.venv\Scripts\python.exe inferencia.py
```

Mantenha USE_SERIAL=False enquanto o leitor da Estação 2 estiver rodando. Apenas um processo deve abrir a mesma porta COM. O Flask não abre a webcam nem a Serial.

## Estação 2

O firmware de bancada usa A0, divisor 10 kΩ/10 kΩ, referência interna nominal de 1,1 V e Serial 9600 baud. A tensão é enviada como TENSAO;valor;APROVADO ou REPROVADO. O limite original de 1,10 V ainda não foi redefinido para a bateria de 3 V.

O painel marca valores próximos ao teto nominal (2,19 V ou superiores) como saturados e não validados. A leitura de 0 V sem bateria não é uma reprovação de uma peça identificada. O gráfico mostra até 120 amostras contínuas, não a contagem de peças.

### Receber as medições no supervisório

Grave `Estacoes_2_3_Integradas/Estacoes_2_3_Integradas.ino` na placa Uno. Feche o Monitor Serial. Em um terminal separado, na raiz:

```powershell
.\.venv\Scripts\python.exe -m serial.tools.list_ports -v
.\.venv\Scripts\python.exe Estacoes_2_3_Integradas\ler_tensao.py COM10 --gravar
```

Substitua COM10 pela porta encontrada no seu PC. Sem `--gravar`, as leituras aparecem apenas no terminal. O SQLite de tensão fica em `Estacoes_2_3_Integradas/tensao_estacao2.db`; os dados não são versionados. Os registros de bancada não são aprovação metrológica. Consulte [instruções do Arduino compartilhado](Estacoes_2_3_Integradas/LEIA-ME.txt).

## Integração física prevista

A0: divisor de tensão. D2: TCRT5000 sem módulo, com circuito externo e pull-up. D8: pulso HIGH provisório de 300 ms, após resultado de ciclo identificado (OK, NOK ou INCONCLUSIVO), para o mestre. Sem resposta do PC, não deve liberar a mesa. A duração e a detecção de borda devem ser combinadas com o grupo do mestre. O Arduino não substitui intertravamentos físicos.

## Dados e validação

Pesos e datasets, bancos SQLite, imagens de inspeções e ambientes virtuais ficam fora do Git. Um treinamento piloto YOLOv8n alcançou mAP@50 de 99,5% em apenas 12 imagens de validação; falta teste independente. Não representa precisão comprovada em produção. O modelo detecta as classes tampa_ok e tampa_nok.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Consulte [Guia de demonstração](GUIA_DEMONSTRACAO.md), [Guia de dados e relatórios](GUIA_DADOS_RELATORIOS_ESTACAO3.md) e [documentação histórica](docs/README-historico-2026-11-18.md). A documentação histórica descreve a versão anterior, não todas as rotas atuais.

## Próximos passos

Calibrar divisor e referência para a bateria de 3 V; definir limite de aprovação com a Estação 2; consolidar a Serial com START e resultados correlacionados; testar TCRT5000 e pulso D8 com mestre desconectado; integrar e validar mestre; testar IA com imagens independentes; implementar rastreabilidade e medir FPS.
