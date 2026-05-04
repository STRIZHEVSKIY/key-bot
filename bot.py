import os
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ─── Настройки ───────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "8626239823:AAGPEdF_tVK9qtmSyYrz83bROTK3vN17xVA")

# ID платного сообщества для проверки подписки.
# Чтобы узнать chat_id: добавьте бота в сообщество как админа,
# затем перешлите любое сообщение из группы боту @userinfobot
# или используйте https://api.telegram.org/bot<TOKEN>/getUpdates
# Примеры формата: -1001234567890 (для супергрупп/каналов)
PAID_CHANNEL_ID = int(os.getenv("PAID_CHANNEL_ID", "-1003880921089"))  # ← ЗАМЕНИТЕ НА РЕАЛЬНЫЙ ID
PAID_CHANNEL_LINK = "https://t.me/KayoAAA"

# Пути к файлам (рядом со скриптом)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KEYS_FILE = os.path.join(BASE_DIR, "activation-keys.txt")
USED_FILE = os.path.join(BASE_DIR, "used-keys.json")  # {user_id: key}

# ─── Логирование ─────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ─── Утилиты для работы с файлами ────────────────────────────────────────────
def load_keys() -> list[str]:
    """Загружает список доступных ключей из файла."""
    if not os.path.exists(KEYS_FILE):
        return []
    with open(KEYS_FILE, "r", encoding="utf-8") as f:
        keys = [line.strip() for line in f if line.strip()]
    return keys


def save_keys(keys: list[str]) -> None:
    """Сохраняет оставшиеся ключи в файл."""
    with open(KEYS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(keys) + ("\n" if keys else ""))


