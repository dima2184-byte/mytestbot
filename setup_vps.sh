#!/bin/bash
set -e

echo "=============================="
echo " VPS Setup Script"
echo "=============================="

# 1. Оновлення системи
echo ""
echo "[1/4] Оновлення системи..."
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y

# 2. Встановлення Python 3, pip, git, venv
echo ""
echo "[2/4] Встановлення Python3, pip, git, venv..."
apt-get install -y python3 python3-pip python3-venv git

# 3. Створення користувача bot
echo ""
echo "[3/4] Створення користувача bot..."
if id "bot" &>/dev/null; then
    echo "Користувач bot вже існує"
else
    useradd -m -s /bin/bash bot
    echo "Користувача bot створено"
fi

# 4. Показати версії
echo ""
echo "[4/4] Версії встановленого ПЗ:"
echo -n "Python: "; python3 --version
echo -n "pip:    "; pip3 --version
echo -n "git:    "; git --version
echo ""
echo "=============================="
echo " Готово! VPS налаштовано."
echo "=============================="
