import os, logging, json, subprocess, datetime, re
from pathlib import Path

for v in ("HTTP_PROXY","HTTPS_PROXY","http_proxy","https_proxy","ALL_PROXY","all_proxy"):
    os.environ.pop(v, None)

from dotenv import load_dotenv
import anthropic
import httpx
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
NOTES_DIR = Path(__file__).parent / "notes"
NOTES_DIR.mkdir(exist_ok=True)

SYSTEM_PROMPT = """Ти — бізнес-асистент українською мовою.
Допомагаєш з аналізом, плануванням, нотатками, підрахунками та пошуком інформації.
Відповідай чітко, по суті, без зайвої води.
Якщо потрібні розрахунки, нотатки або веб-пошук — використовуй інструменти.
Звертайся на "ти"."""

TOOLS = [
    {
        "name": "calculate",
        "description": "Виконує математичні розрахунки. Приймає вираз у вигляді рядка.",
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "Математичний вираз, наприклад: '2 * (3 + 4)'"}
            },
            "required": ["expression"]
        }
    },
    {
        "name": "save_note",
        "description": "Зберігає нотатку для користувача.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer", "description": "ID користувача Telegram"},
                "title": {"type": "string", "description": "Заголовок нотатки"},
                "content": {"type": "string", "description": "Текст нотатки"}
            },
            "required": ["user_id", "title", "content"]
        }
    },
    {
        "name": "list_notes",
        "description": "Показує список всіх нотаток користувача.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer", "description": "ID користувача Telegram"}
            },
            "required": ["user_id"]
        }
    },
    {
        "name": "delete_note",
        "description": "Видаляє нотатку за заголовком.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer", "description": "ID користувача Telegram"},
                "title": {"type": "string", "description": "Заголовок нотатки для видалення"}
            },
            "required": ["user_id", "title"]
        }
    },
    {
        "name": "get_datetime",
        "description": "Повертає поточну дату та час українською мовою.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "read_url",
        "description": "Читає текстовий вміст веб-сторінки за URL.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL сторінки для читання"}
            },
            "required": ["url"]
        }
    }
]


def _user_notes_path(user_id: int) -> Path:
    p = NOTES_DIR / str(user_id)
    p.mkdir(exist_ok=True)
    return p


def tool_calculate(expression: str) -> str:
    try:
        allowed = re.compile(r'^[\d\s\+\-\*\/\(\)\.\,\%\^]+$')
        if not allowed.match(expression.replace("**", "^")):
            return "Помилка: дозволені лише числа та математичні оператори."
        result = eval(expression, {"__builtins__": {}})  # noqa: S307
        return f"Результат: {result}"
    except Exception as e:
        return f"Помилка обчислення: {e}"


def tool_save_note(user_id: int, title: str, content: str) -> str:
    path = _user_notes_path(user_id) / f"{title}.txt"
    path.write_text(content, encoding="utf-8")
    return f"Нотатку '{title}' збережено."


def tool_list_notes(user_id: int) -> str:
    path = _user_notes_path(user_id)
    files = list(path.glob("*.txt"))
    if not files:
        return "Нотаток ще немає."
    lines = [f"📝 {f.stem}" for f in sorted(files)]
    return "Твої нотатки:\n" + "\n".join(lines)


def tool_delete_note(user_id: int, title: str) -> str:
    path = _user_notes_path(user_id) / f"{title}.txt"
    if not path.exists():
        return f"Нотатку '{title}' не знайдено."
    path.unlink()
    return f"Нотатку '{title}' видалено."


def tool_get_datetime() -> str:
    ua_months = [
        "січня","лютого","березня","квітня","травня","червня",
        "липня","серпня","вересня","жовтня","листопада","грудня"
    ]
    ua_days = ["понеділок","вівторок","середа","четвер","п'ятниця","субота","неділя"]
    now = datetime.datetime.now()
    return (
        f"{ua_days[now.weekday()]}, {now.day} {ua_months[now.month-1]} {now.year} р., "
        f"{now.strftime('%H:%M')}"
    )


def tool_read_url(url: str) -> str:
    try:
        resp = httpx.get(url, timeout=15, follow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        lines = [l for l in text.splitlines() if l.strip()]
        return "\n".join(lines[:150])
    except Exception as e:
        return f"Помилка читання URL: {e}"


def run_tool(name: str, inputs: dict) -> str:
    if name == "calculate":
        return tool_calculate(inputs["expression"])
    if name == "save_note":
        return tool_save_note(inputs["user_id"], inputs["title"], inputs["content"])
    if name == "list_notes":
        return tool_list_notes(inputs["user_id"])
    if name == "delete_note":
        return tool_delete_note(inputs["user_id"], inputs["title"])
    if name == "get_datetime":
        return tool_get_datetime()
    if name == "read_url":
        return tool_read_url(inputs["url"])
    return f"Невідомий інструмент: {name}"


history: dict[int, list[dict]] = {}


async def run_agent(uid: int, messages: list[dict]) -> str:
    while True:
        resp = claude.messages.create(
            model="claude-opus-4-7",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        if resp.stop_reason == "end_turn":
            for block in resp.content:
                if hasattr(block, "text"):
                    return block.text
            return "Немає відповіді."

        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": resp.content})
            tool_results = []
            for block in resp.content:
                if block.type == "tool_use":
                    result = run_tool(block.name, block.input)
                    log.info("Tool %s → %s", block.name, result[:80])
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            messages.append({"role": "user", "content": tool_results})
            continue

        return "Помилка агента."


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт! Я бізнес-асистент на Claude.\n\n"
        "Можу:\n"
        "• рахувати і аналізувати\n"
        "• зберігати нотатки (/notes)\n"
        "• читати веб-сторінки\n"
        "• обробляти фото\n"
        "• показувати дату/час\n\n"
        "Просто напиши що потрібно!"
    )


async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    history.pop(update.effective_user.id, None)
    await update.message.reply_text("Історію очищено.")


async def cmd_notes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    try:
        await update.message.reply_text(tool_list_notes(uid))
    except Exception:
        log.exception("cmd_notes error")
        await update.message.reply_text("Помилка при завантаженні нотаток.")


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    history.setdefault(uid, []).append({"role": "user", "content": update.message.text})
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        reply = await run_agent(uid, history[uid])
        history[uid].append({"role": "assistant", "content": reply})
        history[uid] = history[uid][-30:]
        await update.message.reply_text(reply)
    except Exception:
        log.exception("Agent error")
        await update.message.reply_text("Помилка. Спробуй ще раз.")


async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        photo = update.message.photo[-1]
        file = await ctx.bot.get_file(photo.file_id)
        img_bytes = await file.download_as_bytearray()

        import base64
        img_b64 = base64.standard_b64encode(bytes(img_bytes)).decode()
        caption = update.message.caption or "Що зображено на цьому фото? Опиши детально українською."

        resp = claude.messages.create(
            model="claude-opus-4-7",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}},
                    {"type": "text", "text": caption}
                ]
            }]
        )
        reply = resp.content[0].text
        history.setdefault(uid, []).append({"role": "user", "content": caption})
        history[uid].append({"role": "assistant", "content": reply})
        await update.message.reply_text(reply)
    except Exception:
        log.exception("Photo error")
        await update.message.reply_text("Не вдалося обробити фото.")


def main():
    app = ApplicationBuilder().token(os.environ["TELEGRAM_BOT_TOKEN"]).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("notes", cmd_notes))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    log.info("Agent bot started with tools")
    app.run_polling()


if __name__ == "__main__":
    main()