def load_used() -> dict[str, str]:
    """Загружает словарь {user_id: key} уже выданных ключей."""
    if not os.path.exists(USED_FILE):
        return {}
    with open(USED_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_used(used: dict[str, str]) -> None:
    """Сохраняет словарь выданных ключей."""
    with open(USED_FILE, "w", encoding="utf-8") as f:
        json.dump(used, f, indent=2, ensure_ascii=False)


# ─── Проверка подписки ────────────────────────────────────────────────────────
async def check_subscription(user_id: int, bot) -> bool:
    """Проверяет, является ли пользователь участником платного сообщества."""
    try:
        member = await bot.get_chat_member(chat_id=PAID_CHANNEL_ID, user_id=user_id)
        # Допустимые статусы: участник, админ, создатель
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        logger.warning(
            "Не удалось проверить подписку user=%s: %s", user_id, e
        )
        return False


# ─── Обработчики команд ──────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Приветственное сообщение с кнопкой получения ключа."""
    keyboard = [
        [InlineKeyboardButton("🔑 Получить ключ", callback_data="get_key")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "👋 Привет!\n\n"
        "Я бот для выдачи ключей активации.\n"
        "Нажми кнопку ниже, чтобы получить свой ключ.\n\n"
        "⚠️ Для получения ключа необходимо быть участником "
        f"[платного сообщества]({PAID_CHANNEL_LINK}).\n"
        "⚠️ Каждый пользователь может получить только **один** ключ.",
        parse_mode="Markdown",
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )


async def handle_get_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка нажатия кнопки «Получить ключ»."""
    query = update.callback_query

    user_id = str(query.from_user.id)
    username = query.from_user.username or query.from_user.first_name

    # Проверяем подписку на платное сообщество
    is_subscribed = await check_subscription(int(user_id), context.bot)
    if not is_subscribed:
        keyboard = [
            [InlineKeyboardButton("💎 Купить доступ", url=PAID_CHANNEL_LINK)],
            [InlineKeyboardButton("🔄 Я уже подписан — проверить", callback_data="get_key")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.edit_message_text(
                "🔒 *Доступ ограничен!*\n\n"
                "Для получения ключа необходимо быть участником "
                "платного сообщества.\n\n"
                "👉 Нажмите кнопку ниже, чтобы приобрести доступ.\n"
                "После вступления вернитесь и нажмите *«Я уже подписан»*.",
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
        except Exception:
            # Сообщение уже содержит этот текст — показываем всплывающее уведомление
            await query.answer(
                "❌ Вы не подписаны на сообщество!\n"
                "Сначала купите доступ по кнопке ниже.",
                show_alert=True,
            )
        return

    await query.answer()

    used = load_used()

    # Проверяем, получал ли пользователь ключ ранее
    if user_id in used:
        await query.edit_message_text(
            f"❗ Вы уже получили ключ:\n\n"
            f"`{used[user_id]}`\n\n"
            f"Повторная выдача невозможна.",
            parse_mode="Markdown",
        )
        return

    # Загружаем доступные ключи
    keys = load_keys()

    if not keys:
        await query.edit_message_text(
            "😔 К сожалению, все ключи закончились.\n"
            "Попробуйте позже или свяжитесь с администратором."
        )
        return

    # Выдаём первый ключ из списка
    key = keys.pop(0)

    # Сохраняем изменения
    save_keys(keys)
    used[user_id] = key
    save_used(used)

    remaining = len(keys)
    logger.info(
        "Ключ выдан: user=%s (@%s), key=%s, осталось=%d",
        user_id, username, key, remaining,
    )

    await query.edit_message_text(
        f"✅ Ваш ключ активации:\n\n"
        f"`{key}`\n\n"
        f"📋 Нажмите на ключ, чтобы скопировать.\n"
        f"🔒 Сохраните его — повторная выдача невозможна.",
        parse_mode="Markdown",
    )


async def getkey_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выдача ключа через команду /getkey (из меню)."""
    user_id = str(update.effective_user.id)
    username = update.effective_user.username or update.effective_user.first_name

    # Проверяем подписку на платное сообщество
    is_subscribed = await check_subscription(int(user_id), context.bot)
    if not is_subscribed:
        keyboard = [
            [InlineKeyboardButton("💎 Купить доступ", url=PAID_CHANNEL_LINK)],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🔒 *Доступ ограничен!*\n\n"
            "Для получения ключа необходимо быть участником "
            "платного сообщества.\n\n"
            "👉 Нажмите кнопку ниже, чтобы приобрести доступ.\n"
            "После вступления используйте /getkey повторно.",
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )
        return

    used = load_used()

    if user_id in used:
        await update.message.reply_text(
            f"❗ Вы уже получили ключ:\n\n"
            f"`{used[user_id]}`\n\n"
            f"Повторная выдача невозможна.",
            parse_mode="Markdown",
        )
        return

    keys = load_keys()

    if not keys:
        await update.message.reply_text(
            "😔 К сожалению, все ключи закончились.\n"
            "Попробуйте позже или свяжитесь с администратором."
        )
        return

    key = keys.pop(0)
    save_keys(keys)
    used[user_id] = key
    save_used(used)

    remaining = len(keys)
    logger.info(
        "Ключ выдан: user=%s (@%s), key=%s, осталось=%d",
        user_id, username, key, remaining,
    )

    await update.message.reply_text(
        f"✅ Ваш ключ активации:\n\n"
        f"`{key}`\n\n"
        f"📋 Нажмите на ключ, чтобы скопировать.\n"
        f"🔒 Сохраните его — повторная выдача невозможна.",
        parse_mode="Markdown",
    )


async def mykey(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает ранее выданный ключ пользователя."""
    user_id = str(update.effective_user.id)
    used = load_used()

    if user_id in used:
        await update.message.reply_text(
            f"🔑 Ваш ключ:\n\n`{used[user_id]}`",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            "❌ У вас пока нет ключа.\nИспользуйте /start, чтобы получить ключ."
        )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает количество оставшихся ключей (для администрирования)."""
    keys = load_keys()
    used = load_used()
    await update.message.reply_text(
        f"📊 Статистика:\n\n"
        f"🔑 Доступно ключей: {len(keys)}\n"
        f"👤 Выдано ключей: {len(used)}"
    )


# ─── Установка меню команд ────────────────────────────────────────────────────
async def post_init(application: Application) -> None:
    """Устанавливает меню команд бота при запуске."""
    await application.bot.set_my_commands([
        BotCommand("start", "🚀 Старт"),
        BotCommand("getkey", "🔑 Выдать ключ"),
        BotCommand("mykey", "👀 Просмотр ключа"),
    ])
    logger.info("Меню команд установлено.")


# ─── Запуск бота ──────────────────────────────────────────────────────────────
def main() -> None:
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("=" * 50)
        print("ОШИБКА: Укажите токен бота!")
        print()
        print("Варианты:")
        print("1. Установите переменную окружения:")
        print('   set BOT_TOKEN=ваш_токен')
        print("2. Замените YOUR_BOT_TOKEN_HERE в bot.py")
        print()
        print("Получить токен можно у @BotFather в Telegram.")
        print("=" * 50)
        return

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Регистрируем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("getkey", getkey_command))
    app.add_handler(CommandHandler("mykey", mykey))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CallbackQueryHandler(handle_get_key, pattern="^get_key$"))

    logger.info("Бот запущен! Нажмите Ctrl+C для остановки.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
