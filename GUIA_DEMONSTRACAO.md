# Roteiro de demonstração sem tampa pronta

Este roteiro demonstra o fluxo de software, não a precisão de uma IA treinada nem a conexão com equipamento físico. Todos os registros estão identificados como simulador.

## Preparação

Abra dois terminais na pasta do projeto e ative o ambiente virtual. Para o painel basta Flask instalado. O simulador usa a biblioteca padrão de Python.

Terminal 1:

```powershell
$env:ESTACAO3_DB = 'supervisorio/simulacao.db'
python supervisorio/app.py
```

Abra http://127.0.0.1:5000.

Terminal 2:

```powershell
python supervisorio/simulador.py --cenario misto --quantidade 8 --intervalo 2 --seed 42
```

Se ESTACAO3_DB já estiver definido nesse terminal, use o mesmo caminho do terminal 1. Sem a variável, o simulador escolhe supervisorio/simulacao.db.

## O que mostrar e explicar

1. O estado muda de Aguardando para Inspecionando. Enquanto isso, o cartão de resultado mantém o último ciclo encerrado, identificado como histórico.
2. Operação normal produz OK ou NOK, ID de ciclo, confiança e duração.
3. Sem detecção, a tentativa termina INCONCLUSIVO por tempo limite; não reprova a peça automaticamente.
4. Falha de câmera gera estado Falha e resultado INCONCLUSIVO, com motivo visível.
5. Falha Serial mantém o resultado da inspeção e marca falha de envio simulada no histórico.
6. Histórico, totais e gráfico atualizam sem recarregar a página.
7. Ao terminar o simulador, o estado indica Sem conexão e os resultados anteriores continuam no histórico.

Cada fase permanece pelo tempo de --intervalo. Não são chamadas reais ao YOLO, ao Arduino ou à câmera. As durações registradas são tempos simulados.

## Demonstrar um cenário específico

```powershell
python supervisorio/simulador.py --cenario sem-deteccao --quantidade 1 --intervalo 5
python supervisorio/simulador.py --cenario camera-falha --quantidade 1 --intervalo 5
python supervisorio/simulador.py --cenario serial-falha --quantidade 1 --intervalo 5
```

Execute um comando por vez. Não há uso de Serial nem imagem fictícia em nenhum cenário.

## Quando o hardware estiver disponível

Configure webcam e best.pt em config.py. Execute python inferencia.py, posicione a peça e pressione I para iniciar o ciclo. Q encerra. A tecla é um gatilho provisório: o professor ainda precisa definir o evento da mesa que iniciará a inspeção.

Para operação real, pare o Flask e remova ESTACAO3_DB do terminal (`Remove-Item Env:ESTACAO3_DB`) antes de reiniciar. O banco real padrão é supervisorio/inspecoes.db. Não use o simulador nesse banco.
