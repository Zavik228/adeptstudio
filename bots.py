import asyncio
from datetime import datetime
import ftplib
import io
import logging
import math
import os
import sqlite3
from typing import Any, Awaitable, Callable, Dict, List, Tuple

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatMemberStatus, ParseMode
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyParameters,
    TelegramObject,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from PIL import Image, ImageDraw, ImageFont

# =====================================================================
# ⚙️ КОНФИГУРАЦИЯ СТУДИИ (ТВОИ ДАННЫЕ СОХРАНЕНЫ)
# =====================================================================
BOT_TOKEN = "8584088415:AAGBxzQI81QRN-_q2amVheuCQfh9onnSKjU"
ADMIN_IDS = [1231872136]  # Твой Telegram ID
STUDIO_NAME = "ADEPT STUDIO"  # Название твоей студии
SUPPORT_USERNAME = "tonkidala"  # Без @

# Канал, куда будут публиковаться одобренные отзывы (бот должен быть там админом с правом постить!)
REVIEWS_CHANNEL_ID = "@otzadept"

# Если хочешь стартовую прибавку к числу участников в описании — укажи число (например, 1800). Если только реальные — 0.
FAKE_USERS_OFFSET = 0

# 2 обязательных канала (Бот ДОЛЖЕН быть в них администратором!)
CHANNELS = [
    {
        "name": "MATRIX ONLINE | ПРОЕКТ",
        "id": "@matrixonl",
        "url": "https://t.me/matrixonl",
    },
    {
        "name": "ADEPT STUDIO | РАЗРАБОТКА",
        "id": "@adeptstudi0",
        "url": "https://t.me/adeptstudi0",
    },
]

# Реквизиты для ручной оплаты
PAYMENT_DETAILS = (
    "💳 <b>Карта (Т-Банк / Сбер):</b> <code>2200 0000 0000 0000</code>\n"
    "📲 <b>СБП (по номеру):</b> <code>+7 (900) 000-00-00</code> (Банк получателя)\n"
    "👤 <b>Получатель:</b> Иван И."
)

# Настройки рефералки
REQUIRED_REFERRALS = 5
FREE_MOD_FILE = "files/free_mod.zip"

# Каталог товаров
PRODUCTS = {
    "mod_pack": {
        "name": "🎮 Мод + Сборка (AMX + PWN)",
        "clean_name": "Мод + Сборка (AMX + PWN)",
        "price": 600,
        "desc": (
            "Полная копия проекта с исходниками (PWN + AMX) и готовой сборкой.\n"
            "• Полный доступ к коду и автообновлениям.\n"
            "• Доступна автоматическая установка на ваш FTP-хостинг прямо из бота."
        ),
        "file_path": "files/full_mod.zip",
        "has_ftp": True,
    },
    "launcher": {
        "name": "🚀 Персональный Лаунчер",
        "clean_name": "Персональный лаунчер",
        "price": 350,
        "desc": (
            "Исходники и билд кастомного лаунчера (C++ / CEF) под ваш сервер.\n"
            "• Замена названия, иконки и привязка вашего IP.\n"
            "• Готовая WEB-часть для автозагрузки файлов."
        ),
        "file_path": "files/launcher.zip",
        "has_ftp": False,
    },
    "web_forum": {
        "name": "🌐 Сайт + Форум",
        "clean_name": "Сайт + Форум (XenForo)",
        "price": 400,
        "desc": (
            "Стильный портал и настроенный форум (XenForo стиль) с рулеткой и автодонатом.\n"
            "• Полная адаптация под мобильные устройства.\n"
            "• Инструкция по подключению базы данных сервера."
        ),
        "file_path": "files/web_forum.zip",
        "has_ftp": False,
    },
    "dev_kit": {
        "name": "💎 Набор РАЗРАБОТЧИКА (ALL-IN-ONE)",
        "clean_name": "Набор разработчика",
        "price": 1100,
        "desc": (
            "Максимальный комплект для запуска собственного проекта под ключ!\n"
            "Включает в себя сразу всё:\n"
            "✅ Мод + Сборка (AMX + PWN)\n"
            "✅ Персональный Лаунчер\n"
            "✅ Сайт + Форум\n"
            "✅ Автоустановка на игровой и WEB FTP + VIP-поддержка."
        ),
        "file_path": "files/dev_kit.zip",
        "has_ftp": True,
    },
}

os.makedirs("files", exist_ok=True)

RU_MONTHS = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
}
RU_MONTHS_NOM = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
}


def format_ru_date(dt: datetime = None) -> str:
    dt = dt or datetime.now()
    return f"{dt.day} {RU_MONTHS[dt.month]} {dt.year}"


# =====================================================================
# 🗄 БАЗА ДАННЫХ (SQLite)
# =====================================================================
def init_db():
    with sqlite3.connect("studio_bot.db") as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                referrer_id INTEGER DEFAULT NULL,
                ref_verified INTEGER DEFAULT 0,
                free_claimed INTEGER DEFAULT 0
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS purchases (
                user_id INTEGER,
                product_key TEXT,
                PRIMARY KEY (user_id, product_key)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                product_key TEXT,
                amount INTEGER,
                status TEXT DEFAULT 'pending',
                paid_at TEXT DEFAULT NULL
            )
        """)
        try:
            c.execute("ALTER TABLE orders ADD COLUMN paid_at TEXT DEFAULT NULL")
        except sqlite3.OperationalError:
            pass

        c.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                review_id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER,
                user_id INTEGER,
                username TEXT,
                product_key TEXT,
                amount INTEGER,
                rating INTEGER,
                review_text TEXT,
                chat_id INTEGER,
                message_id INTEGER,
                paid_at TEXT,
                status TEXT DEFAULT 'pending'
            )
        """)
        conn.commit()


def db_add_user(
    user_id: int, username: str, first_name: str, referrer_id: int = None
) -> bool:
    with sqlite3.connect("studio_bot.db") as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if not c.fetchone():
            if referrer_id == user_id:
                referrer_id = None
            c.execute(
                "INSERT INTO users (user_id, username, first_name, referrer_id) VALUES (?, ?, ?, ?)",
                (user_id, username, first_name, referrer_id),
            )
            conn.commit()
            return True
        else:
            c.execute(
                "UPDATE users SET username = ?, first_name = ? WHERE user_id = ?",
                (username, first_name, user_id),
            )
            conn.commit()
            return False


def db_get_total_users() -> int:
    with sqlite3.connect("studio_bot.db") as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        return (c.fetchone()[0] or 0) + FAKE_USERS_OFFSET


def db_get_recent_reviews(limit: int = 3) -> List[Tuple[str, int, str, str]]:
    with sqlite3.connect("studio_bot.db") as conn:
        c = conn.cursor()
        c.execute(
            "SELECT username, rating, review_text, paid_at FROM reviews WHERE status = 'published' ORDER BY review_id DESC LIMIT ?",
            (limit,),
        )
        rows = c.fetchall()

    defaults = [
        ("user123", 5, "Отличный набор, всё запустилось с пол-оборота!", "5 нояб."),
        ("matrixdev", 5, "Лучшая сборка и лаунчер, рекомендую студию!", "4 нояб."),
        ("ilya_gg", 5, "Качественно, помогли залить мод на FTP", "3 нояб."),
    ]
    result = []
    for u, r, txt, dt in rows:
        short_dt = " ".join(dt.split()[:2]) if dt else "недавно"
        result.append((u if u != "NoUsername" else "client", r, txt, short_dt))
    for d in defaults:
        if len(result) >= limit:
            break
        result.append(d)
    return result


def db_get_referrals(user_id: int):
    with sqlite3.connect("studio_bot.db") as conn:
        c = conn.cursor()
        c.execute(
            "SELECT user_id, ref_verified FROM users WHERE referrer_id = ?",
            (user_id,),
        )
        return c.fetchall()


def db_verify_referral(user_id: int):
    with sqlite3.connect("studio_bot.db") as conn:
        c = conn.cursor()
        c.execute(
            "SELECT referrer_id, ref_verified FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = c.fetchone()
        if row and row[0] and row[1] == 0:
            c.execute(
                "UPDATE users SET ref_verified = 1 WHERE user_id = ?",
                (user_id,),
            )
            conn.commit()
            return row[0]
        return None


def db_has_Access(user_id: int, product_key: str) -> bool:
    with sqlite3.connect("studio_bot.db") as conn:
        c = conn.cursor()
        c.execute(
            "SELECT 1 FROM purchases WHERE user_id = ? AND (product_key = ? OR product_key = 'dev_kit')",
            (user_id, product_key),
        )
        return c.fetchone() is not None


def db_get_purchases(user_id: int):
    with sqlite3.connect("studio_bot.db") as conn:
        c = conn.cursor()
        c.execute(
            "SELECT product_key FROM purchases WHERE user_id = ?", (user_id,)
        )
        return [r[0] for r in c.fetchall()]


def db_grant_product(user_id: int, product_key: str):
    with sqlite3.connect("studio_bot.db") as conn:
        c = conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO purchases (user_id, product_key) VALUES (?, ?)",
            (user_id, product_key),
        )
        conn.commit()


