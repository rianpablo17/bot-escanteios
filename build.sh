#!/bin/bash
set -e  # Para o script parar se algum comando falhar

echo "🔹 Instalando Python 3.11..."
# Instala o Python 3.11 via apt-get (Render roda Debian/Ubuntu)
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3.11-dev python3-pip

# Define o Python 3.11 como padrão no script
alias python=python3.11
alias pip=pip3

echo "🔹 Versão do Python: $(python --version)"
echo "🔹 Versão do pip: $(pip --version)"

# Cria um ambiente virtual (opcional, mas recomendado)
python -m venv .venv
source .venv/bin/activate

# Atualiza pip dentro do venv
pip install --upgrade pip

# Instala dependências do bot
echo "🔹 Instalando dependências..."
pip install -r requirements.txt

# Roda o bot
echo "🔹 Iniciando o bot..."
python main.py