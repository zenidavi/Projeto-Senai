# O que foi desenvolvido na Estação 3

A responsabilidade deste software é avaliar a condição da tampa, registrar o resultado e disponibilizá-lo ao supervisório e, opcionalmente, ao Arduino. A estação não comanda a mesa, robôs ou mecanismos de separação.

## O que já existia e foi preservado

O projeto recebido tinha identificação de câmeras, captura de imagens, treinamento, dependências e README. Os scripts existentes foram mantidos com as melhorias necessárias:

| Arquivo | Mudança | Motivo |
|---|---|---|
| captura_dataset.py | Salva a cópia limpa do frame mostrado, sem nova leitura | Evitar salvar uma imagem diferente do preview |
| captura_dataset.py | Retoma a maior sequência e verifica a gravação | Evitar sobrescrita ao remover imagens e informar falhas |
| listar_cameras.py | Execução protegida por main | Permitir importar o módulo sem abrir câmeras |
| treinar.py | Configuração central, mensagens de erro e pasta de execução | Facilitar uso pelo grupo e preservar treinos anteriores |
| treinar.py | Exibe o best.pt realmente gerado | Não assumir um caminho fixo de treino |
| README.md | Instruções e estado real de implementação | Separar software disponível de validação física pendente |

O modelo base continua yolov8n.pt, em Object Detection. requirements.txt continua com as quatro dependências originais; SQLite usa o módulo padrão sqlite3. O arquivo gitignore original foi preservado e .gitignore foi criado com o nome reconhecido pelo Git.

## Partes acrescentadas e sua finalidade

- config.py: reúne caminhos, câmera, limiar, tempo de inspeção e Serial.
- ciclo.py: gerencia uma tentativa com início explícito, estabilidade, prazo e conclusão única.
- inferencia.py: conecta webcam e YOLO ao ciclo, grava histórico/imagem e transmite resultado quando habilitado.
- supervisorio/database.py: persistência, migração do histórico e leitura consistente para o painel.
- supervisorio/app.py e interface: painel local com polling, APIs, gráfico e acesso às imagens.
- supervisorio/simulador.py: demonstra o fluxo de ciclos e falhas sem equipamento.
- arduino/estacao3_serial: sketch de recepção Serial e confirmação; LED apenas provisório.
- tests/: suíte de software com bancos temporários e simulações dos componentes ausentes.
- .github/workflows/tests.yml: execução da suíte por GitHub Actions em pushes e pull requests.

## Como o ciclo funciona

No modo manual, I inicia uma tentativa. Uma detecção única e estável pode gerar OK ou NOK. Se o prazo vencer sem condição válida, o resultado é INCONCLUSIVO. Falha técnica da estação fica separada do resultado da peça.

Um UUID identifica a tentativa. O histórico inclui duração, motivo, origem, versão/hash do modelo e imagem, quando disponível. Um novo comando manual pode avaliar novamente a mesma peça: o ID ainda não identifica uma peça física pelo sistema da mesa.

O painel mostra o estado atual informado pelo processo e o último ciclo encerrado em cartões separados. Se o processo parar ou deixar de atualizar, indica falta de conexão; o resultado anterior permanece como histórico.

## Comunicação com Arduino

A conexão é apenas Serial USB PC ↔ Uno e fica desabilitada por padrão. Com ACK habilitado, mensagem e resposta incluem o ID do ciclo. Confirmação significa recepção pelo sketch; não comprova atuação física. INCONCLUSIVO não é enviado como NOK. Nenhum protocolo entre estações foi implementado.

## O que foi validado e o que falta

A suíte local tem 33 testes aprovados e o dashboard foi verificado com simulação. Isso valida o fluxo de software, não a precisão de uma IA treinada ou hardware físico. Consulte VALIDACAO_CICLOS.md para a evidência e as limitações.

Faltam tampa real, dataset rotulado, treinamento, avaliação de precisão, testes de câmera/iluminação, compilação e teste do Uno. O professor ainda precisa definir o gatilho da mesa, comunicação entre estações e interface física. I2C, atuadores, robôs e supervisório geral não foram implementados.
