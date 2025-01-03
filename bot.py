from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import logging
import asyncio

# Импорт нужных функций
from database import (
    create_user_tables, get_unread_posts, mark_posts_as_read, add_user_channel, remove_user_channel,
    get_user_channels, is_active, activate_user, deactivate_user, get_channel_description,
    add_channel_description, add_detailed_channel_description
)
from CONFIG import TELEGRAM_BOT_API
# Важно, чтобы был импорт get_last_posts, если вы используете его при добавлении канала
from AI_main import check_new_posts, auto_update, get_last_posts
from ai_analyzer import generate_summary_of_best_posts, remove_duplicate_summaries, is_summary_relevant, generate_digest
from channel_analyzer import create_detailed_channel_description, create_short_channel_description


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

bot = Bot(
    token=TELEGRAM_BOT_API,
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
)

storage = MemoryStorage()
dp = Dispatcher(storage=storage)


class AddChannel(StatesGroup):
    waiting_for_channel = State()


def escape_md(text):
    """
    Экранирует спецсимволы Markdown.
    """
    escape_chars = ['*', '_', '`', '[', ']']
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    return text


def get_main_keyboard(user_id):
    """
    Возвращает клавиатуру в зависимости от состояния активации.
    """
    if is_active(user_id):
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Новые посты")],
                [KeyboardButton(text="Дайджест")],
                [KeyboardButton(text="Список каналов")],
                [KeyboardButton(text="Отключить бота")]
            ],
            resize_keyboard=True
        )
    else:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Новые посты")],
                [KeyboardButton(text="Добавить канал"), KeyboardButton(text="Удалить канал")],
                [KeyboardButton(text="Список каналов")],
                [KeyboardButton(text="Включить бота")]
            ],
            resize_keyboard=True
        )
    return keyboard


@dp.message(Command("start"))
async def send_welcome(message: Message):
    """
    Обработчик команды /start. Отправляет приветственное сообщение и показывает клавиатуру.
    """
    user_id = message.from_user.id
    create_user_tables(user_id)  # Создаем таблицы для пользователя, если они еще не существуют

    welcome_text = (
        "👋 Привет! Я бот, который помогает отслеживать новые посты в Telegram-каналах.\n\n"
        "📌 Как пользоваться ботом:\n"
        "1. Добавьте каналы, которые хотите отслеживать, кнопкой \"Добавить канал\" или командой /add_channel.\n"
        "2. Нажмите кнопку \"Включить бота\", чтобы начать получать выжимки постов.\n\n"
        "Сейчас можете добавить каналы, которые хотите отслеживать."
    )
    await message.answer(escape_md(welcome_text), reply_markup=get_main_keyboard(user_id))


@dp.message(lambda message: message.text == "Включить бота")
async def activate_ai_main(message: Message):
    user_id = message.from_user.id

    channels = get_user_channels(user_id)
    if not channels:
        await message.answer(
            "Вы не добавили ни одного канала. Сначала добавьте каналы, чтобы начать отслеживание.",
            reply_markup=get_main_keyboard(user_id)
        )
        return

    activate_user(user_id)

    waiting_msg = await message.answer("Идет изучение постов. Подождите...")
    summaries, new_posts_found = await check_new_posts(user_id)
    await waiting_msg.delete()

    await message.answer(
        "Отслеживание постов активировано!\n"
        "Теперь можно составлять дайджест или смотреть новые посты.",
        reply_markup=get_main_keyboard(user_id)
    )


    asyncio.create_task(auto_update(user_id))
    """
    Обработчик нажатия на кнопку "Включить бота".
    Теперь не делает сразу выжимку из всех постов, а просто активирует бота.
    """
    user_id = message.from_user.id
    channels = get_user_channels(user_id)
    if not channels:
        await message.answer(
            escape_md("Вы не добавили ни одного канала. Сначала добавьте каналы, чтобы начать отслеживание."),
            reply_markup=get_main_keyboard(user_id)
        )
        return

    activate_user(user_id)



