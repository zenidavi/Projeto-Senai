# Inspeção Automática de Tampa com Visão Computacional

Projeto desenvolvido como aluno SENAI em parceria com a Volkswagen do Brasil, como parte de uma estação de uma mesa giratória automatizada com robôs. A estação usa uma câmera e um modelo de visão computacional (YOLO) para inspecionar se a tampa de uma caixa foi fechada corretamente, comunicando o resultado a um Arduino que direciona a peça para a linha correta.

## Contexto do projeto

A mesa giratória gira até posicionar cada peça na estação correspondente. Nesta estação, a peça permanece parada enquanto a câmera captura a imagem e o sistema decide se a tampa está OK ou NOK (não conforme). Com base nessa decisão, um sinal é enviado via serial para um Arduino Uno, que aciona o mecanismo de separação física da peça.

## Arquitetura

```
Webcam USB → Python (YOLO) → Decisão OK/NOK → Serial → Arduino Uno → Atuador
                    ↓
              Banco de dados (SQLite)
                    ↓
         Supervisório web (Flask) → Painel em tempo real
```

## Funcionalidades

- **Captura de dataset**: script para coleta de imagens direto da webcam, já organizadas por classe
- **Treinamento**: modelo YOLOv8 treinado para classificar tampa OK / NOK
- **Inferência em tempo real**: leitura contínua da webcam com decisão e envio serial ao Arduino
- **Supervisório web**: painel com status ao vivo, contadores e histórico gráfico das inspeções

## Tecnologias

- Python 3
- [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics)
- OpenCV
- Flask + SQLite
- Roboflow (rotulagem do dataset)
- Arduino Uno (comunicação serial)

## Estrutura do repositório

```
├── captura_dataset.py     # Captura de imagens via webcam para o dataset
├── listar_cameras.py      # Utilitário para identificar índices de câmera
├── treinar.py              # Treinamento do modelo YOLO
├── inferencia.py           # Inferência em tempo real + comunicação serial
└── supervisorio/
    ├── app.py               # Servidor Flask
    ├── database.py          # Camada de banco de dados (SQLite)
    ├── simulador.py         # Simulador de inspeções para testes
    └── templates/
        └── index.html       # Painel web
```

## Como executar

```bash
# Clonar o repositório
git clone https://github.com/SEU_USUARIO/senai-vw-inspecao-tampa.git
cd senai-vw-inspecao-tampa

# Criar e ativar ambiente virtual
python -m venv venv
venv\Scripts\activate      # Windows
source venv/bin/activate   # Linux/Mac

# Instalar dependências
pip install -r requirements.txt
```

### Captura do dataset
```bash
python captura_dataset.py
```

### Treinamento
Após rotular o dataset no Roboflow e exportar no formato YOLOv8:
```bash
python treinar.py
```

### Supervisório
```bash
cd supervisorio
python app.py
```
Acesse `http://localhost:5000` no navegador.

## Autor

Davi — Estudante de Ciência da Computação (FEI) e aprendiz de mecatrônica (SENAI/Volkswagen do Brasil)