# =====================================================================
# 📊 ОБНОВЛЕНИЕ ОПИСАНИЯ БОТА (ТВОЙ ШАБЛОН)
# =====================================================================
def get_bot_bio_text() -> str:
    count = db_get_total_users()
    return (
        f"⚡ ADEPT STUDIO\n"
        f"╭・Участников: {count}\n"
        f"├・Материалы для AMAZING ONLINE\n"
        f"└・Всё в одном боте\n"
        f"--- @adeptstudi0 ---"
    )


async def update_bot_description_count(bot: Bot):
    bio_text = get_bot_bio_text()
    try:
        await bot.set_my_short_description(short_description=bio_text)
        await bot.set_my_description(description=bio_text)
    except Exception as e:
        logging.warning(f"Не удалось обновить описание бота: {e}")


# =====================================================================
# 🎨 АВТОРСКИЙ ГЕНЕРАТОР ДАШБОРДА ОТЗЫВОВ (CYBER-OBSIDIAN BENTO UI)
# =====================================================================
def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    font_candidates = (
        ["segoeuib.ttf", "arialbd.ttf", "calibrib.ttf", "DejaVuSans-Bold.ttf"]
        if bold
        else ["segoeui.ttf", "arial.ttf", "calibri.ttf", "DejaVuSans.ttf"]
    )
    for name in font_candidates:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass
    return ImageFont.load_default()


def draw_star(draw: ImageDraw.Draw, cx: float, cy: float, r: float, color: tuple):
    pts = []
    for i in range(10):
        ang = i * math.pi / 5 - math.pi / 2
        rad = r if i % 2 == 0 else r * 0.44
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    draw.polygon(pts, fill=color)


def draw_user_badge_avatar(
    draw: ImageDraw.Draw, cx: int, cy: int, r: int, letter: str, accent: tuple
):
    # Внешнее неоновое кольцо
    draw.ellipse(
        (cx - r - 3, cy - r - 3, cx + r + 3, cy + r + 3),
        outline=accent,
        width=2,
    )
    # Внутренний круг
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(26, 35, 52))
    f_av = load_font(int(r * 0.95), bold=True)
    bbox = draw.textbbox((0, 0), letter.upper(), font=f_av)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        (cx - tw / 2, cy - th / 2 - r * 0.12),
        letter.upper(),
        font=f_av,
        fill=(255, 255, 255),
    )


def wrap_text_lines(text: str, max_chars: int, max_lines: int) -> List[str]:
    words = text.split()
    lines = []
    cur = ""
    for w in words:
        if len(cur + " " + w) <= max_chars:
            cur = (cur + " " + w).strip()
        else:
            if cur:
                lines.append(cur)
            cur = w[:max_chars]
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: max(1, max_chars - 3)] + "..."
    return lines


