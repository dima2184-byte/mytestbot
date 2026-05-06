#!/bin/bash
set -e

# Validate required env vars
for var in TG_TOKEN ANTHROPIC_KEY GH_USER GH_TOKEN REPO_NAME; do
  if [ -z "${!var}" ]; then
    echo "ERROR: $var is not set"
    exit 1
  fi
done

apt update && apt install -y git python3 python3-pip python3-venv

cd /root
git clone "https://${GH_TOKEN}@github.com/${GH_USER}/${REPO_NAME}.git"
cd "/root/${REPO_NAME}"
git config user.name "auto-deploy"
git config user.email "deploy@server"

cat > bot.py <<'PYEOF'
import os, logging
for v in ("HTTP_PROXY","HTTPS_PROXY","http_proxy","https_proxy","ALL_PROXY","all_proxy"):
    os.environ.pop(v, None)
from dotenv import load_dotenv
import anthropic
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
history: dict[int, list[dict]] = {}

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привіт! Я бот на Claude. Питай будь-що.")

async def reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    history.pop(update.effective_user.id, None)
    await update.message.reply_text("Історію очищено.")

async def chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    history.setdefault(uid, []).append({"role": "user", "content": update.message.text})
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        resp = claude.messages.create(
            model="claude-opus-4-7", max_tokens=1024,
            system="Ти доброзичливий асистент. Відповідай коротко та по суті українською.",
            messages=history[uid],
        )
        text = resp.content[0].text
        history[uid].append({"role": "assistant", "content": text})
        history[uid] = history[uid][-20:]
        await update.message.reply_text(text)
    except Exception:
        log.exception("error")
        await update.message.reply_text("Помилка. Спробуй ще раз.")

def main():
    app = ApplicationBuilder().token(os.environ["TELEGRAM_BOT_TOKEN"]).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    log.info("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
PYEOF

cat > requirements.txt <<'EOF'
anthropic>=0.40.0
python-telegram-bot>=21.0
python-dotenv>=1.0.0
EOF

cat > .gitignore <<'EOF'
.env
venv/
__pycache__/
*.pyc
EOF

cat > .env <<EOF
TELEGRAM_BOT_TOKEN=${TG_TOKEN}
ANTHROPIC_API_KEY=${ANTHROPIC_KEY}
GITHUB_TOKEN=${GH_TOKEN}
EOF

cat > CLAUDE.md <<'EOF'
# Telegram-бот на Claude

Головний файл — bot.py. Залежності — requirements.txt.

## Сервер
Бот працює на VPS DigitalOcean.
- Шлях: /root/my-bot
- Сервіс: mybot.service (systemd)
- Автодеплой: /root/autodeploy.sh запускається щохвилини,
  робить git pull і перезапускає сервіс при змінах.

## Workflow
Усе через GitHub: коміт у main → за хвилину сервер оновиться.
Руками до сервера не лізьмо.

## Користувач
Говорить українською, не програміст — пояснювати простими словами.
EOF

python3 -m venv venv
./venv/bin/pip install -q -r requirements.txt

git add bot.py requirements.txt .gitignore CLAUDE.md
git commit -m "Initial bot setup"
git branch -M main
git push -u origin main

cat > /etc/systemd/system/mybot.service <<EOF
[Unit]
Description=Telegram Bot on Claude
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/${REPO_NAME}
ExecStart=/root/${REPO_NAME}/venv/bin/python /root/${REPO_NAME}/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

cat > /root/autodeploy.sh <<EOF
#!/bin/bash
cd /root/${REPO_NAME} || exit 1
BEFORE=\$(git rev-parse HEAD)
git pull --quiet
AFTER=\$(git rev-parse HEAD)
if [ "\$BEFORE" != "\$AFTER" ]; then
    /root/${REPO_NAME}/venv/bin/pip install -q -r requirements.txt
    systemctl restart mybot.service
fi
EOF
chmod +x /root/autodeploy.sh

cat > /etc/systemd/system/autodeploy.service <<'EOF'
[Unit]
Description=Auto deploy from GitHub
[Service]
Type=oneshot
ExecStart=/root/autodeploy.sh
EOF

cat > /etc/systemd/system/autodeploy.timer <<'EOF'
[Unit]
Description=Run autodeploy every minute
[Timer]
OnBootSec=1min
OnUnitActiveSec=1min
[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now mybot.service
systemctl enable --now autodeploy.timer

echo ""
echo "============================================="
echo "✅ ВСЕ ГОТОВО!"
echo "Відкрий Telegram, знайди свого бота, напиши /start"
echo "============================================="
