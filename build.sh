#!/bin/bash
set -e

echo "🔹 Usando Python 3.11.9 definido pelo .python-version"

# Ativa o ambiente virtual se existir
if [ -d ".venv" ]; then
  echo "🔹 Ativando ambiente virtual existente..."
  source .venv/bin/activate
else
  echo "🔹 Criando novo ambiente virtual..."
  python3.11 -m venv .venv
  source .venv/bin/activate
fi

# Atualiza pip dentro do venv
pip install --upgrade pip

# Instala dependências
echo "🔹 Instalando dependências..."
pip install -r requirements.txt

# Roda o bot
echo "🔹 Iniciando o bot..."
python main.py