@dp.message(lambda message: message.text == "Отключить бота")
async def deactivate_ai_main(message: Message):
    """
    Обработчик нажатия на кнопку "Отключить бота".
    """
    user_id = message.from_user.id
    deactivate_user(user_id)
    await message.answer(
        escape_md("Отслеживание постов деактивировано. Теперь вы можете изменять список каналов."),
        reply_markup=get_main_keyboard(user_id)
    )


@dp.message(Command("add_channel"))
@dp.message(lambda message: message.text == "Добавить канал")
async def add_channel_start(message: Message, state: FSMContext):
    """
    Обработчик команды /add_channel ИЛИ нажатия на кнопку "Добавить канал".
    Переводит бота в состояние ожидания ввода названия канала.
    """
    user_id = message.from_user.id
    if is_active(user_id):
        await message.answer(
            escape_md("❌ Отслеживание активно. Сначала отключите бота, чтобы изменить список каналов."),
            reply_markup=get_main_keyboard(user_id)
        )
        return

    await message.answer(escape_md("Введите название канала (например, @channel_name):"))
    await state.set_state(AddChannel.waiting_for_channel)


@dp.message(AddChannel.waiting_for_channel)
async def add_channel_finish(message: Message, state: FSMContext):
    """
    Обработчик ввода названия канала. Добавляет канал в список отслеживаемых.
    """
    user_id = message.from_user.id
    channel_username = message.text.strip().replace("@", "")
    try:
        await message.answer(escape_md("Идет изучение контента канала... Подождите."))

        # Получаем последние посты канала (максимум 30)
        posts = await get_last_posts(channel_username, limit=30)

        # Создаем краткое и подробное описание канала
        short_description = await create_short_channel_description(posts)
        detailed_description = await create_detailed_channel_description(posts)

        # Добавляем канал и его описания в базу данных
        add_user_channel(user_id, channel_username)
        add_channel_description(user_id, channel_username, short_description)
        add_detailed_channel_description(user_id, channel_username, detailed_description)

        await message.answer(
            escape_md(f"Канал @{channel_username} добавлен в список отслеживаемых.\n\nКраткое описание: {short_description}"),
            reply_markup=get_main_keyboard(user_id)
        )
    except Exception as e:
        await message.answer(escape_md(f"Ошибка при добавлении канала: {e}"))
    finally:
        await state.clear()


@dp.message(Command("remove_channel"))
@dp.message(lambda message: message.text == "Удалить канал")
async def remove_channel_menu(message: Message):
    """
    Обработчик команды /remove_channel ИЛИ нажатия на кнопку "Удалить канал".
    Показывает меню для удаления каналов.
    """
    user_id = message.from_user.id
    if is_active(user_id):
        await message.answer(
            escape_md("❌ Отслеживание активно. Сначала отключите бота, чтобы изменить список каналов."),
            reply_markup=get_main_keyboard(user_id)
        )
        return

    channels = get_user_channels(user_id)
    if not channels:
        await message.answer(escape_md("Вы не отслеживаете ни один канал."), reply_markup=get_main_keyboard(user_id))
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=channel["username"], callback_data=f"remove_{channel['username']}")]
        for channel in channels
    ])
    await message.answer(escape_md("Выберите канал для удаления:"), reply_markup=keyboard)


@dp.callback_query(lambda c: c.data.startswith("remove_"))
async def remove_channel_callback(callback_query: types.CallbackQuery):
    """
    Обработчик нажатия на кнопку удаления канала.
    """
    user_id = callback_query.from_user.id
    if is_active(user_id):
        await callback_query.answer(escape_md("❌ Отслеживание активно. Сначала отключите бота, чтобы изменить список каналов."))
        return

    channel_username = callback_query.data.replace("remove_", "")
    try:
        remove_user_channel(user_id, channel_username)
        await callback_query.answer(escape_md(f"Канал @{channel_username} удален из списка отслеживаемых."))
    except Exception as e:
        await callback_query.answer(escape_md(f"Ошибка при удалении канала: {e}"))

    channels = get_user_channels(user_id)
    if channels:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=ch["username"], callback_data=f"remove_{ch['username']}")]
            for ch in channels
        ])
        await callback_query.message.edit_text(escape_md("Выберите канал для удаления:"), reply_markup=keyboard)
    else:
        await callback_query.message.edit_text(escape_md("Вы больше не отслеживаете ни один канал."))


