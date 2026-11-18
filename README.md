# Estação 3 — Inspeção visual inteligente | SENAI Volkswagen

**Projeto acadêmico de automação industrial:** sistema de visão computacional para avaliar a condição visual de peças na Estação 3 de uma mesa giratória. A webcam USB fornece imagens ao Python/OpenCV; o YOLOv8 Object Detection identifica a condição da tampa; uma máquina de estados determina **OK**, **NOK** ou **INCONCLUSIVO**. O sistema mantém histórico em SQLite e disponibiliza um supervisório Flask. A comunicação com o Arduino é opcional e a integração final com a mesa ainda está em desenvolvimento.

> **Importante — código publicado × protótipo local:** o repositório contém a base do sistema, testes, simulador e supervisório básico. O modelo treinado, os datasets, a câmera ao vivo no painel, o redesign de central de controle e os experimentos de relatórios foram desenvolvidos/testados em cópias **locais** e **não estão integralmente publicados nesta branch**. Não se deve interpretar a presença de funções no escopo como implementação disponível no GitHub.

## Estado do projeto

| Componente | Situação |
|---|---|
| Captura, inferência, ciclos, SQLite, Flask e testes | Código disponível neste repositório |
| Dataset da tampa e YOLOv8n treinado | Realizados e validados inicialmente no computador do SENAI; arquivos locais não versionados |
| Teste com webcam e reconhecimento verde/OK, vermelho/NOK | Funcionou no piloto local |
| Câmera ao vivo, botão web e visual de central de controle | Protótipos locais; não disponíveis integralmente neste repositório |
| Painéis analíticos, filtros e relatórios PDF/CSV | Desenvolvidos como expansão local; integração no projeto principal ainda precisa ser verificada |
| Serial com ACK PC ↔ Arduino | Implementação de software no repositório; protocolo final e hardware não validados de ponta a ponta |
| I2C/controlador central e integração com outras estações | Pendente de integração e testes físicos |
| Desempenho da prévia web | Versão experimental local limitada a 12 FPS; otimização pendente |

## Piloto de treinamento realizado em 11/11/2026

Foi treinado um **YOLOv8n** para duas classes, `tampa_ok` e `tampa_nok`, com imagens anotadas em bounding boxes no Roboflow. O treinamento local foi executado com Python/Ultralytics na CPU **Intel Core i5-14500**, resolução de 640 × 640, até 100 épocas, batch 16 e early stopping com patience 20. Terminou após **56 épocas (~14,7 minutos)** e gerou `runs/estacao3/tampa/weights/best.pt` (arquivo local, ignorado pelo Git).

| Métrica final de validação | Valor |
|---|---:|
| Precision | 99,1% |
| Recall | 100% |
| mAP@50 | 99,5% |
| mAP@50:95 | 87,3% |

**Limitação dos resultados:** a validação teve **apenas 12 imagens (7 OK, 5 NOK)**. O valor de mAP não representa uma taxa de acerto garantida na operação real. Precisamos de um conjunto independente coletado em outras sessões, posições e iluminações, evitando imagens quase idênticas em treino e teste. A detecção de faces verde/vermelha valida o fluxo de software, **não** constitui detecção de defeitos físicos industriais.

Os arquivos `best.pt`, `dataset/`, `dataset_roboflow/` e os bancos SQLite não são publicados no GitHub. Quem clonar este repositório precisará fornecer um modelo e um dataset próprios ou usar o simulador sem hardware.

![Dashboard da Estação 3 com registros simulados](docs/images/dashboard-ciclos.png)

*Captura de uma simulação: uma falha de câmera encerrou a tentativa como INCONCLUSIVO. O processo já estava parado na imagem, por isso a estação aparece sem conexão.*

## Começar pela demonstração sem hardware