def generate_order_card_image(
    order_id: int,
    username: str,
    user_id: int,
    paid_at: str,
    amount: int,
    product_title: str,
    rating: int,
    review_text: str,
) -> bytes:
    W, H = 1400, 900
    # Цветовая палитра Cyber-Obsidian
    bg_canvas = (10, 14, 22)
    c_card = (18, 25, 38)
    c_card_alt = (23, 32, 48)
    c_border = (36, 49, 72)
    c_emerald = (16, 185, 129)
    c_emerald_bg = (13, 52, 43)
    c_amber = (245, 158, 11)
    c_indigo = (99, 102, 241)
    c_white = (248, 250, 252)
    c_muted = (148, 163, 184)
    c_dim = (100, 116, 139)

    img = Image.new("RGB", (W, H), bg_canvas)
    draw = ImageDraw.Draw(img)

    # Декоративные фоновые сетки/точки в углах
    for gx in range(40, W, 45):
        for gy in range(40, H, 45):
            draw.point((gx, gy), fill=(25, 34, 50))

    # Шрифты
    f_brand = load_font(26, bold=True)
    f_sub_caps = load_font(12, bold=True)
    f_h2 = load_font(22, bold=True)
    f_user = load_font(26, bold=True)
    f_badge = load_font(13, bold=True)
    f_reg_15 = load_font(15, bold=False)
    f_bold_15 = load_font(15, bold=True)
    f_reg_13 = load_font(13, bold=False)
    f_bold_13 = load_font(13, bold=True)
    f_score_huge = load_font(64, bold=True)

    # =================================================================
    # 1. ВЕРХНИЙ НАВИГАЦИОННЫЙ ТОП-БАР (x: 40..1360, y: 30..108)
    # =================================================================
    draw.rounded_rectangle(
        (40, 30, 1360, 108), radius=20, fill=c_card, outline=c_border, width=2
    )
    # Неоновая иконка логотипа
    draw.rounded_rectangle((62, 44, 112, 94), radius=14, fill=c_indigo)
    draw.text((75, 47), "A", font=load_font(34, bold=True), fill=c_white)
    draw_star(draw, 101, 56, 7, c_amber)

    draw.text((130, 44), "ADEPT STUDIO", font=f_brand, fill=c_white)
    draw.text(
        (130, 75),
        "СИСТЕМА ВЕРИФИКАЦИИ ЗАКАЗОВ И ОТЗЫВОВ КЛИЕНТОВ",
        font=f_sub_caps,
        fill=c_emerald,
    )

    # Правые информационные капсулы в шапке
    now = datetime.now()
    month_str = f"{RU_MONTHS_NOM[now.month]} {now.year}"

    draw.rounded_rectangle(
        (845, 49, 1045, 89), radius=14, fill=c_emerald_bg, outline=c_emerald, width=1
    )
    draw.ellipse((863, 64, 873, 74), fill=c_emerald)
    draw.text((883, 60), "VERIFIED SYSTEM", font=f_bold_13, fill=c_emerald)

    draw.rounded_rectangle(
        (1060, 49, 1205, 89), radius=14, fill=c_card_alt, outline=c_border, width=1
    )
    draw.text((1082, 59), f"📅 {month_str}", font=f_reg_15, fill=c_white)

    draw.rounded_rectangle(
        (1220, 49, 1340, 89), radius=14, fill=c_card_alt, outline=c_border, width=1
    )
    draw.text((1236, 59), "@otzadept", font=f_bold_15, fill=c_indigo)

    # =================================================================
    # 2. ГЛАВНАЯ КАРТОЧКА ОТЗЫВА ПОКУПАТЕЛЯ (x: 40..915, y: 130..595)
    # =================================================================
    draw.rounded_rectangle(
        (40, 130, 915, 595), radius=24, fill=c_card, outline=c_border, width=2
    )
    # Верхняя акцентная неоновая линия на карточке
    draw.line((100, 130, 420, 130), fill=c_indigo, width=4)

    buyer_clean = (
        username if username and username != "NoUsername" else f"user_{user_id}"
    )
    first_let = buyer_clean[0] if buyer_clean else "A"
    draw_user_badge_avatar(draw, 108, 202, 38, first_let, c_emerald)

    buyer_tag = f"@{buyer_clean}"
    draw.text((168, 164), buyer_tag, font=f_user, fill=c_white)

    # Бейдж "ПОКУПКА ПОДТВЕРЖДЕНА"
    tag_bbox = draw.textbbox((0, 0), buyer_tag, font=f_user)
    tag_w = tag_bbox[2] - tag_bbox[0]
    bx = 185 + tag_w
    draw.rounded_rectangle(
        (bx, 166, bx + 225, 198),
        radius=16,
        fill=c_emerald_bg,
        outline=c_emerald,
        width=1,
    )
    draw.text(
        (bx + 14, 174),
        "✓ ПОКУПКА ПОДТВЕРЖДЕНА",
        font=f_badge,
        fill=c_emerald,
    )

    # Звезды рейтинга и цифровой балл
    for i in range(5):
        col = c_amber if i < rating else (45, 58, 82)
        draw_star(draw, 180 + i * 28, 218, 11, col)
    draw.text(
        (325, 208),
        f"{rating}.0 / 5.0 · Оценка клиента",
        font=f_bold_15,
        fill=c_amber,
    )

    # Правый верхний штамп номера заказа и цены
    draw.rounded_rectangle(
        (725, 158, 885, 224),
        radius=16,
        fill=c_card_alt,
        outline=c_border,
        width=1,
    )
    draw.text(
        (745, 168), f"ЗАКАЗ № {order_id:03d}", font=f_bold_15, fill=c_white
    )
    draw.text(
        (745, 194), f"Сумма: {amount} ₽", font=f_reg_13, fill=c_emerald
    )

    # Блок с цитатой отзыва
    draw.rounded_rectangle(
        (70, 258, 885, 415), radius=18, fill=(13, 19, 30), outline=(28, 39, 58), width=1
    )
    # Вертикальная неоновая плашка цитаты
    draw.rounded_rectangle((70, 258, 78, 415), radius=4, fill=c_amber)

    clean_rev = review_text.strip()
    if len(clean_rev) <= 32:
        f_quote = load_font(34, bold=True)
        draw.text((102, 312), f"«{clean_rev.upper()}»", font=f_quote, fill=c_white)
    else:
        f_quote = load_font(22, bold=True)
        q_lines = wrap_text_lines(clean_rev, max_chars=56, max_lines=3)
        qy = 282
        for ql in q_lines:
            draw.text((102, qy), ql, font=f_quote, fill=c_white)
            qy += 34

    # Встроенный блок "ОТВЕТ ADEPT STUDIO"
    draw.rounded_rectangle(
        (70, 432, 885, 515),
        radius=16,
        fill=c_card_alt,
        outline=c_border,
        width=1,
    )
    draw.rounded_rectangle((86, 448, 128, 490), radius=10, fill=c_indigo)
    draw.text((99, 453), "⚡", font=load_font(20, bold=True), fill=c_white)

    draw.text(
        (144, 446),
        "ОТВЕТ ADEPT STUDIO · ОФИЦИАЛЬНЫЙ КОММЕНТАРИЙ",
        font=f_sub_caps,
        fill=c_indigo,
    )
    draw.text(
        (144, 470),
        "Спасибо за доверие! Рады, что материалы студии помогли вашему проекту.",
        font=f_reg_15,
        fill=(226, 232, 240),
    )

    # Нижние мета-теги карточки (Товар, Дата, ID)
    date_label = paid_at if paid_at else format_ru_date()
    draw.rounded_rectangle((70, 534, 415, 572), radius=12, fill=(14, 20, 32))
    draw.text(
        (88, 543), f"📦 Товар: {product_title}", font=f_bold_15, fill=c_white
    )

    draw.rounded_rectangle((430, 534, 655, 572), radius=12, fill=(14, 20, 32))
    draw.text((448, 543), f"🕒 {date_label}", font=f_reg_15, fill=c_muted)

    draw.rounded_rectangle((670, 534, 885, 572), radius=12, fill=(14, 20, 32))
    draw.text((688, 543), f"🆔 ID: {user_id}", font=f_reg_15, fill=c_muted)

    # =================================================================
    # 3. ПРАВЫЙ ВЕРХНИЙ ВИДЖЕТ: МАТРИЦА РЕЙТИНГА (x: 940..1360, y: 130..375)
    # =================================================================
    draw.rounded_rectangle(
        (940, 130, 1360, 375), radius=24, fill=c_card, outline=c_border, width=2
    )
    draw.text((970, 152), "РЕПУТАЦИЯ СТУДИИ", font=f_sub_caps, fill=c_muted)

    draw.text((970, 175), "4.9", font=f_score_huge, fill=c_white)
    for s in range(5):
        draw_star(draw, 982 + s * 22, 265, 9, c_amber)
    draw.text((970, 286), "Средний балл", font=f_bold_15, fill=c_white)
    draw.text(
        (970, 310),
        f"{128 + order_id} проверенных",
        font=f_reg_13,
        fill=c_muted,
    )
    draw.text((970, 328), "отзывов в канале", font=f_reg_13, fill=c_muted)

    # Полосы распределения звезд
    bars = [
        ("5★", "88%", 122, c_amber),
        ("4★", "9%", 22, c_indigo),
        ("3★", "2%", 8, c_indigo),
        ("2★", "1%", 4, c_dim),
        ("1★", "0%", 0, c_dim),
    ]
    by = 182
    for label_st, pct_txt, bar_w, b_col in bars:
        draw.text((1125, by), label_st, font=f_bold_13, fill=c_muted)
        draw.rounded_rectangle(
            (1162, by + 4, 1295, by + 16), radius=6, fill=(12, 17, 27)
        )
        if bar_w > 0:
            draw.rounded_rectangle(
                (1162, by + 4, 1162 + bar_w, by + 16), radius=6, fill=b_col
            )
        draw.text((1305, by), pct_txt, font=f_bold_13, fill=c_white)
        by += 34

    # =================================================================
    # 4. ПРАВЫЙ СРЕДНИЙ ВИДЖЕТ: ИНДЕКС ДОВЕРИЯ (x: 940..1360, y: 395..595)
    # =================================================================
    draw.rounded_rectangle(
        (940, 395, 1360, 595), radius=24, fill=c_card, outline=c_border, width=2
    )
    draw.text(
        (970, 418), "ДИНАМИКА И НАДЁЖНОСТЬ", font=f_sub_caps, fill=c_emerald
    )
    draw.text(
        (970, 442), "99.2%", font=load_font(44, bold=True), fill=c_white
    )
    draw.text(
        (970, 498),
        "Успешных выдач и установок",
        font=f_reg_15,
        fill=c_muted,
    )

    draw.rounded_rectangle(
        (1245, 418, 1335, 452),
        radius=12,
        fill=c_emerald_bg,
        outline=c_emerald,
        width=1,
    )
    draw.text((1258, 426), "↗ +18%", font=f_bold_15, fill=c_emerald)

    # Неоновый график внизу виджета
    g_pts = [
        (970, 568),
        (1020, 558),
        (1065, 562),
        (1115, 542),
        (1165, 546),
        (1215, 524),
        (1275, 528),
        (1330, 502),
    ]
    poly_area = g_pts + [(1330, 578), (970, 578)]
    draw.polygon(poly_area, fill=(13, 45, 40))
    draw.line(g_pts, fill=c_emerald, width=3)
    draw.ellipse((1324, 496, 1336, 508), fill=c_emerald)

    # =================================================================
    # 5. НИЖНИЙ ЛЕВЫЙ БЛОК: ЛЕНТА ПОСЛЕДНИХ ОТЗЫВОВ (x: 40..915, y: 620..865)
    # =================================================================
    draw.rounded_rectangle(
        (40, 620, 915, 865), radius=24, fill=c_card, outline=c_border, width=2
    )
    draw.text(
        (72, 642),
        "ПОСЛЕДНИЕ ВЕРИФИЦИРОВАННЫЕ ОТЗЫВЫ",
        font=f_bold_15,
        fill=c_white,
    )
    draw.text(
        (745, 642),
        "Все отзывы в канале →",
        font=f_bold_13,
        fill=c_indigo,
    )
    draw.line((72, 674, 885, 674), fill=c_border, width=1)

    recent_list = db_get_recent_reviews(3)
    ry = 692
    for r_user, r_score, r_txt, r_dt in recent_list:
        u_let = r_user[0] if r_user else "U"
        draw_user_badge_avatar(draw, 88, ry + 16, 16, u_let, c_indigo)
        draw.text((118, ry + 6), f"@{r_user[:13]}", font=f_bold_15, fill=c_white)

        for s in range(5):
            sc = c_amber if s < r_score else (45, 58, 82)
            draw_star(draw, 265 + s * 18, ry + 16, 7, sc)

        short_t = r_txt if len(r_txt) <= 38 else r_txt[:35] + "..."
        draw.text((370, ry + 6), short_t, font=f_reg_15, fill=(215, 222, 234))
        draw.text((795, ry + 7), r_dt, font=f_reg_13, fill=c_dim)
        ry += 52

    # =================================================================
    # 6. НИЖНИЙ ПРАВЫЙ БЛОК: ПАСПОРТ СДЕЛКИ (x: 940..1360, y: 620..865)
    # =================================================================
    draw.rounded_rectangle(
        (940, 620, 1360, 865), radius=24, fill=c_card, outline=c_border, width=2
    )
    draw.text(
        (970, 642),
        "ЦИФРОВОЙ ПАСПОРТ СДЕЛКИ",
        font=f_bold_15,
        fill=c_white,
    )
    draw.line((970, 674, 1330, 674), fill=c_border, width=1)

    passport_rows = [
        ("Статус оплаты:", "Проверено владельцем", c_emerald),
        ("Метод оплаты:", "Прямой перевод (Карта / СБП)", c_white),
        ("Лицензия:", "Бессрочный доступ + FTP", c_amber),
        ("Канал студии:", "@adeptstudi0", c_indigo),
    ]
    py = 692
    for p_label, p_val, p_col in passport_rows:
        draw.text((970, py), p_label, font=f_reg_15, fill=c_muted)
        draw.text((1120, py), p_val, font=f_bold_15, fill=p_col)
        py += 38

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# =====================================================================
# 🔒 ПРОВЕРКА ПОДПИСКИ НА 2 КАНАЛА (MIDDLEWARE)
# =====================================================================
async def check_user_subscriptions(bot: Bot, user_id: int) -> Dict[str, bool]:
    results = {}
    for ch in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=ch["id"], user_id=user_id)
            is_sub = member.status in [
                ChatMemberStatus.MEMBER,
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.CREATOR,
            ]
            results[ch["name"]] = is_sub
        except Exception:
            results[ch["name"]] = False
    return results