@dp.message(Command("list_channels"))
@dp.message(lambda message: message.text == "Список каналов")
async def list_channels(message: Message):
    """
    Обработчик команды /list_channels ИЛИ нажатия на кнопку "Список каналов".
    Показывает список отслеживаемых каналов и их описания.
    """
    user_id = message.from_user.id
    channels = get_user_channels(user_id)
    if not channels:
        await message.answer(escape_md("Вы не отслеживаете ни один канал."), reply_markup=get_main_keyboard(user_id))
        return

    channels_list = []
    for channel in channels:
        description = get_channel_description(user_id, channel["username"])
        channels_list.append(f"• @{channel['username']}: {description if description else 'Описание отсутствует'}")

    await message.answer(
        escape_md("📋 Список отслеживаемых каналов:\n\n" + "\n".join(channels_list)),
        reply_markup=get_main_keyboard(user_id)
    )


@dp.message(Command("new"))
@dp.message(lambda message: message.text == "Новые посты")
async def get_new_posts(message: Message):
    """
    Обработчик команды /new ИЛИ нажатия на кнопку "Новые посты".
    Отправляет пользователю непрочитанные посты из отслеживаемых каналов.
    """
    user_id = message.from_user.id
    if not is_active(user_id):
        await message.answer(
            escape_md("❌ Отслеживание не активировано. Сначала включите бота, чтобы получать новые посты."),
            reply_markup=get_main_keyboard(user_id)
        )
        return

    unread_posts = get_unread_posts(user_id)
    if not unread_posts:
        await message.answer(escape_md("Новых постов нет."), reply_markup=get_main_keyboard(user_id))
        return

    for post in unread_posts:
        await message.answer(
            escape_md(f"📄 Новый пост из @{post['channel_username']}:\n\n{post['summary']}")
        )
        # Сразу удаляем этот пост из БД
        mark_posts_as_read(user_id, post['id'])


@dp.message(Command("digest"))
@dp.message(lambda message: message.text == "Дайджест")
async def send_digest(message: Message):
    user_id = message.from_user.id
    if not is_active(user_id):
        await message.answer("❌ Отслеживание не активировано. Сначала включите бота, чтобы получать дайджест.")
        return

    # 1) Отправляем служебное сообщение о генерации
    waiting_msg = await message.answer("Генерируется дайджест...")

    # 2) Генерируем дайджест (может занять время)
    digest_text = await generate_digest(user_id)

    # 3) Удаляем сообщение "Генерируется дайджест..."
    await waiting_msg.delete()

    # 4) Отправляем сам дайджест
    await message.answer(digest_text)


    user_id = message.from_user.id
    if not is_active(user_id):
        await message.answer(
            escape_md("❌ Отслеживание не активировано. Сначала включите бота, чтобы получать дайджест."),
            reply_markup=get_main_keyboard(user_id)
        )
        return

    # Сгенерировать дайджест (внутри generate_digest в конце вызывается mark_posts_as_read)
    digest = await generate_digest(user_id)
    await message.answer(escape_md(digest), reply_markup=get_main_keyboard(user_id))
    # Здесь postы уже помечены как прочитанные => удалены из БД
    # благодаря логике в generate_digest и mark_posts_as_read.


async def main():
    """
    Основная функция для запуска бота.
    """
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logging.error(f"Ошибка при запуске бота: {e}")
    finally:
        await bot.session.close()


if __name__ == '__main__':
    asyncio.run(main())