Na raiz do projeto, com Python instalado:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install flask
$env:ESTACAO3_DB = 'supervisorio/simulacao.db'
python supervisorio/app.py
```

Em outro terminal, também na raiz:

```powershell
python supervisorio/simulador.py --cenario misto --quantidade 8 --intervalo 2 --seed 42
```

Abra **http://127.0.0.1:5000**. Essa demonstração não usa câmera, pesos YOLO ou Arduino. Ela mostra o fluxo de ciclos, histórico, gráfico e falhas técnicas.

Documentação:

- [Guia de demonstração](GUIA_DEMONSTRACAO.md): roteiro para apresentar o projeto.
- [O que foi desenvolvido](ALTERACOES.md): funções de cada parte e mudanças nos scripts originais.
- [Validação atual](VALIDACAO_CICLOS.md): testes realizados e limitações.
- As seções abaixo explicam instalação completa, dataset, treinamento, inferência e Arduino.

## Arquitetura implementada

```text
Webcam USB → OpenCV/Python → YOLOv8 (best.pt) → ciclo de inspeção + confirmação estável
                                              ├→ SQLite → Flask → dashboard
                                              └→ Serial USB opcional → Arduino Uno
```

O Flask consulta o mesmo banco que a inferência escreve. O painel atualiza a cada 2 segundos, sem recarregar a página. Os gráficos usam HTML/CSS e JavaScript locais, sem CDN. O painel separa **estado atual da estação** (atualizações do processo) de **último ciclo encerrado** (histórico). A conexão com Flask não comprova conexão da câmera. Se o processo parar ou não atualizar por 8 segundos, a estação aparece SEM CONEXÃO; um OK antigo continua apenas como histórico.

## Estrutura

```text
config.py                         Configurações centralizadas
listar_cameras.py                 Identificação da webcam no Windows
captura_dataset.py                Captura com 1 / 2 / Q
treinar.py                        Treinamento YOLOv8 de detecção
inferencia.py                     Inferência, evidência e Serial
ciclo.py                          Máquina de estados independente do hardware
requirements.txt                  ultralytics, opencv-python, pyserial, flask
.gitignore                        Ignora dataset, pesos e bancos locais
gitignore                         Arquivo original preservado
supervisorio/
  __init__.py
  database.py                     sqlite3 padrão; WAL; conexões curtas
  app.py                          Flask e APIs JSON
  simulador.py                    Somente execução explícita
  templates/index.html
  static/style.css
  static/dashboard.js
arduino/estacao3_serial/
  estacao3_serial.ino              Receptor Serial; LED provisório
