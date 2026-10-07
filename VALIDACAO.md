> Relatório histórico da primeira implementação, antes dos ciclos explícitos. Para a versão atual, consulte VALIDACAO_CICLOS.md.

# Validação da Estação 3

Executada em 07/10/2026 no ambiente Windows de desenvolvimento. Projeto original recebido em projetosenai.rar, contendo seis arquivos, todos lidos antes das edições. O RAR original não foi alterado. A implementação está na cópia extraída em outputs/projetosenai.

## Arquivos

Criados: config.py, inferencia.py, .gitignore, supervisorio/__init__.py, supervisorio/database.py, supervisorio/app.py, supervisorio/simulador.py, supervisorio/templates/index.html, supervisorio/static/style.css, supervisorio/static/dashboard.js, arduino/estacao3_serial/estacao3_serial.ino, tests/test_estacao3.py e este relatório.

Alterados: captura_dataset.py (cópia limpa do frame, sequência segura, configuração central e verificação de gravação), treinar.py (configuração, erros básicos e caminho real do peso), listar_cameras.py (mesmo comportamento dentro de main, sem abrir câmera ao importar) e README.md (estado real e instruções).

Preservados sem alteração: requirements.txt e gitignore original. .gitignore foi acrescentado porque o nome original sem ponto não é reconhecido pelo Git.

## Testes executados e resultados

- Compilação de todos os arquivos Python com compileall: passou.
- Importação dos módulos próprios, incluindo captura, utilitário de câmeras, treinamento, inferência, banco, Flask e simulador: passou, sem iniciar captura ou simulação automaticamente.
- unittest: **17 testes passaram**. Cobrem banco vazio, persistência, validação de valores, percentuais, gráfico, histórico, rotas e arquivos estáticos; acesso simultâneo com seis threads (40 gravações intercaladas com 20 leituras); estabilidade, oscilação, cooldown e rearme; fluxo com uma confirmação em oito frames da mesma peça; conversão de boxes simuladas; captura do mesmo frame limpo; sequência com lacunas; modelo ausente; Serial indisponível; falha de envio sem perda do registro; caminho de best.pt e erros de treinamento por mocks.
- Serial pyserial real em loop://: comprovada escrita/leitura de NOK seguido de newline no PC, integrada à gravação no SQLite. Não comprova recepção física pelo Uno.
- Simulador executado da raiz com quantidade 8 e seed 42, depois quantidade 1 e seed 1: nove registros explícitos, todos com origem simulador, em banco exclusivo dentro de work/. Nenhum dado de teste foi incluído no banco padrão do projeto entregue.
- Flask iniciado pelo comando python supervisorio/app.py, sem debug. GET /, /api/status, /api/historico e arquivos estáticos responderam corretamente. APIs também verificadas por requisições HTTP ao servidor real.
- Dashboard conferido no navegador: última inspeção, origem, confiança, totais, histórico e barras renderizados. Após nova inserção, passou de 8 para 9 inspeções, de NOK para OK, com OK=5, NOK=4, percentuais 55,6%/44,4%, sem reload. Captura em outputs/dashboard-estacao3.png.
- JavaScript verificado com node --check: passou.
- python inferencia.py sem best.pt e python treinar.py sem data.yaml: mensagens orientativas, código de saída 1, sem traceback.
- Caminhos configurados a partir da raiz física de config.py; app e simulador têm suporte à execução direta pela raiz ou como módulo.

As dependências de teste foram instaladas em work/test_deps, sem alterar o Python global nem adicionar dependências ao requirements original. Ambiente: Python 3.14.5; Flask 3.1.3, pyserial 3.5, OpenCV 5.0.0.93 e NumPy 2.5.3. Ultralytics/PyTorch não foram instalados no ambiente de desenvolvimento; os testes do adaptador YOLO e treino usam mocks. Recomenda-se instalar o requirements completo no PC de operação com Python compatível com PyTorch/Ultralytics, como 3.11/3.12.

## Não validado fisicamente

- Webcam USB e backend MSMF, qualidade de imagem, iluminação e estabilidade na mesa real.
- Dataset Roboflow real, treinamento YOLOv8, leitura de pesos reais, desempenho ou acurácia. Não foram baixados datasets nem treinados modelos irrelevantes.
- Arduino IDE/toolchain não disponível: sketch não foi compilado nem carregado em Uno. LED e recepção Serial precisam de teste físico.
- Comunicação entre estações e integração física final dependem das decisões do professor. Não há I2C, controle de robôs ou atuadores.

## Limitações operacionais documentadas

O painel mostra a última inspeção persistida, não heartbeat de câmera. O rearme por ausência é provisório e pode confundir oclusões longas com retirada; requer calibração e posterior gatilho físico. Serial é envio simples sem ACK/reconexão automática. Contagens incluem todos os registros do banco escolhido; use banco separado para simulação. O servidor Flask é para demonstração local.