def get_sub_Lock_screen(sub_results: Dict[str, bool]):
    status_lines = []
    for ch in CHANNELS:
        icon = "✅" if sub_results.get(ch["name"]) else "❌"
        status_lines.append(f"{icon} <b>{ch['name']}</b>")

    text = (
        f"🔒 <b>ДОСТУП К {STUDIO_NAME}</b>\n"
        f". ──────────────────── .\n\n"
        f"<blockquote>Подпишись на оба официальных канала студии. "
        f"Это открывает меню магазина, бесплатный мод за рефералов и обновления.</blockquote>\n\n"
        + "\n".join(status_lines)
        + "\n\n<i>Готово? Нажми «Проверить подписку».</i>"
    )

    kb = InlineKeyboardBuilder()
    for ch in CHANNELS:
        kb.row(InlineKeyboardButton(text=f"📢 {ch['name']}", url=ch["url"]))
    kb.row(
        InlineKeyboardButton(
            text="🔄 Проверить подписку", callback_data="check_subs"
        )
    )
    return text, kb.as_markup()


class MandatorySubMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        bot: Bot = data["bot"]
        user = data.get("event_from_user")

        if not user or user.id in ADMIN_IDS:
            return await handler(event, data)

        if (
            isinstance(event, Message)
            and event.text
            and event.text.startswith("/start")
        ):
            return await handler(event, data)

        if isinstance(event, CallbackQuery) and event.data == "check_subs":
            return await handler(event, data)

        sub_results = await check_user_subscriptions(bot, user.id)
        if not all(sub_results.values()):
            text, markup = get_sub_Lock_screen(sub_results)
            if isinstance(event, Message):
                await event.answer(text, reply_markup=markup)
            elif isinstance(event, CallbackQuery):
                await event.answer(
                    "❌ Вы не подписаны на обязательные каналы!",
                    show_alert=True,
                )
                try:
                    await event.message.edit_text(text, reply_markup=markup)
                except Exception:
                    await event.message.answer(text, reply_markup=markup)
            return

        return await handler(event, data)


# =====================================================================
# 🎛 СОСТОЯНИЯ (FSM)
# =====================================================================
class BotStates(StatesGroup):
    waiting_receipt = State()
    ftp_host = State()
    ftp_user = State()
    ftp_pass = State()
    ftp_dir = State()
    admin_grant_user = State()
    waiting_review_text = State()


# =====================================================================
# 🖥 КЛАВИАТУРЫ И ЭКРАНЫ
# =====================================================================
def get_main_menu_kb(user_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🛒 Магазин проектов", callback_data="menu_shop"))
    kb.row(
        InlineKeyboardButton(
            text="🎮 Получить мод бесплатно", callback_data="menu_free"
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="⭐️ Канал с отзывами", url="https://t.me/otzadept"
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="👤 Профиль и Покупки", callback_data="menu_profile"
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="💬 Связь с владельцем",
            url=f"https://t.me/{SUPPORT_USERNAME}",
        )
    )
    if user_id in ADMIN_IDS:
        kb.row(
            InlineKeyboardButton(
                text="👑 Админ-панель", callback_data="admin_panel"
            )
        )
    return kb.as_markup()


def get_main_menu_text(first_name: str) -> str:
    total = db_get_total_users()
    return (
        f"🔥 <b>{STUDIO_NAME}</b>\n"
        f". ──────────────────── .\n"
        f"<i>Привет, {first_name}! Выбери нужный раздел:</i>\n\n"
        f"<blockquote>⚡ ADEPT STUDIO\n"
        f"╭・Участников: <b>{total}</b>\n"
        f"├・Материалы для AMAZING ONLINE\n"
        f"└・Всё в одном боте\n"
        f"--- @adeptstudi0 ---</blockquote>\n\n"
        f"Ниже основные разделы бота:"
    )


# =====================================================================
# 🚀 ОБРАБОТЧИКИ (HANDLERS)
# =====================================================================
router = Router()


@router.message(CommandStart())
async def cmd_start(
    message: Message, command: CommandObject, bot: Bot, state: FSMContext
):
    await state.clear()
    user = message.from_user
    ref_id = (
        int(command.args)
        if command.args and command.args.isdigit()
        else None
    )

    is_new = db_add_user(
        user.id, user.username or "NoUsername", user.first_name, ref_id
    )
    if is_new:
        await update_bot_description_count(bot)

    sub_results = await check_user_subscriptions(bot, user.id)
    if not all(sub_results.values()) and user.id not in ADMIN_IDS:
        text, markup = get_sub_Lock_screen(sub_results)
        await message.answer(text, reply_markup=markup)
        return

    inviter_id = db_verify_referral(user.id)
    if inviter_id:
        try:
            await bot.send_message(
                inviter_id,
                f"🎉 <b>Новый реферал!</b>\nПользователь <b>{user.first_name}</b> перешел по твоей ссылке и подписался на оба канала!",
            )
        except Exception:
            pass

    await message.answer(
        get_main_menu_text(user.first_name),
        reply_markup=get_main_menu_kb(user.id),
    )


@router.callback_query(F.data == "check_subs")
async def cb_check_subs(call: CallbackQuery, bot: Bot):
    user = call.from_user
    sub_results = await check_user_subscriptions(bot, user.id)

    if not all(sub_results.values()):
        await call.answer(
            "❌ Подписка оформлена не на все каналы!", show_alert=True
        )
        text, markup = get_sub_Lock_screen(sub_results)
        try:
            await call.message.edit_text(text, reply_markup=markup)
        except Exception:
            pass
        return

    inviter_id = db_verify_referral(user.id)
    if inviter_id:
        try:
            await bot.send_message(
                inviter_id,
                f"🎉 <b>Реферал засчитан!</b>\nДруг <b>{user.first_name}</b> подписался на обязательные каналы!",
            )
        except Exception:
            pass

    await call.answer("✅ Доступ открыт!")
    await call.message.edit_text(
        get_main_menu_text(user.first_name),
        reply_markup=get_main_menu_kb(user.id),
    )


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(
        get_main_menu_text(call.from_user.first_name),
        reply_markup=get_main_menu_kb(call.from_user.id),
    )


# ---------------------------------------------------------------------
# 🎮 БЕСПЛАТНЫЙ МОД И РЕФЕРАЛЬНАЯ СИСТЕМА
# ---------------------------------------------------------------------
@router.callback_query(F.data == "menu_free")
async def cb_menu_free(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"

    refs = db_get_referrals(user_id)
    total_joined = len(refs)

    active_verified = 0
    for r_id, _ in refs:
        subs = await check_user_subscriptions(bot, r_id)
        if all(subs.values()):
            active_verified += 1

    text = (
        f"🎮 <b>БЕСПЛАТНЫЙ МОД ЗА РЕФЕРАЛОВ</b>\n"
        f". ──────────────────── .\n\n"
        f"Бесплатно: отправь свою ссылку друзьям. Нужно <b>{REQUIRED_REFERRALS} человек</b>.\n"
        f"Каждый друг должен запустить бота по твоей персональной ссылке и "
        f"оставаться подписанным на <b>оба обязательных канала</b> до момента выдачи.\n\n"
        f"Или приобрети полную версию (AMX + PWN + Сборка) в магазине.\n\n"
        f"👥 Зашло по ссылке: <b>{total_joined}</b>\n"
        f"✅ Засчитано с подпиской: <b>{active_verified} / {REQUIRED_REFERRALS}</b>\n\n"
        f"🔗 <b>Твоя ссылка (нажми, чтобы скопировать):</b>\n"
        f"<code>{ref_link}</code>"
    )

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="📤 Поделиться ссылкой",
            url=f"https://t.me/share/url?url={ref_link}&text=Забирай%20крутой%20мод%20CRMP%20бесплатно!",
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="🔄 Проверить приглашённых", callback_data="menu_free"
        )
    )
    if active_verified >= REQUIRED_REFERRALS:
        kb.row(
            InlineKeyboardButton(
                text="🎁 ЗАБРАТЬ БЕСПЛАТНЫЙ МОД",
                callback_data="claim_free_mod",
            )
        )
    kb.row(
        InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu")
    )

    try:
        await call.message.edit_text(text, reply_markup=kb.as_markup())
    except Exception:
        await call.answer("🔄 Данные актуальны!")