tests/test_estacao3.py             Testes da base
tests/test_ciclos.py               Ciclos, falhas, migração e ACK
GUIA_DEMONSTRACAO.md              Apresentação sem tampa/câmera/modelo
VALIDACAO_CICLOS.md               Validação da versão atual
```

As pastas dataset/, dataset_roboflow/, runs/ e o banco são criados/usados conforme necessário. O dataset rotulado e o `best.pt` do piloto existem na cópia local de desenvolvimento, mas **não estão incluídos no GitHub**. Todos os caminhos padrão partem da pasta de config.py, independentemente do diretório atual.

## Situação do supervisório e das expansões locais

A branch publicada atualmente expõe as rotas **`/`**, **`/api/status`**, **`/api/historico`** e **`/api/inspecoes/<id>/imagem`** (além dos arquivos estáticos). O dashboard consulta registros reais ou simulados do SQLite. As rotas de vídeo, comando web e relatórios avançados **não fazem parte desta versão publicada**.

Na cópia de desenvolvimento foram testados transmissão de vídeo do OpenCV ao navegador, controle manual pelo painel, estilo visual de central industrial e ferramentas de análise/relatórios. Essas mudanças passaram por scripts experimentais e devem ser consolidadas, revisadas e testadas antes de sincronizar com esta branch. Não rode os scripts experimentais nem tente acessar `/analises` em um clone limpo esperando encontrar esses recursos.

**Pendências de robustez identificadas no piloto:** no Windows do SENAI apareceram um `WinError 5` ao substituir o arquivo JPEG da prévia e um erro SQLite de banco somente leitura. O banco copiado para outro computador passou nos testes de integridade e escrita, mas isso **não demonstra** que o problema no PC do SENAI foi resolvido. A otimização da prévia atualmente limitada a **12 FPS** também permanece pendente.

## Instalar (Windows / PowerShell)

Abra o terminal na pasta do projeto. Recomenda-se Python 3.11 ou 3.12 para maior compatibilidade com PyTorch/Ultralytics. A disponibilidade de dependências deve ser verificada no PC de operação.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Caso a ativação esteja bloqueada, use diretamente `.\.venv\Scripts\python.exe` em lugar de `python`. SQLite usa sqlite3 do próprio Python, sem pacote adicional. Para testar apenas o supervisório, basta instalar Flask (`python -m pip install flask`). A operação de inferência não usa serviços de nuvem; instale dependências e obtenha os pesos antecipadamente.

## 1. Identificar e configurar câmera

```powershell
python listar_cameras.py
```

O utilitário testa os índices 0 a 4 usando o backend Windows MSMF. Pressione uma tecla no preview para passar ao próximo índice. Ajuste **CAM_INDEX em config.py** para a webcam USB. Captura e inferência usam o mesmo índice. Este projeto mantém o backend Windows do script original.

## 2. Capturar e rotular dataset

```powershell
python captura_dataset.py
```

- 1: dataset/tampa_ok/tampa_ok_0001.jpg e seguintes.
- 2: dataset/tampa_nok/tampa_nok_0001.jpg e seguintes.
- Q: sair.

A imagem salva é uma cópia limpa do mesmo frame do preview, antes dos textos. O contador retoma a maior sequência existente, evitando sobrescritas se imagens foram removidas. A tela mantém contador, preview e atalhos originais.

Crie no Roboflow um projeto de **Object Detection**, envie as imagens e desenhe bounding boxes na tampa. A pasta de captura indica a condição, mas **não substitui os rótulos de detecção**. Use os nomes exatos tampa_ok e tampa_nok. Separe treino/validação/teste evitando imagens quase idênticas da mesma sequência em partições diferentes. Exporte no formato YOLOv8 e extraia em dataset_roboflow/.

Verifique data.yaml: names, nc e caminhos train/val/test devem corresponder às imagens e labels extraídos. Os caminhos relativos de exportações Roboflow podem precisar de ajuste. Configure DATA_YAML em config.py. A validação do script impede download automático de outro dataset.

## 3. Treinar e localizar best.pt

```powershell
python treinar.py
```

config.py concentra MODELO_BASE=yolov8n.pt, EPOCHS=100, IMG_SIZE=640, BATCH=16 e PATIENCE=20. O treinamento é de detecção; não troca para -cls. O peso base oficial pode ser baixado pelo Ultralytics no primeiro uso, se ausente. O dataset do piloto já foi preparado localmente, mas precisa ser fornecido por quem executar o projeto a partir do GitHub.

Resultados ficam em runs/estacao3/tampa/. Para preservar treinos anteriores, Ultralytics pode criar tampa2/, tampa3/, etc. O programa imprime o **caminho efetivo de model.trainer.best**, em vez de assumir runs/detect/train. Copie esse caminho para MODEL_PATH em config.py. O padrão aponta para runs/estacao3/tampa/weights/best.pt. Mensagens orientam sobre YAML inexistente, dataset inválido, falha de carga e erro de treino. Ajuste BATCH se faltar memória. Dataset inválido pode envolver problemas que só aparecem durante o treinamento.

## 4. Inferência e ciclo de inspeção

Configure MODEL_PATH e CAM_INDEX em config.py; deixe USE_SERIAL=False para começar sem Arduino.

```powershell
python inferencia.py
```

O padrão agora é **INSPECTION_MODE="manual"**. Posicione a peça, pressione **I** na janela do preview e aguarde uma decisão. Q encerra. Apertar I durante inspeção ou cooldown não inicia outro ciclo. Cada início gera um ID único; esse ID identifica a tentativa, não uma peça física rastreada pela mesa. Uma segunda solicitação manual pode inspecionar novamente a mesma peça.

```text
AGUARDANDO → I → INSPECIONANDO → CONCLUIDO (OK / NOK / INCONCLUSIVO)
                         └→ FALHA da estação (ciclo ativo termina INCONCLUSIVO)
