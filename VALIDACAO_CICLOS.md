# Validação atual — ciclos e falhas

Versão atualizada em 07/10/2026. O relatório VALIDACAO.md descreve a primeira etapa; este arquivo descreve a versão com ciclos explícitos.

## Alterações desta etapa

Criados: ciclo.py, tests/test_ciclos.py, GUIA_DEMONSTRACAO.md e este relatório.

Atualizados: config.py, inferencia.py, banco, simulador, APIs Flask, dashboard HTML/CSS/JS, sketch Arduino, testes existentes, README e .gitignore. Captura de dataset, identificação de câmeras, treinamento, requirements.txt e gitignore original foram preservados nesta etapa.

- Modo manual por tecla I como padrão; modo automático provisório mantido.
- Máquina de estados e prazo por tentativa, com resultado INCONCLUSIVO distinto de NOK.
- UUID único para cada ciclo, duração, motivo, início/fim, versão/hash dos pesos e referência de imagem.
- Migração SQLite v1 → v2 transacional, preservando registros e IDs. Ciclos duplicados são recusados pelo banco.
- Heartbeat do processo, disponibilidade dos componentes e indicação de estado obsoleto. Sessões concorrentes no mesmo banco são recusadas enquanto houver atualização recente.
- Fotos limpas das inspeções e rota de visualização restrita à pasta de imagens. Falha da câmera não usa foto antiga como evidência.
- Protocolo opcional PC ↔ Uno com ID de ciclo e ACK correspondente. OK/NOK manual continuam aceitos pelo sketch. Nenhuma comunicação entre estações foi acrescentada.
- Simulador com fases e cenários normal, sem detecção, câmera com falha e Serial com falha. Banco de simulação separado por padrão.
- Dashboard com resultado histórico separado do estado da estação, três categorias de resultado e motivos legíveis.

## Testes de software

**33 testes passaram**, incluindo os 17 da implementação inicial adaptados aos novos campos e 16 testes adicionais.

Cobertura: estabilidade/cooldown, comando de início, prazo prevalecendo sobre frame tardio, uma conclusão por tentativa, falhas sem inventar NOK, ausência de modelo sem criar peça fictícia, queda de câmera no loop de inferência, preservação de registros na migração, ID duplicado, consultas/gravações simultâneas, sessão concorrente, heartbeat obsoleto, imagem JPEG gravada a partir de frame sintético e servida por Flask, recusa de caminho fora da pasta, falha de imagem preservando resultado, ACK correspondente, ACK de outro ciclo recusado e INCONCLUSIVO sem envio OK/NOK.

SQLite, Flask e OpenCV foram usados realmente nos testes; webcam/YOLO/ACK do Uno foram simulados nos testes que dependem deles. Loopback pyserial simples da primeira etapa permanece na suíte. Não há Arduino físico nem inferência com peso real validados.

Verificações complementares:

- compileall nos arquivos Python e node --check no JavaScript.
- Simulador executado da raiz com --cenario misto --quantidade 4 --intervalo 0 --seed 42. Gerou dois NOK e dois INCONCLUSIVOS, incluindo falha Serial identificada como simulada.
- Simulador de câmera com falha executado com fases visíveis e acrescentou um INCONCLUSIVO.
- Flask executado na porta local 5000 com banco exclusivo em work/ciclos_demo.db. APIs e arquivos estáticos responderam com HTTP 200.
- Navegador mostrou INSPECIONANDO com ID do ciclo e origem SIMULAÇÃO DE EQUIPAMENTOS. O último resultado ficou separado do ciclo ativo. A nova tentativa apareceu por polling, sem reload para receber o resultado. Após fim do processo, o estado passou a SEM CONEXÃO, sem apresentar câmera/modelo como atualmente disponíveis.
- Dados e imagens de testes não foram incluídos no banco real nem no ZIP entregue.

Dependências de teste instaladas apenas em work/deps_ciclos: Flask 3.1.3, pyserial 3.5, OpenCV 5.0.0.93, NumPy 2.5.3; Python 3.14.5. Ultralytics/PyTorch não instalados no ambiente de desenvolvimento. A pasta anterior de dependências ficou inacessível, então foi usada uma nova pasta isolada para validar a versão.

## Limitações e testes ainda necessários

- Tampa, webcam e iluminação reais; dataset rotulado; treinamento, desempenho e precisão da IA.
- Compilar/carregar o sketch no Uno e testar recepção/ACK na USB física.
- Gatilho e identificação reais de peça/ciclo pela mesa. O UUID identifica a tentativa, não uma peça física identificada externamente.
- Tempo limite verificado entre frames, sem interromper operações de câmera/YOLO bloqueadas. Heartbeat obsoleto sinaliza falta de atualização, sem comandar parada física.
- Confirmação do Uno significa recebimento, não atuação física. Não há reenvio/reconexão automática. INCONCLUSIVO fica local; não pode ser interpretado como OK/NOK nem como liberação de peça.
- Salvamento de imagens usa o último frame disponível da tentativa, não uma análise de vídeo inteira. Falha entre imagem e banco pode deixar foto sem registro. Sem limpeza automática: monitorar espaço.
- Uma sessão ativa por banco evita concorrência recente; escolher deliberadamente o banco real para simulação ainda mistura o histórico. Use banco separado.
- Servidor Flask para demonstração local. O sistema não é controlador de segurança nem autoriza movimento da mesa.

Comunicação entre estações, I2C, supervisório geral, integração física e atuadores continuam pendentes da definição do professor.
