import logging
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from openai import AsyncOpenAI
from CONFIG import OPENAI_API, CHECK_INTERVAL, POST_LIMIT, OPENAI_MODEL, OPENAI_MAX_TOKENS
from database import add_post, get_last_post_number, is_post_processed, create_user_tables, get_user_channels, mark_channel_as_old, get_channel_description
from ai_analyzer import generate_summary_of_best_posts

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Настройки OpenAI
client = AsyncOpenAI(api_key=OPENAI_API)

def truncate_text(text, max_tokens):
    """
    Обрезает текст до указанного количества токенов.
    """
    tokens = text.split()
    if len(tokens) > max_tokens:
        return " ".join(tokens[:max_tokens])
    return text

async def fetch_channel_page(channel_username):
    """
    Асинхронно получает HTML-страницу канала.
    """
    url = f"https://t.me/s/{channel_username}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                raise Exception(f"Ошибка при запросе к каналу: {response.status}")
            return await response.text()

async def get_last_posts(channel_username, limit=POST_LIMIT):
    """
    Получает последние посты из публичного Telegram-канала.
    """
    try:
        html = await fetch_channel_page(channel_username)
        soup = BeautifulSoup(html, 'html.parser')
        posts = []
        for message in soup.find_all('div', class_='tgme_widget_message', limit=limit):
            post_id = message.get('data-post')
            post_content = {'id': post_id}

            # Проверяем наличие текста
            text = message.find('div', class_='tgme_widget_message_text')
            if text:
                post_content['text'] = text.get_text(strip=True)
            else:
                # Если текста нет, проверяем наличие медиа
                media_types = {
                    'photo': "[Картинка]",
                    'video': "[Видео]",
                    'gif': "[GIF]",
                    'document': "[Файл]"
                }
                post_content['text'] = "[Медиа]"
                for media_type, label in media_types.items():
                    if message.find('div', class_=f'tgme_widget_message_{media_type}'):
                        post_content['text'] = label
                        break

            posts.append(post_content)
        return posts
    except Exception as e:
        logging.error(f"Ошибка при получении постов из канала @{channel_username}: {e}")
        return []

async def check_new_posts(user_id):
    """
    Проверяет новые посты в каналах и возвращает список выжимок и флаг наличия новых постов.
    Для новых каналов анализирует только 5 последних постов.
    """
    summaries = []
    new_posts_found = False

    # Получаем каналы, добавленные пользователем
    user_channels = get_user_channels(user_id)
    if not user_channels:
        logging.info(f"Пользователь {user_id} не добавил ни одного канала.")
        return summaries, new_posts_found

    for channel in user_channels:
        channel_username = channel["username"]
        is_new_channel = channel["is_new_channel"]


        limit = 5 if is_new_channel else POST_LIMIT
        posts = await get_last_posts(channel_username, limit=limit)
        for post in posts:
            if not is_post_processed(user_id, post['id']):
                new_posts_found = True
                last_post_number = get_last_post_number(user_id) + 1
                if post['text'] in ["[Картинка]", "[Видео]", "[GIF]", "[Файл]", "[Медиа]"]:
                    summary = post['text']
                else:
                    summary = await generate_summary_of_best_posts([post], get_channel_description(user_id, channel_username))
                summaries.append(f"📢 Канал: @{channel_username}\n\n{summary}")
                add_post(user_id, post['id'], post['text'], summary, last_post_number, channel_username)
                logging.info(f"Пост {post['id']} добавлен в базу данных для пользователя {user_id}.")

        # Если канал был новым, после первого сканирования он больше не считается новым
        if is_new_channel:
            mark_channel_as_old(user_id, channel_username)

    return summaries, new_posts_found

async def auto_update(user_id):
    """
    Автоматически проверяет новые посты каждые N секунд.
    """
    no_posts_message_shown = False

    while True:
        summaries, new_posts_found = await check_new_posts(user_id)
        if new_posts_found:
            for summary in summaries:
                logging.info(summary)
            no_posts_message_shown = False
        elif not no_posts_message_shown:
            logging.info("Новых постов нет :(")
            no_posts_message_shown = True

        await asyncio.sleep(CHECK_INTERVAL)

async def start_ai_main(user_id):
    """
    Запускает AI_main для конкретного пользователя.
    """
    create_user_tables(user_id)  # Создаем таблицы для пользователя
    await auto_update(user_id)