```

- OK/NOK exigem uma única detecção válida e a mesma classe/condição por STABLE_FRAMES.
- Sem detecção, múltiplas boxes ou classe desconhecida aguardam até o prazo.
- Prazo vencido gera INCONCLUSIVO com motivo; não vira NOK.
- Falha de câmera/modelo durante ciclo gera INCONCLUSIVO e falha da estação.
- Falha antes de iniciar um ciclo não cria inspeção fictícia.
- Q durante ciclo registra cancelamento como INCONCLUSIVO.
- O estado CONCLUIDO permanece até o próximo comando; não confirma novamente a cada frame.

| Configuração | Padrão | Função |
|---|---:|---|
| CONF_THRESHOLD | 0.70 | Confiança mínima |
| STABLE_FRAMES | 5 | Frames consecutivos |
| INSPECTION_TIMEOUT_SECONDS | 5.0 | Tempo máximo de avaliação |
| COOLDOWN_SECONDS | 2.0 | Intervalo após fim antes de outro início |
| INSPECTION_MODE | manual | Comando I; automatico é demonstração |
| REARM_FRAMES | 10 | Rearme por ausência, apenas no automático |
| HEARTBEAT_SECONDS | 1.0 | Atualização do estado pelo processo |
| STATION_STALE_SECONDS | 8.0 | Prazo para indicar falta de atualização |

O prazo é verificado entre chamadas ao detector; não interrompe uma chamada bloqueada de OpenCV/YOLO. Se o processo travar, o painel perde a atualização após o prazo de heartbeat. Não é um controlador de segurança da mesa.

O modo `automatico` preserva a demonstração por presença de detecção e retirada. Ele não tem sensor real: oclusão pode causar rearme e não é possível concluir que uma peça sem detecção chegou. Para testar falta de tampa no modo manual, inicie um ciclo mesmo sem detecção. O gatilho definitivo será conectado futuramente à função iniciar() de CicloInspecao, sem assumir protocolo entre estações.

## 5. Histórico, evidência e dashboard

Em outro terminal:

```powershell
python supervisorio/app.py
```

Abra http://127.0.0.1:5000. Também funciona `python -m supervisorio.app`. Servidor local, sem debug.

O painel mostra estado da estação, disponibilidade de câmera/modelo/Serial, ciclo ativo, horário da atualização, último ciclo, motivo, duração, versão do modelo, totais, gráfico e últimas 20 tentativas. Status de equipamento é informado pelo processo; em simulação, o painel identifica SIMULAÇÃO DE EQUIPAMENTOS. Se não houver atualização, não apresenta os últimos estados como disponibilidade atual.

- GET /api/status: estado da estação, último ciclo, contagens, gráfico e histórico.
- GET /api/historico: últimas 20 inspeções.
- GET /api/inspecoes/<id>/imagem: foto registrada, quando existir.

O banco supervisorio/inspecoes.db armazena resultado, classe/confiança (podem ser vazios para inconclusivo), origem, ID único do ciclo, horário de início/fim, duração, motivo, versão do modelo, referência da imagem e estado do envio Serial. A versão inclui MODEL_VERSION e hash parcial SHA-256 do arquivo real de pesos; renomear o arquivo não muda o hash.

O gráfico inclui OK, NOK e INCONCLUSIVO. Percentuais usam todas as tentativas como denominador, não apenas as peças avaliadas. Migração do banco da versão anterior é automática e transacional, preservando IDs e registros. Faça uma cópia do banco antes de atualizar um PC que já tenha histórico importante. Pare os processos da versão anterior antes da migração.

SAVE_IMAGES=True salva o último frame limpo capturado em inspecoes_imagens/<ciclo_id>.jpg para os resultados de SAVE_IMAGE_RESULTS. O histórico oferece link da foto. Falha ao salvar imagem não elimina o resultado; fica registrada no motivo. Queda de câmera não usa foto antiga como evidência da falha. Não há política de exclusão automática de imagens: monitore o espaço e arquive quando necessário. Uma queda entre salvar a foto e gravar o banco pode deixar uma imagem sem registro.

## 6. Simulação de ciclos e falhas

O simulador usa **supervisorio/simulacao.db por padrão**. Não inicia automaticamente e não usa câmera/modelo/Serial reais. Para o dashboard consultar esse banco, configure no terminal do Flask:

```powershell
$env:ESTACAO3_DB = 'supervisorio/simulacao.db'
python supervisorio/app.py
```

Em outro terminal:

```powershell
python supervisorio/simulador.py --cenario misto --quantidade 8 --intervalo 2 --seed 42
```

Cenários: normal, sem-deteccao, camera-falha, serial-falha e misto. Cada ciclo apresenta fases aguardando/inspecionando/resultado; intervalo controla a pausa entre fases. Durações dos registros são simuladas. O modo misto alterna os quatro cenários. Não gera imagens fictícias nem confirmações físicas do Uno. Quando o simulador termina, a estação aparece SEM CONEXÃO e o histórico permanece.

Se ESTACAO3_DB estiver definido no terminal do simulador, ele usa esse banco. Para outro banco, configure a mesma variável nos dois terminais. Há uma única sessão ativa por banco: inferência e simulador simultâneos são recusados enquanto houver atualização recente. Isso impede concorrência ativa, mas executar simulação num banco com histórico real ainda mistura os totais; use o banco separado.

Para voltar à operação real, pare os processos e execute `Remove-Item Env:ESTACAO3_DB` no terminal do Flask antes de reiniciar. Consulte GUIA_DEMONSTRACAO.md para um roteiro sem hardware.

## 7. Arduino Uno / Serial com confirmação

Abra arduino/estacao3_serial/estacao3_serial.ino na Arduino IDE, selecione Uno/porta e carregue. Código continua somente recepção de resultado e LED provisório, sem I2C ou atuador.

O sketch mantém compatibilidade com `OK\n` e `NOK\n` para o Monitor Serial a 9600 baud; aceita CRLF. LED_BUILTIN ligado indica OK e desligado indica NOK, apenas demonstração. Estado inicial também deixa LED apagado.

Com SERIAL_REQUIRE_ACK=True, o Python usa protocolo correlacionado exclusivamente PC ↔ Uno:

```text
PC:      RESULTADO;<id_hexadecimal_32_caracteres>;OK\n
Arduino: ACK;<mesmo_id>;OK\n
```

NOK segue o mesmo formato. O Python só considera confirmado se o ID e o resultado coincidirem, dentro de SERIAL_ACK_TIMEOUT (1 segundo). ACK de outro ciclo é ignorado. Sem ACK, o resultado continua no banco com sem_confirmacao; não se repete o envio automaticamente. A confirmação indica recepção pelo sketch, não atuação física.

INCONCLUSIVO não é transmitido como OK/NOK; fica registrado localmente, com nao_aplicavel para Serial. O último resultado do Uno pode continuar sendo de outro ciclo, então ele não deve ser interpretado como decisão de uma nova peça. A comunicação definitiva de falhas à mesa ainda depende do professor.

Configure USE_SERIAL=True, SERIAL_PORT e BAUD_RATE. Feche o Monitor Serial antes de abrir Python. O Uno pode reiniciar ao abrir a USB; há espera configurável de 2 segundos. Falha de conexão/envio não encerra a avaliação local; o painel e o histórico mostram o problema. Reconexão exige reiniciar. Para testar o protocolo simples com um sketch antigo, SERIAL_REQUIRE_ACK=False usa OK/NOK, identificado como escrito_sem_ack, sem comprovar recepção.

## IMPLEMENTADO NESTE REPOSITÓRIO

- Captura de imagens, preparação de dataset e scripts de treinamento/inferência YOLOv8.
- Máquina de estados com ciclos identificados, estabilidade, timeout, cooldown e resultado INCONCLUSIVO separado de falhas técnicas.
- Histórico SQLite com ID único, duração, motivo, versão/hash dos pesos, evidências de imagem e situação do envio Serial.
- Estado de estação publicado por heartbeat; identificação de atualização obsoleta e proteção de sessão ativa por banco.
- Supervisório Flask com totais, três resultados, histórico, dados da estação e acesso às imagens.
- Simulador explícito com banco separado por padrão, sem controle de hardware.
- Serial USB opcional com protocolo de ACK correlacionado no código e sketch Arduino para teste com LED.
- Testes de software existentes no diretório `tests/` (a execução física do hardware não é coberta).

## VALIDADO NO PILOTO LOCAL, MAS NÃO PUBLICADO INTEGRALMENTE

- Dataset com classes `tampa_ok`/`tampa_nok`, treinamento YOLOv8n e geração de `best.pt`.
- Inferência com webcam USB e acionamento por `I`, reconhecendo as condições verde/OK e vermelho/NOK.
- Supervisório local recebendo registros da inferência pelo SQLite.
- Transmissão experimental de câmera ao vivo e visual industrial do painel; implementação local diferente da branch publicada.
- Protótipos de análises/relatórios PDF/CSV e botão web, ainda sujeitos à consolidação e testes integrados.

## PRÓXIMAS ETAPAS / PENDENTE

1. **Consolidar o código local:** unificar os scripts experimentais de câmera e controle com o Flask principal, sem abrir a webcam duas vezes; manter a operação por `inferencia.py` + `supervisorio/app.py`. Revisar e validar os relatórios e o redesign.
2. **Validar a IA independentemente:** capturar imagens novas em outra sessão, dividir por sessão, gerar matriz de confusão e medir falsos OK/NOK.
3. **Definir e simular contrato de comunicação:** início, resultado, ACK, erro e heartbeat com ID de ciclo, timeout e proteção contra duplicação. O controlador central deve impedir aprovação por ausência de resultado.
4. **Integrar o Arduino real:** testar serial, I2C, controle de ciclo e interação com a mesa em conjunto com os grupos responsáveis. O supervisor não substitui intertravamentos físicos.
5. **QR Code e rastreabilidade:** reconhecer a identidade esperada da peça e comparar com a identificação visual.
6. **Novos protótipos e dataset:** ID.4, ID. Buzz e ID. Polo fictício; avaliar diferentes abordagens de modelo usando o mesmo conjunto de teste independente.
7. **Desempenho:** medir captura, inferência, renderização, JPEG e transmissão; remover gargalos e avaliar backends otimizados para CPU. A prévia web experimental tem teto de **12 FPS**, não uma medição do FPS máximo do YOLO.
8. **Supervisório avançado:** diagnósticos, filtros, gráficos temporais e exportação CSV/PDF com dados existentes, distinguindo registros reais de simulados.

**Extensões de menor prioridade:** estoque físico/virtual, previsão de demanda, autenticação avançada, gestão de modelos e realidade aumentada. Não devem atrasar a inspeção e a integração física.

Não existe nesta branch controle definitivo dos robôs, atuadores de outras estações nem protocolo I2C final da mesa giratória.

## Testes de software

Após instalar as dependências:

```powershell
python -m compileall -q .
python -m unittest discover -s tests -v
```

Os testes usam bancos temporários, mocks de câmera/modelo/ACK e loopback Serial simples no PC. Eles não comprovam funcionamento físico da webcam, do Uno nem inferência com pesos reais.

O repositório inclui um fluxo GitHub Actions que executa a sintaxe e a suíte em Windows com Python 3.12, usando as dependências de teste e mocks de YOLO. O resultado local de 33 testes não implica aprovação da execução remota; consulte a aba Actions após publicar. A automação não testa equipamento físico nem treina um modelo.

## Autor

Davi — Estudante de Ciência da Computação (FEI) e aprendiz de mecatrônica (SENAI/Volkswagen do Brasil).

Referências de implementação: documentação oficial Ultralytics [treinamento](https://docs.ultralytics.com/modes/train/), [predição](https://docs.ultralytics.com/modes/predict/) e [trainer.best](https://docs.ultralytics.com/reference/engine/trainer/).