@router.callback_query(F.data == "claim_free_mod")
async def cb_claim_free_mod(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    refs = db_get_referrals(user_id)

    active_verified = 0
    for r_id, _ in refs:
        subs = await check_user_subscriptions(bot, r_id)
        if all(subs.values()):
            active_verified += 1

    if active_verified < REQUIRED_REFERRALS:
        await call.answer(
            f"❌ У вас только {active_verified}/{REQUIRED_REFERRALS} активных друзей с подпиской!",
            show_alert=True,
        )
        return

    if not os.path.exists(FREE_MOD_FILE):
        await call.answer(
            "⚠️ Архив бесплатного мода временно обновляется администратором. Напишите в поддержку!",
            show_alert=True,
        )
        return

    await call.answer("📦 Отправляю архив с модом...")
    await call.message.answer_document(
        FSInputFile(FREE_MOD_FILE),
        caption=(
            f"🎉 <b>Поздравляем! Твой бесплатный мод готов.</b>\n\n"
            f"Выполнено условие: {active_verified}/{REQUIRED_REFERRALS} приглашённых друзей.\n"
            f"<i>Для покупки полной версии с PWN и автоустановкой на FTP загляни в наш Магазин!</i>"
        ),
    )


# ---------------------------------------------------------------------
# 🛒 МАГАЗИН И КАРТОЧКИ ТОВАРОВ
# ---------------------------------------------------------------------
@router.callback_query(F.data == "menu_shop")
async def cb_menu_shop(call: CallbackQuery):
    text = (
        f"🛒 <b>КАТАЛОГ ТОВАРОВ | {STUDIO_NAME}</b>\n"
        f". ──────────────────── .\n\n"
        f"Выбери интересующий продукт для просмотра описания, "
        f"покупки или управления уже купленным товаром:"
    )
    kb = InlineKeyboardBuilder()
    for key, item in PRODUCTS.items():
        bought = "✅ " if db_has_Access(call.from_user.id, key) else ""
        kb.row(
            InlineKeyboardButton(
                text=f"{bought}{item['name']} • {item['price']} ₽",
                callback_data=f"prod_{key}",
            )
        )
    kb.row(
        InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu")
    )
    await call.message.edit_text(text, reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("prod_"))
async def cb_product_view(call: CallbackQuery):
    prod_key = call.data.split("prod_")[1]
    product = PRODUCTS[prod_key]
    user_id = call.from_user.id
    has_access = db_has_Access(user_id, prod_key)

    kb = InlineKeyboardBuilder()

    if has_access:
        text = (
            f"✅ <b>{product['name'].upper()} — ОПЛАЧЕН</b>\n"
            f". ──────────────────── .\n\n"
            f"Доступ предоставлен <b>навсегда</b>. Выбери нужное действие кнопками ниже:\n\n"
            f"• <b>Скачать архив</b> — получить файлы прямо в Telegram.\n"
        )
        if product["has_ftp"]:
            text += "• <b>Установить на FTP</b> — автоматическая загрузка мода на твой игровой хостинг.\n"
        text += f"• <b>Помощь / Настройка</b> — связь напрямую с @{SUPPORT_USERNAME}."

        kb.row(
            InlineKeyboardButton(
                text="⬇️ Скачать файлы", callback_data=f"download_{prod_key}"
            )
        )
        if product["has_ftp"]:
            kb.row(
                InlineKeyboardButton(
                    text="🚀 Установить мод на игровой FTP",
                    callback_data=f"ftp_install_{prod_key}",
                )
            )
        kb.row(
            InlineKeyboardButton(
                text=f"💬 Настроить с @{SUPPORT_USERNAME}",
                url=f"https://t.me/{SUPPORT_USERNAME}",
            )
        )
        kb.row(
            InlineKeyboardButton(
                text="◀️ Назад в магазин", callback_data="menu_shop"
            )
        )
    else:
        text = (
            f"{product['name']}\n"
            f". ──────────────────── .\n\n"
            f"<blockquote>{product['desc']}</blockquote>\n\n"
            f"💰 <b>Стоимость:</b> {product['price']} ₽ навсегда.\n"
            f"⚡️ <b>Выдача:</b> Мгновенно после подтверждения оплаты."
        )
        kb.row(
            InlineKeyboardButton(
                text=f"💳 Купить навсегда • {product['price']} ₽",
                callback_data=f"buy_{prod_key}",
            )
        )
        kb.row(
            InlineKeyboardButton(
                text="◀️ Назад в магазин", callback_data="menu_shop"
            )
        )

    await call.message.edit_text(text, reply_markup=kb.as_markup())


# ---------------------------------------------------------------------
# 💳 РУЧНАЯ ОПЛАТА (КАРТА / СБП)
# ---------------------------------------------------------------------
@router.callback_query(F.data.startswith("buy_"))
async def cb_buy_product(call: CallbackQuery):
    prod_key = call.data.split("buy_")[1]
    product = PRODUCTS[prod_key]
    user_id = call.from_user.id

    with sqlite3.connect("studio_bot.db") as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO orders (user_id, product_key, amount, status) VALUES (?, ?, ?, 'pending')",
            (user_id, prod_key, product["price"]),
        )
        order_id = c.lastrowid
        conn.commit()

    text = (
        f"🛒 <b>ОФОРМЛЕНИЕ ЗАКАЗА #{order_id}</b>\n"
        f". ──────────────────── .\n\n"
        f"📦 <b>Товар:</b> {product['name']}\n"
        f"💰 <b>Сумма к оплате:</b> <code>{product['price']}</code> ₽\n\n"
        f"<b>Реквизиты для перевода (Карта / СБП):</b>\n"
        f"<blockquote>{PAYMENT_DETAILS}</blockquote>\n\n"
        f"📌 <i>Переведи точную сумму по реквизитам выше, после чего нажми кнопку <b>«✅ Я оплатил»</b> и отправь скриншот чека (или ФИО отправителя).</i>"
    )

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="✅ Я оплатил", callback_data=f"paid_{order_id}"
        )
    )
    kb.row(
        InlineKeyboardButton(
            text=f"💬 Помощь @{SUPPORT_USERNAME}",
            url=f"https://t.me/{SUPPORT_USERNAME}",
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="◀️ Назад к товару", callback_data=f"prod_{prod_key}"
        )
    )

    await call.message.edit_text(text, reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("paid_"))
async def cb_paid_click(call: CallbackQuery, state: FSMContext):
    order_id = int(call.data.split("paid_")[1])
    await state.update_data(order_id=order_id)
    await state.set_state(BotStates.waiting_receipt)

    text = (
        f"🧾 <b>ПОДТВЕРЖДЕНИЕ ОПЛАТЫ (Заказ #{order_id})</b>\n"
        f". ──────────────────── .\n\n"
        f"Отправь в чат <b>скриншот чека</b> или напиши текстом <b>время перевода / последние 4 цифры карты</b>, чтобы владелец быстрее проверил платёж:"
    )
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="◀️ Отмена", callback_data="menu_shop"))
    await call.message.edit_text(text, reply_markup=kb.as_markup())


@router.message(BotStates.waiting_receipt)
async def process_receipt(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    order_id = data.get("order_id")
    await state.clear()

    with sqlite3.connect("studio_bot.db") as conn:
        c = conn.cursor()
        c.execute(
            "SELECT user_id, product_key, amount FROM orders WHERE order_id = ?",
            (order_id,),
        )
        order = c.fetchone()

    if not order:
        await message.answer("❌ Заказ не найден.")
        return

    user_id, prod_key, amount = order
    product = PRODUCTS[prod_key]

    await message.answer(
        f"⏳ <b>Заявка #{order_id} отправлена на проверку!</b>\n"
        f"Владелец проверит поступление средств и откроет доступ к <b>{product['name']}</b>. Обычно это занимает от 1 до 15 минут.",
        reply_markup=get_main_menu_kb(user_id),
    )

    admin_kb = InlineKeyboardBuilder()
    admin_kb.row(
        InlineKeyboardButton(
            text="✅ Подтвердить выдачу", callback_data=f"adm_approve_{order_id}"
        ),
        InlineKeyboardButton(
            text="❌ Отклонить", callback_data=f"adm_reject_{order_id}"
        ),
    )

    admin_caption = (
        f"🔔 <b>НОВАЯ ОПЛАТА НА ПРОВЕРКУ! (Заказ #{order_id})</b>\n"
        f". ──────────────────── .\n"
        f"👤 <b>Покупатель:</b> {message.from_user.full_name} (@{message.from_user.username})\n"
        f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
        f"📦 <b>Товар:</b> {product['name']}\n"
        f"💰 <b>Сумма:</b> {amount} ₽\n"
    )

    for admin_id in ADMIN_IDS:
        try:
            if message.photo:
                await bot.send_photo(
                    admin_id,
                    photo=message.photo[-1].file_id,
                    caption=admin_caption
                    + f"\n💬 <b>Комментарий:</b> {message.caption or 'Скриншот чека'}",
                    reply_markup=admin_kb.as_markup(),
                )
            else:
                await bot.send_message(
                    admin_id,
                    admin_caption + f"\n💬 <b>Реквизиты/Чек:</b> {message.text}",
                    reply_markup=admin_kb.as_markup(),
                )
        except Exception as e:
            logging.error(
                f"Не удалось отправить уведомление админу {admin_id}: {e}"
            )


# ---------------------------------------------------------------------
# ⭐️ СИСТЕМА ОТЗЫВОВ С МОДЕРАЦИЕЙ И АВТОРСКИМ ДАШБОРДОМ
# ---------------------------------------------------------------------
@router.callback_query(F.data.startswith("leave_review_"))
async def cb_leave_review_start(call: CallbackQuery):
    order_id = int(call.data.split("leave_review_")[1])

    with sqlite3.connect("studio_bot.db") as conn:
        c = conn.cursor()
        c.execute("SELECT 1 FROM reviews WHERE order_id = ?", (order_id,))
        if c.fetchone():
            await call.answer(
                "Вы уже оставляли отзыв по этому заказу!", show_alert=True
            )
            return

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="⭐️⭐️⭐️⭐️⭐️ (5/5)",
            callback_data=f"revrate_{order_id}_5",
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="⭐️⭐️⭐️⭐️ (4/5)", callback_data=f"revrate_{order_id}_4"
        ),
        InlineKeyboardButton(
            text="⭐️⭐️⭐️ (3/5)", callback_data=f"revrate_{order_id}_3"
        ),
    )
    kb.row(InlineKeyboardButton(text="◀️ Отмена", callback_data="menu_profile"))

    await call.message.answer(
        f"⭐️ <b>ОСТАВИТЬ ЧЕСТНЫЙ ОТЗЫВ · ЗАКАЗ #{order_id:03d}</b>\n"
        f". ──────────────────── .\n\n"
        f"Выбери оценку качества товара и работы студии:",
        reply_markup=kb.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("revrate_"))
