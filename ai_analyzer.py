import logging
from openai import AsyncOpenAI
from CONFIG import OPENAI_API, OPENAI_MODEL, OPENAI_MAX_TOKENS
from database import get_unread_posts, mark_posts_as_read, get_channel_description
from channel_analyzer import is_post_relevant
import sqlite3

# Настройка логирования
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Настройки OpenAI
client = AsyncOpenAI(api_key=OPENAI_API)

async def analyze_post_quality(post_text):
    """
    Анализирует качество и достоверность поста с использованием OpenAI.
    Если информация в посте ненужная или мусор, возвращает '.'.
    """
    if not post_text or not post_text.strip():  # Если текст пустой или отсутствует, считаем его мусором
        return "."

    try:
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Ты — эксперт, который анализирует тексты на качество и достоверность."},
                {"role": "user", "content": f"Проанализируй этот текст и оцени его качество и достоверность. Если, по твоему мнению, информация в посте ненужная или же просто мусор, то напиши вместо анализа '.': \n\n{post_text}"}
            ],
            max_tokens=OPENAI_MAX_TOKENS
        )
        analysis = response.choices[0].message.content
        logging.info(f"Анализ поста: {analysis}")
        return analysis
    except Exception as e:
        logging.error(f"Ошибка при анализе поста: {e}")
        return "."

async def generate_summary_of_best_posts(posts, channel_description):
    """
    Генерирует краткую и конкретную выжимку по самым полезным постам.
    Если постов нет или они не содержат текста, возвращает пустую строку.
    """
    if not posts:
        logging.info("Нет постов для генерации выжимки.")
        return ""

    # Фильтруем посты, оставляя только те, которые соответствуют тематике канала
    relevant_posts = []
    for post in posts:
        if 'text' in post and post['text'].strip():
            if await is_post_relevant(post['text'], channel_description):
                relevant_posts.append(post)

    if not relevant_posts:
        logging.info("Нет постов с текстом, соответствующих тематике канала.")
        return ""

    try:
        content = "\n\n".join([f"Пост {i+1}:\n{post['text']}" for i, post in enumerate(relevant_posts)])
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Ты — секретарь, который делает краткие и конкретные выжимки. Пиши только самое важное, без лишних слов."},
                {"role": "user", "content": f"Сделай краткую выжимку по этим постам. Пиши только самое важное, без повторов и лишних деталей:\n\n{content}"}
            ],
            max_tokens=OPENAI_MAX_TOKENS
        )
        summary = response.choices[0].message.content
        logging.info(f"Сгенерирована выжимка: {summary}")
        return summary
    except Exception as e:
        logging.error(f"Ошибка при генерации выжимки: {e}")
        return "Не удалось сгенерировать выжимку."

async def remove_duplicate_summaries(summaries):
    """
    Убирает повторяющиеся мысли из списка выжимок.
    Если список пустой, возвращает пустой список.
    """
    if not summaries:
        logging.info("Список выжимок пуст. Пропускаем удаление дубликатов.")
        return []

    try:
        # Объединяем все выжимки в один текст
        combined_summaries = "\n\n".join(summaries)

        # Запрашиваем у OpenAI удаление дубликатов
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Ты — помощник, который анализирует тексты и удаляет повторяющиеся мысли."},
                {"role": "user", "content": f"Проанализируй эти выжимки и оставь только уникальные мысли по темам из постов. "
                                            f"Слишком мощно тоже не убирай все, оставляй многое. "
                                            f"Ни в коем случае не добавляй разметку заголовков и подзаголовков:\n\n{combined_summaries}"}
            ],
            max_tokens=OPENAI_MAX_TOKENS
        )
        unique_summaries = response.choices[0].message.content
        return unique_summaries.split("\n\n")  # Разделяем обратно на отдельные выжимки
    except Exception as e:
        logging.error(f"Ошибка при удалении дубликатов: {e}")
        return summaries  # Возвращаем оригинальный список в случае ошибки



def get_channel_username_from_db(user_id, post_id):
    """
    Возвращает channel_username для поста по его ID.
    """
    conn = sqlite3.connect(f"user_{user_id}.db")
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT channel_username FROM posts WHERE id = ?', (post_id,))
        result = cursor.fetchone()
        return result[0] if result else None
    except Exception as e:
        logging.error(f"Ошибка при получении channel_username для поста {post_id}: {e}")
        return None
    finally:
        conn.close()


async def generate_digest(user_id):
    """
    Генерирует дайджест всех непрочитанных (is_read=0) постов, разбивая их по каналам.
    Для каждого НЕпустого summary создаём скрытую ссылку [Ссылка].
    Если summary пустое (мусор), пост не попадает в дайджест.
    """
    unread_posts = get_unread_posts(user_id)
    if not unread_posts:
        return "Нет новых постов для дайджеста."

    # Группируем посты по каналам
    posts_by_channel = {}
    for post in unread_posts:
        channel = post['channel_username']
        if channel not in posts_by_channel:
            posts_by_channel[channel] = []
        posts_by_channel[channel].append(post)

    digest_parts = []

    for channel_username, posts in posts_by_channel.items():
        channel_description = get_channel_description(user_id, channel_username) or "Канал без описания."

        # Сюда будем складывать строки дайджеста для данного канала
        channel_digest_lines = []

        for post in posts:
            # Генерируем выжимку для одного поста
            summary = await generate_summary_of_best_posts([post], channel_description)

            # Если summary пустая, пропускаем этот пост (он считается мусором)
            if not summary or not summary.strip():
                continue

            # Формируем ссылку
            post_link = f"https://t.me/{channel_username}/{post['post_id']}"
            line_text = f"{summary}\n [Ссылка]({post_link})"
            channel_digest_lines.append(line_text)

        if channel_digest_lines:
            combined_text = "\n\n".join(channel_digest_lines)
            digest_parts.append(f"Канал: @{channel_username}\n\n{combined_text}")

    # Все непрочитанные посты (включая те, у которых summary оказалось пустым) помечаем как прочитанные,
    # чтобы не предлагать их повторно в будущем.
    for post in unread_posts:
        mark_posts_as_read(user_id, post['id'])

    # Если после фильтрации «мусора» ничего не осталось
    if not digest_parts:
        return "Нет полезных постов для дайджеста."

    return "\n\n".join(digest_parts)

async def is_summary_relevant(summary, channel_description):
    """
    Проверяет, соответствует ли summary описанию канала.
    Если summary не по теме или бессмысленна, возвращает False (мусор).
    """
    if not summary or not channel_description:
        logging.info("Summary или описание канала отсутствуют. Считаем summary мусором.")
        return False

    try:
        # Формируем запрос к OpenAI
        user_content = f"Описание канала: {channel_description}\n\nSummary: {summary}\n\nСоответствует ли summary описанию канала? Ответь только 'Да' или 'Нет'."
        # Логируем запрос
        logging.info(f"Запрос к OpenAI:\n{user_content}")
        # Отправляем запрос к OpenAI
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Ты — помощник, который анализирует, соответствует ли summary описанию канала."},
                {"role": "user", "content": user_content}
            ],
            max_tokens=10
        )

        # Получаем ответ от OpenAI
        decision = response.choices[0].message.content.strip().lower()

        # Логируем ответ
        logging.info(f"Ответ от OpenAI: {decision}")

        return decision == "да"
    except Exception as e:
        logging.error(f"Ошибка при проверке summary: {e}")
        return False  # В случае ошибки считаем summary мусором