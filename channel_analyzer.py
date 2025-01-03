import logging
from openai import AsyncOpenAI
from CONFIG import OPENAI_API, OPENAI_MODEL, OPENAI_MAX_TOKENS

# Настройка логирования
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Настройки OpenAI
client = AsyncOpenAI(api_key=OPENAI_API)

async def analyze_channel_content(posts):
    """
    Анализирует контент канала на основе последних постов и создает краткое описание.
    """
    if not posts:
        return "Канал не содержит постов."

    try:
        # Объединяем тексты постов в один текст для анализа
        content = "\n\n".join([post['text'] for post in posts if 'text' in post and post['text'].strip()])

        # Запрашиваем у OpenAI краткое описание канала
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Ты — эксперт, который анализирует контент каналов и создает краткие описания."},
                {"role": "user", "content": f"Проанализируй контент этого канала и составь список основных тем, которые канал затрагивает, самые упоминаемые проекты/термины. Всего уложись в 4-5 предложений.\n\n{content}"}
            ],
            max_tokens=OPENAI_MAX_TOKENS
        )
        description = response.choices[0].message.content
        logging.info(f"Создано описание канала: {description}")
        return description
    except Exception as e:
        logging.error(f"Ошибка при анализе контента канала: {e}")
        return "Не удалось создать описание канала."

async def filter_unrelated_posts(posts, channel_description):
    """
    Фильтрует посты, которые не связаны с тематикой канала.
    """
    if not posts or not channel_description:
        return posts  # Если постов или описания нет, возвращаем оригинальный список

    try:
        # Объединяем тексты постов в один текст для анализа
        content = "\n\n".join([post['text'] for post in posts if 'text' in post and post['text'].strip()])

        # Запрашиваем у OpenAI фильтрацию постов
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Ты — помощник, который фильтрует посты на основе тематики канала. Будь менее строг при отборе."},
                {"role": "user", "content": f"Описание канала: {channel_description}\n\nОтфильтруй эти посты и оставь только те, которые хотя бы частично связаны с тематикой канала, без жёсткого отсечения:\n\n{content}"}
            ],
            max_tokens=OPENAI_MAX_TOKENS
        )
        # Предположим, что модель возвращает в ответ список постов (или фрагменты)
        filtered_posts = response.choices[0].message.content.split("\n\n")
        logging.info(f"Отфильтровано постов: {len(filtered_posts)}")
        return [post for post in posts if post['text'] in filtered_posts]
    except Exception as e:
        logging.error(f"Ошибка при фильтрации постов: {e}")
        return posts  # В случае ошибки возвращаем оригинальный список

async def create_short_channel_description(posts):
    """
    Создает краткое описание канала для отображения в list_channels.
    """
    if not posts:
        return "Канал не содержит постов."

    try:
        # Объединяем тексты постов в один текст для анализа
        content = "\n\n".join([post['text'] for post in posts if 'text' in post and post['text'].strip()])

        # Запрашиваем у OpenAI краткое описание канала
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Ты — эксперт, который анализирует контент каналов и создает краткие описания."},
                {"role": "user", "content": f"Проанализируй контент этого канала и составь краткое описание его тематики. Описание должно быть коротким, максимум 2-3 предложения:\n\n{content}"}
            ],
            max_tokens=100  # Ограничиваем количество токенов для краткости
        )
        description = response.choices[0].message.content
        logging.info(f"Создано краткое описание канала: {description}")
        return description
    except Exception as e:
        logging.error(f"Ошибка при создании краткого описания канала: {e}")
        return "Не удалось создать краткое описание канала."

async def create_detailed_channel_description(posts):
    """
    Создает подробное описание канала для фильтрации контента.
    """
    if not posts:
        return "Канал не содержит постов."

    try:
        # Объединяем тексты постов в один текст для анализа
        content = "\n\n".join([post['text'] for post in posts if 'text' in post and post['text'].strip()])

        # Запрашиваем у OpenAI подробное описание канала
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Ты — эксперт, который анализирует контент каналов и создает подробные описания."},
                {"role": "user", "content": f"Проанализируй контент этого канала и создай подробное описание его тематики, основных тем и ключевых идей. Будь детальным, но не слишком строгим при описании границ тематики:\n\n{content}"}
            ],
            max_tokens=OPENAI_MAX_TOKENS
        )
        description = response.choices[0].message.content
        logging.info(f"Создано подробное описание канала: {description}")
        return description
    except Exception as e:
        logging.error(f"Ошибка при создании подробного описания канала: {e}")
        return "Не удалось создать подробное описание канала."

async def is_post_relevant(post_text, channel_description):
    """
    Проверяет, соответствует ли пост тематике канала.
    Возвращает True, если пост релевантен, и False, если нет.
    """
    if not post_text or not channel_description:
        logging.info("Пост или описание канала отсутствуют. Считаем пост нерелевантным.")
        return False

    try:
        # Формируем запрос к OpenAI
        user_content = (f"Описание канала: {channel_description}\n\nПост: {post_text}\n\nСоответствует ли пост тематике канала?"
                        f"Ответь только 'Да' или 'Нет'."
                        f"Если ты замечаешь, что пост - это реклама чего-либо (сервиса, приложения, другого канала), то"
                        f"сразу пиши 'нет'."
                        f"Ни в коем случае не добавляй разметку заголовков и подзаголовков.")

        # Отправляем запрос к OpenAI
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Ты — помощник, который анализирует, соответствует ли пост тематике канала."},
                {"role": "user", "content": user_content}
            ],
            max_tokens=10
        )

        # Получаем ответ от OpenAI
        decision = response.choices[0].message.content.strip().lower()

        # Логируем ответ нейросети
        logging.info(f"Ответ нейросети на релевантность поста: {decision}")

        return decision == "да"
    except Exception as e:
        logging.error(f"Ошибка при проверке соответствия поста тематике канала: {e}")
        return False