async def cb_review_rate(call: CallbackQuery, state: FSMContext):
    _, order_id_str, rating_str = call.data.split("_")
    order_id = int(order_id_str)
    rating = int(rating_str)

    await state.update_data(review_order_id=order_id, review_rating=rating)
    await state.set_state(BotStates.waiting_review_text)

    await call.message.edit_text(
        f"✍️ <b>НАПИШИ ТЕКСТ ОТЗЫВА (Оценка: {rating}/5)</b>\n"
        f". ──────────────────── .\n\n"
        f"Напиши одним сообщением свой честный отзыв о покупке.\n"
        f"<i>После проверки администратором дашборд заказа и твое сообщение будут опубликованы в канале {REVIEWS_CHANNEL_ID}!</i>"
    )


@router.message(BotStates.waiting_review_text)
async def process_review_text(message: Message, state: FSMContext, bot: Bot):
    if not message.text:
        await message.answer("Пожалуйста, отправь отзыв текстовым сообщением.")
        return

    data = await state.get_data()
    order_id = data["review_order_id"]
    rating = data["review_rating"]
    await state.clear()

    review_text = message.text.strip()
    user = message.from_user

    with sqlite3.connect("studio_bot.db") as conn:
        c = conn.cursor()
        c.execute(
            "SELECT product_key, amount, paid_at FROM orders WHERE order_id = ?",
            (order_id,),
        )
        row = c.fetchone()
        if not row:
            await message.answer("❌ Заказ не найден.")
            return
        prod_key, amount, paid_at = row
        if not paid_at:
            paid_at = format_ru_date()

        c.execute(
            """
            INSERT INTO reviews (
                order_id, user_id, username, product_key, amount,
                rating, review_text, chat_id, message_id, paid_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            """,
            (
                order_id,
                user.id,
                user.username or "NoUsername",
                prod_key,
                amount,
                rating,
                review_text,
                message.chat.id,
                message.message_id,
                paid_at,
            ),
        )
        review_id = c.lastrowid
        conn.commit()

    await message.answer(
        "✅ <b>Спасибо! Твой отзыв отправлен на модерацию владельцу.</b>\n"
        "Как только администратор одобрит его, ты получишь уведомление, а карточка появится в канале!",
        reply_markup=get_main_menu_kb(user.id),
    )

    product_clean = PRODUCTS.get(prod_key, {}).get("clean_name", prod_key)
    card_bytes = await asyncio.to_thread(
        generate_order_card_image,
        order_id,
        user.username or "NoUsername",
        user.id,
        paid_at,
        amount,
        product_clean,
        rating,
        review_text,
    )

    adm_kb = InlineKeyboardBuilder()
    adm_kb.row(
        InlineKeyboardButton(
            text="✅ Одобрить и выложить в канал",
            callback_data=f"adm_rev_pub_{review_id}",
        )
    )
    adm_kb.row(
        InlineKeyboardButton(
            text="❌ Отклонить отзыв",
            callback_data=f"adm_rev_rej_{review_id}",
        )
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_photo(
                admin_id,
                photo=BufferedInputFile(
                    card_bytes, filename=f"adept_review_{order_id}.png"
                ),
                caption=(
                    f"🌟 <b>НОВЫЙ ОТЗЫВ НА МОДЕРАЦИЮ (#{review_id})</b>\n"
                    f". ──────────────────── .\n"
                    f"🧾 <b>Заказ:</b> #{order_id:03d}\n"
                    f"👤 <b>Покупатель:</b> @{user.username or user.id}\n"
                    f"⭐️ <b>Оценка:</b> {rating}/5\n"
                    f"💬 <b>Текст:</b> <i>{review_text}</i>"
                ),
                reply_markup=adm_kb.as_markup(),
            )
        except Exception as e:
            logging.error(f"Ошибка отправки превью отзыва админу: {e}")


@router.callback_query(F.data.startswith("adm_rev_pub_"))
async def cb_adm_review_publish(call: CallbackQuery, bot: Bot):
    if call.from_user.id not in ADMIN_IDS:
        return

    review_id = int(call.data.split("adm_rev_pub_")[1])
    with sqlite3.connect("studio_bot.db") as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT order_id, user_id, username, product_key, amount,
                   rating, review_text, chat_id, message_id, paid_at, status
            FROM reviews WHERE review_id = ?
            """,
            (review_id,),
        )
        rev = c.fetchone()
        if not rev:
            await call.answer("Отзыв не найден!", show_alert=True)
            return

        (
            order_id,
            user_id,
            username,
            prod_key,
            amount,
            rating,
            review_text,
            chat_id,
            message_id,
            paid_at,
            status,
        ) = rev

        if status == "published":
            await call.answer("Этот отзыв уже опубликован!", show_alert=True)
            return

        c.execute(
            "UPDATE reviews SET status = 'published' WHERE review_id = ?",
            (review_id,),
        )
        conn.commit()

    product_clean = PRODUCTS.get(prod_key, {}).get("clean_name", prod_key)
    card_bytes = await asyncio.to_thread(
        generate_order_card_image,
        order_id,
        username,
        user_id,
        paid_at,
        amount,
        product_clean,
        rating,
        review_text,
    )

    try:
        # 1. Отправляем дашборд отзыва в канал
        await bot.send_photo(
            chat_id=REVIEWS_CHANNEL_ID,
            photo=BufferedInputFile(
                card_bytes, filename=f"adept_review_{order_id}.png"
            ),
            caption=(
                f"⚡ <b>ADEPT STUDIO · Верифицированный заказ #{order_id:03d}</b>\n"
                f"📦 Товар: <b>{product_clean}</b>\n"
                f"Оригинал сообщения покупателя переслан ниже."
            ),
        )

        # 2. Пересылаем оригинальное сообщение покупателя
        forwarded_msg = None
        try:
            forwarded_msg = await bot.forward_message(
                chat_id=REVIEWS_CHANNEL_ID,
                from_chat_id=chat_id,
                message_id=message_id,
            )
        except Exception:
            pass

        # 3. Отправляем ответ-сводку реплаем на пересланный отзыв
        stars = "⭐️" * rating
        mood = "🔥 положительный" if rating >= 4 else "😐 нейтральный"
        buyer_tag = (
            f"@{username}"
            if username and username != "NoUsername"
            else f"<a href='tg://user?id={user_id}'>Покупатель</a>"
        )
        summary_text = (
            f"Оценка: {stars} {rating}/5 · {mood}\n"
            f"Покупатель: {buyer_tag}"
        )

        if forwarded_msg:
            await bot.send_message(
                chat_id=REVIEWS_CHANNEL_ID,
                text=summary_text,
                reply_parameters=ReplyParameters(
                    message_id=forwarded_msg.message_id
                ),
            )
        else:
            await bot.send_message(
                chat_id=REVIEWS_CHANNEL_ID,
                text=f"💬 <i>«{review_text}»</i>\n\n" + summary_text,
            )

    except Exception as e:
        await call.answer(
            f"❌ Ошибка публикации в {REVIEWS_CHANNEL_ID}: {e}",
            show_alert=True,
        )
        return

    try:
        await bot.send_message(
            user_id,
            "✅ Администратор одобрил твой отзыв — он опубликован в канале. Спасибо за доверие!",
        )
    except Exception:
        pass

    await call.answer("✅ Отзыв успешно опубликован в канале!")
    await call.message.edit_caption(
        caption=call.message.caption + "\n\n✅ <b>ОПУБЛИКОВАНО В КАНАЛЕ</b>"
    )


@router.callback_query(F.data.startswith("adm_rev_rej_"))
async def cb_adm_review_reject(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return
    review_id = int(call.data.split("adm_rev_rej_")[1])
    with sqlite3.connect("studio_bot.db") as conn:
        c = conn.cursor()
        c.execute(
            "UPDATE reviews SET status = 'rejected' WHERE review_id = ?",
            (review_id,),
        )
        conn.commit()
    await call.answer("❌ Отзыв отклонен.")
    await call.message.edit_caption(
        caption=call.message.caption + "\n\n❌ <b>ОТЗЫВ ОТКЛОНЕН</b>"
    )


# ---------------------------------------------------------------------
# 📦 ВЫДАЧА ФАЙЛОВ И АВТОУСТАНОВКА НА FTP
# ---------------------------------------------------------------------
@router.callback_query(F.data.startswith("download_"))
async def cb_download_product(call: CallbackQuery):
    prod_key = call.data.split("download_")[1]
    if not db_has_Access(call.from_user.id, prod_key):
        await call.answer(
            "❌ У вас нет доступа к этому товару!", show_alert=True
        )
        return

    product = PRODUCTS[prod_key]
    file_path = product["file_path"]

    if not os.path.exists(file_path):
        await call.answer(
            f"⚠️ Файл ({file_path}) ещё не загружен на сервер бота. Обратитесь к @{SUPPORT_USERNAME}!",
            show_alert=True,
        )
        return

    await call.answer("📦 Отправляю архив в чат...")
    await call.message.answer_document(
        FSInputFile(file_path),
        caption=f"✅ <b>{product['name']}</b>\nАктуальный архив проекта от {STUDIO_NAME}.",
    )


@router.callback_query(F.data.startswith("ftp_install_"))
async def cb_ftp_start(call: CallbackQuery, state: FSMContext):
    prod_key = call.data.split("ftp_install_")[1]
    if not db_has_Access(call.from_user.id, prod_key):
        await call.answer("❌ Нет доступа!", show_alert=True)
        return

    await state.update_data(ftp_prod_key=prod_key)
    await state.set_state(BotStates.ftp_host)

    text = (
        f"🚀 <b>МАСТЕР АВТОУСТАНОВКИ НА FTP (Шаг 1/4)</b>\n"
        f". ──────────────────── .\n\n"
        f"Бот автоматически подключится к твоему игровому хостингу и загрузит архив сборки.\n\n"
        f"👉 <b>Введи IP или адрес FTP-сервера</b> (например, <code>80.242.59.112</code>):"
    )
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="◀️ Отмена", callback_data=f"prod_{prod_key}"
        )
    )
    await call.message.edit_text(text, reply_markup=kb.as_markup())


@router.message(BotStates.ftp_host)
async def process_ftp_host(message: Message, state: FSMContext):
    await state.update_data(host=message.text.strip())
    await state.set_state(BotStates.ftp_user)
    await message.answer(
        "👤 <b>Шаг 2/4:</b> Введи <b>Логин (Username)</b> от FTP:"
    )


@router.message(BotStates.ftp_user)
async def process_ftp_user(message: Message, state: FSMContext):
    await state.update_data(user=message.text.strip())
    await state.set_state(BotStates.ftp_pass)
    await message.answer(
        "🔑 <b>Шаг 3/4:</b> Введи <b>Пароль</b> от FTP (сообщение с паролем будет сразу удалено для безопасности):"
    )


@router.message(BotStates.ftp_pass)
async def process_ftp_pass(message: Message, state: FSMContext):
    await state.update_data(password=message.text.strip())
    try:
        await message.delete()
    except Exception:
        pass
    await state.set_state(BotStates.ftp_dir)
    await message.answer(
        "📂 <b>Шаг 4/4:</b> Укажи <b>папку на сервере</b>, куда загрузить мод (отправь <code>/</code> для корневой папки сервера):"
    )


def upload_to_ftp_sync(
    host: str, user: str, passwd: str, remote_dir: str, local_file: str
):
    with ftplib.FTP(host, timeout=30) as ftp:
        ftp.login(user=user, passwd=passwd)
        if remote_dir and remote_dir != "/":
            ftp.cwd(remote_dir)
        filename = os.path.basename(local_file)
        with open(local_file, "rb") as f:
            ftp.storbinary(f"STOR {filename}", f)


@router.message(BotStates.ftp_dir)
async def process_ftp_upload(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    prod_key = data["ftp_prod_key"]
    local_file = PRODUCTS[prod_key]["file_path"]
    remote_dir = message.text.strip()

    if not os.path.exists(local_file):
        await message.answer(
            f"❌ Локальный файл <code>{local_file}</code> не найден на сервере бота."
        )
        return

    wait_msg = await message.answer(
        "⏳ <b>Подключаюсь к FTP-хостингу и загружаю файлы...</b> Пожалуйста, подождите."
    )

    try:
        await asyncio.to_thread(
            upload_to_ftp_sync,
            data["host"],
            data["user"],
            data["password"],
            remote_dir,
            local_file,
        )
        await wait_msg.edit_text(
            f"✅ <b>УСПЕШНО ЗАГРУЖЕНО НА FTP!</b>\n"
            f". ──────────────────── .\n"
            f"🖥 <b>Хост:</b> <code>{data['host']}</code>\n"
            f"📂 <b>Директория:</b> <code>{remote_dir}</code>\n"
            f"📦 <b>Файл:</b> <code>{os.path.basename(local_file)}</code>\n\n"
            f"<i>Теперь открой панель хостинга, распакуй архив и перезапусти сервер!</i>",
            reply_markup=get_main_menu_kb(message.from_user.id),
        )
    except Exception as e:
        await wait_msg.edit_text(
            f"❌ <b>Ошибка при подключении к FTP:</b>\n<code>{e}</code>\n\n"
            f"Проверь правильность IP, логина и пароля и попробуй снова.",
            reply_markup=get_main_menu_kb(message.from_user.id),
        )


# ---------------------------------------------------------------------
# 👤 ПРОФИЛЬ И ПОКУПКИ ПОЛЬЗОВАТЕЛЯ
# ---------------------------------------------------------------------
@router.callback_query(F.data == "menu_profile")
async def cb_profile(call: CallbackQuery):
    user_id = call.from_user.id
    purchases = db_get_purchases(user_id)
    refs = db_get_referrals(user_id)

    if purchases:
        bought_list = "\n".join(
            [f"• {PRODUCTS[k]['name']}" for k in purchases if k in PRODUCTS]
        )
    else:
        bought_list = "<i>У вас пока нет покупок</i>"

    text = (
        f"👤 <b>ЛИЧНЫЙ ПРОФИЛЬ</b>\n"
        f". ──────────────────── .\n\n"
        f"🆔 <b>Ваш ID:</b> <code>{user_id}</code>\n"
        f"👥 <b>Приглашено друзей:</b> {len(refs)}\n\n"
        f"📦 <b>Ваши покупки:</b>\n{bought_list}"
    )

    kb = InlineKeyboardBuilder()
    for k in purchases:
        if k in PRODUCTS:
            kb.row(
                InlineKeyboardButton(
                    text=f"⚙️ Управление: {PRODUCTS[k]['name']}",
                    callback_data=f"prod_{k}",
                )
            )
    kb.row(
        InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu")
    )
    await call.message.edit_text(text, reply_markup=kb.as_markup())


# =====================================================================
# 👑 АДМИН-ПАНЕЛЬ ВЛАДЕЛЬЦА
# =====================================================================
@router.message(Command("admin"))
@router.callback_query(F.data == "admin_panel")
async def admin_panel_view(
    event: Message | CallbackQuery, state: FSMContext, bot: Bot
):
    user_id = event.from_user.id
    if user_id not in ADMIN_IDS:
        return
    await state.clear()

    with sqlite3.connect("studio_bot.db") as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        real_users = c.fetchone()[0]
        c.execute(
            "SELECT COUNT(*), SUM(amount) FROM orders WHERE status = 'approved'"
        )
        sales_row = c.fetchone()
        total_sales = sales_row[0] or 0
        total_revenue = sales_row[1] or 0
        c.execute("SELECT COUNT(*) FROM orders WHERE status = 'pending'")
        pending_orders = c.fetchone()[0]

    text = (
        f"👑 <b>ПАНЕЛЬ УПРАВЛЕНИЯ | {STUDIO_NAME}</b>\n"
        f". ──────────────────── .\n\n"
        f"👥 <b>Пользователей в БД:</b> {real_users} (В описании: {real_users + FAKE_USERS_OFFSET})\n"
        f"⏳ <b>Ожидают проверки оплаты:</b> {pending_orders}\n"
        f"✅ <b>Успешных продаж:</b> {total_sales} шт.\n"
        f"💰 <b>Общая выручка:</b> {total_revenue} ₽"
    )

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text=f"📋 Заявки на оплату ({pending_orders})",
            callback_data="adm_pending_list",
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="🎁 Выдать товар вручную по ID",
            callback_data="adm_grant_manual",
        )
    )
    kb.row(
        InlineKeyboardButton(
            text="🔄 Обновить описание бота (счетчик чел.)",
            callback_data="adm_sync_bio",
        )
    )
    kb.row(
        InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu")
    )

    if isinstance(event, Message):
        await event.answer(text, reply_markup=kb.as_markup())
    else:
        await event.message.edit_text(text, reply_markup=kb.as_markup())


@router.callback_query(F.data == "adm_sync_bio")
async def cb_adm_sync_bio(call: CallbackQuery, bot: Bot):
    if call.from_user.id not in ADMIN_IDS:
        return
    await update_bot_description_count(bot)
    await call.answer(
        f"✅ Описание бота обновлено! Участников: {db_get_total_users()}",
        show_alert=True,
    )


@router.callback_query(F.data == "adm_pending_list")
async def cb_adm_pending(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return

    with sqlite3.connect("studio_bot.db") as conn:
        c = conn.cursor()
        c.execute(
            "SELECT order_id, user_id, product_key, amount FROM orders WHERE status = 'pending' LIMIT 10"
        )
        rows = c.fetchall()

    if not rows:
        await call.answer("✅ Нет неразобранных заявок!", show_alert=True)
        return

    kb = InlineKeyboardBuilder()
    for o_id, u_id, p_key, amount in rows:
        kb.row(
            InlineKeyboardButton(
                text=f"✅ #{o_id} ({u_id}) - {amount}₽",
                callback_data=f"adm_approve_{o_id}",
            ),
            InlineKeyboardButton(
                text=f"❌ #{o_id}", callback_data=f"adm_reject_{o_id}"
            ),
        )
    kb.row(
        InlineKeyboardButton(
            text="◀️ Назад в админку", callback_data="admin_panel"
        )
    )

    await call.message.edit_text(
        "📋 <b>ОЖИДАЮТ ПОДТВЕРЖДЕНИЯ ОПЛАТЫ:</b>\nНажми ✅ для выдачи товара или ❌ для отмены:",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("adm_approve_"))
async def cb_adm_approve(call: CallbackQuery, bot: Bot):
    if call.from_user.id not in ADMIN_IDS:
        return

    order_id = int(call.data.split("adm_approve_")[1])
    now_str = format_ru_date()

    with sqlite3.connect("studio_bot.db") as conn:
        c = conn.cursor()
        c.execute(
            "SELECT user_id, product_key, amount, status FROM orders WHERE order_id = ?",
            (order_id,),
        )
        order = c.fetchone()
        if not order:
            await call.answer("Заказ не найден", show_alert=True)
            return
        user_id, prod_key, amount, status = order
        if status == "approved":
            await call.answer(
                "Этот заказ уже был подтвержден ранее!", show_alert=True
            )
            return

        c.execute(
            "UPDATE orders SET status = 'approved', paid_at = ? WHERE order_id = ?",
            (now_str, order_id),
        )
        conn.commit()

    db_grant_product(user_id, prod_key)
    product = PRODUCTS[prod_key]

    buyer_kb = InlineKeyboardBuilder()
    buyer_kb.row(
        InlineKeyboardButton(
            text="⭐️ Оставить честный отзыв",
            callback_data=f"leave_review_{order_id}",
        )
    )
    buyer_kb.row(
        InlineKeyboardButton(
            text=f"⚙️ Открыть {product['name']}", callback_data=f"prod_{prod_key}"
        )
    )
    buyer_kb.row(
        InlineKeyboardButton(
            text="👤 Мои покупки", callback_data="menu_profile"
        )
    )

    try:
        await bot.send_message(
            user_id,
            f"✅ <b>Покупка подтверждена (Заказ № {order_id:03d}).</b>\n"
            f"Сохрани номер заказа и оставь честный отзыв после проверки товара.\n\n"
            f"Доступ к <b>{product['name']}</b> предоставлен <b>навсегда</b>.",
            reply_markup=buyer_kb.as_markup(),
        )
    except Exception:
        pass

    await call.answer(f"✅ Заказ #{order_id} подтвержден, товар выдан!")
    if call.message.photo:
        await call.message.edit_caption(
            caption=call.message.caption
            + "\n\n✅ <b>СТАТУС: ОПЛАТА ПОДТВЕРЖДЕНА</b>"
        )
    else:
        await call.message.edit_text(
            call.message.text + "\n\n✅ <b>СТАТУС: ОПЛАТА ПОДТВЕРЖДЕНА</b>"
        )


@router.callback_query(F.data.startswith("adm_reject_"))
async def cb_adm_reject(call: CallbackQuery, bot: Bot):
    if call.from_user.id not in ADMIN_IDS:
        return

    order_id = int(call.data.split("adm_reject_")[1])
    with sqlite3.connect("studio_bot.db") as conn:
        c = conn.cursor()
        c.execute(
            "SELECT user_id, product_key FROM orders WHERE order_id = ?",
            (order_id,),
        )
        order = c.fetchone()
        if order:
            c.execute(
                "UPDATE orders SET status = 'rejected' WHERE order_id = ?",
                (order_id,),
            )
            conn.commit()
            try:
                await bot.send_message(
                    order[0],
                    f"❌ <b>Оплата по заказу #{order_id} не найдена или отклонена администратором.</b>\n"
                    f"Если произошла ошибка, свяжитесь с @{SUPPORT_USERNAME}.",
                )
            except Exception:
                pass

    await call.answer(f"❌ Заказ #{order_id} отклонен.")
    if call.message.photo:
        await call.message.edit_caption(
            caption=call.message.caption + "\n\n❌ <b>СТАТУС: ОТКЛОНЕНО</b>"
        )
    else:
        await call.message.edit_text(
            call.message.text + "\n\n❌ <b>СТАТУС: ОТКЛОНЕНО</b>"
        )


@router.callback_query(F.data == "adm_grant_manual")
async def cb_adm_grant_manual(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(BotStates.admin_grant_user)
    await call.message.edit_text(
        "🎁 <b>РУЧНАЯ ВЫДАЧА ТОВАРА</b>\n\nОтправь <b>Telegram ID</b> пользователя и ключ товара через пробел.\n"
        "Доступные ключи:\n"
        "• <code>mod_pack</code> — Мод + Сборка\n"
        "• <code>launcher</code> — Лаунчер\n"
        "• <code>web_forum</code> — Сайт + Форум\n"
        "• <code>dev_kit</code> — Набор РАЗРАБОТЧИКА\n\n"
        "<i>Пример:</i> <code>123456789 dev_kit</code>"
    )


@router.message(BotStates.admin_grant_user)
async def process_adm_grant(message: Message, state: FSMContext, bot: Bot):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.clear()
    parts = message.text.strip().split()
    if len(parts) != 2 or not parts[0].isdigit() or parts[1] not in PRODUCTS:
        await message.answer("❌ Неверный формат. Попробуй снова через /admin")
        return

    target_id = int(parts[0])
    prod_key = parts[1]
    now_str = format_ru_date()

    with sqlite3.connect("studio_bot.db") as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO orders (user_id, product_key, amount, status, paid_at) VALUES (?, ?, ?, 'approved', ?)",
            (target_id, prod_key, PRODUCTS[prod_key]["price"], now_str),
        )
        order_id = c.lastrowid
        conn.commit()

    db_grant_product(target_id, prod_key)

    buyer_kb = InlineKeyboardBuilder()
    buyer_kb.row(
        InlineKeyboardButton(
            text="⭐️ Оставить честный отзыв",
            callback_data=f"leave_review_{order_id}",
        )
    )
    buyer_kb.row(
        InlineKeyboardButton(
            text=f"⚙️ Открыть {PRODUCTS[prod_key]['name']}",
            callback_data=f"prod_{prod_key}",
        )
    )

    try:
        await bot.send_message(
            target_id,
            f"✅ <b>Покупка подтверждена (Заказ № {order_id:03d}).</b>\n"
            f"Сохрани номер заказа и оставь честный отзыв после проверки товара.\n\n"
            f"Доступ к <b>{PRODUCTS[prod_key]['name']}</b> предоставлен <b>навсегда</b>.",
            reply_markup=buyer_kb.as_markup(),
        )
    except Exception:
        pass

    await message.answer(
        f"✅ Товар <b>{PRODUCTS[prod_key]['name']}</b> (Заказ № {order_id:03d}) выдан пользователю <code>{target_id}</code>!"
    )


# =====================================================================
# ▶️ ЗАПУСК БОТА
# =====================================================================
async def main():
    logging.basicConfig(level=logging.INFO)
    init_db()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    dp.message.middleware(MandatorySubMiddleware())
    dp.callback_query.middleware(MandatorySubMiddleware())

    dp.include_router(router)

    # При запуске синхронизируем новое описание бота с базой
    await update_bot_description_count(bot)

    print(f"🚀 Бот {STUDIO_NAME} успешно запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
