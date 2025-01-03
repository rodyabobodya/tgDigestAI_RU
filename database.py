import sqlite3
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def create_user_tables(user_id):
    """
    Создает таблицы для пользователя, если они еще не существуют.
    """
    conn = sqlite3.connect(f"user_{user_id}.db")
    cursor = conn.cursor()
    try:
        # Таблица для хранения каналов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                is_new_channel INTEGER DEFAULT 1  -- 1 - новый канал, 0 - не новый
            )
        ''')

        # Таблица для хранения постов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id TEXT NOT NULL UNIQUE,
                content TEXT NOT NULL,
                summary TEXT,
                post_number INTEGER,
                channel_username TEXT NOT NULL,
                is_read INTEGER DEFAULT 0
            )
        ''')

        # Таблица для хранения состояния пользователя
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_state (
                id INTEGER PRIMARY KEY DEFAULT 1,
                is_active INTEGER DEFAULT 0
            )
        ''')

        # Таблица для хранения описаний каналов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS channel_descriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                description TEXT
            )
        ''')

        # Таблица для хранения подробных описаний каналов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS detailed_channel_descriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                description TEXT
            )
        ''')

        conn.commit()
        logging.info(f"Таблицы созданы для пользователя {user_id}.")
    except Exception as e:
        logging.error(f"Ошибка при создании таблиц для пользователя {user_id}: {e}")
    finally:
        conn.close()

def add_post(user_id, post_id, content, summary, post_number, channel_username):
    """
    Добавляет пост в базу данных.
    """
    conn = sqlite3.connect(f"user_{user_id}.db")
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO posts (post_id, content, summary, post_number, channel_username, is_read)
            VALUES (?, ?, ?, ?, ?, 0)
        ''', (post_id, content, summary, post_number, channel_username))
        conn.commit()
        logging.info(f"Пост {post_id} добавлен в базу данных для пользователя {user_id}.")
    except sqlite3.IntegrityError:
        logging.warning(f"Пост {post_id} уже существует в базе данных для пользователя {user_id}.")
    except Exception as e:
        logging.error(f"Ошибка при добавлении поста {post_id}: {e}")
    finally:
        conn.close()

def get_last_post_number(user_id):
    """
    Возвращает номер последнего добавленного поста.
    """
    conn = sqlite3.connect(f"user_{user_id}.db")
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT MAX(post_number) FROM posts')
        last_post_number = cursor.fetchone()[0]
        logging.info(f"Последний номер поста для пользователя {user_id}: {last_post_number}.")
        return last_post_number if last_post_number else 0
    except Exception as e:
        logging.error(f"Ошибка при получении последнего номера поста для пользователя {user_id}: {e}")
        return 0
    finally:
        conn.close()

def is_post_processed(user_id, post_id):
    """
    Проверяет, был ли пост уже обработан (добавлен в базу).
    """
    conn = sqlite3.connect(f"user_{user_id}.db")
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT 1 FROM posts WHERE post_id = ?', (post_id,))
        result = cursor.fetchone()
        return result is not None
    except Exception as e:
        logging.error(f"Ошибка при проверке поста {post_id} для пользователя {user_id}: {e}")
        return False
    finally:
        conn.close()

def get_user_channels(user_id):
    """
    Возвращает список отслеживаемых каналов для пользователя и их статус (новый/не новый).
    """
    conn = sqlite3.connect(f"user_{user_id}.db")
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT username, is_new_channel FROM channels')
        rows = cursor.fetchall()
        channels = [{"username": row[0], "is_new_channel": row[1]} for row in rows]
        return channels
    except Exception as e:
        logging.error(f"Ошибка при получении каналов для пользователя {user_id}: {e}")
        return []
    finally:
        conn.close()

def get_unread_posts(user_id):
    """
    Возвращает список непрочитанных постов для пользователя.
    Переименовываем 'content' -> 'text', чтобы код работал с post['text'].
    """
    conn = sqlite3.connect(f"user_{user_id}.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT id, post_id, channel_username, content, summary FROM posts WHERE is_read = 0')
        posts = cursor.fetchall()
        logging.info(f"Найдено {len(posts)} непрочитанных постов для пользователя {user_id}.")
    except Exception as e:
        logging.error(f"Ошибка при получении непрочитанных постов для пользователя {user_id}: {e}")
        posts = []
    finally:
        conn.close()

    posts_list = []
    for row in posts:
        row_dict = dict(row)
        row_dict["text"] = row_dict.pop("content", "")
        posts_list.append(row_dict)

    return posts_list

def mark_posts_as_read(user_id, post_id):
    """
    Помечает пост как прочитанный (is_read = 1), но не удаляет его из базы.
    """
    conn = sqlite3.connect(f"user_{user_id}.db")
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE posts SET is_read = 1 WHERE id = ?', (post_id,))
        conn.commit()
        logging.info(f"Пост {post_id} помечен как прочитанный для пользователя {user_id}.")
    except Exception as e:
        logging.error(f"Ошибка при пометке поста {post_id} как прочитанного: {e}")
    finally:
        conn.close()

def add_user_channel(user_id, channel_username):
    """
    Добавляет канал в список отслеживаемых для пользователя.
    Если канал добавляется впервые, он считается новым.
    """
    conn = sqlite3.connect(f"user_{user_id}.db")
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO channels (username, is_new_channel) VALUES (?, 1)', (channel_username,))
        conn.commit()
        logging.info(f"Канал @{channel_username} добавлен для пользователя {user_id}.")
    except sqlite3.IntegrityError:
        logging.warning(f"Канал @{channel_username} уже существует для пользователя {user_id}.")
    except Exception as e:
        logging.error(f"Ошибка при добавлении канала @{channel_username}: {e}")
    finally:
        conn.close()

def remove_user_channel(user_id, channel_username):
    """
    Удаляет канал из списка отслеживаемых для пользователя и все связанные данные:
    - Сам канал (channels)
    - Все посты из этого канала (posts)
    - Краткое описание (channel_descriptions)
    - Подробное описание (detailed_channel_descriptions)
    """
    conn = sqlite3.connect(f"user_{user_id}.db")
    cursor = conn.cursor()
    try:
        # Удаляем сам канал
        cursor.execute('DELETE FROM channels WHERE username = ?', (channel_username,))
        # Удаляем все посты из этого канала
        cursor.execute('DELETE FROM posts WHERE channel_username = ?', (channel_username,))
        # Удаляем краткое описание
        cursor.execute('DELETE FROM channel_descriptions WHERE username = ?', (channel_username,))
        # Удаляем подробное описание
        cursor.execute('DELETE FROM detailed_channel_descriptions WHERE username = ?', (channel_username,))
        conn.commit()
        logging.info(f"Канал @{channel_username} и все связанные посты/описания удалены для пользователя {user_id}.")
    except Exception as e:
        logging.error(f"Ошибка при удалении канала @{channel_username}: {e}")
    finally:
        conn.close()

def is_active(user_id):
    """
    Проверяет, активно ли отслеживание для пользователя.
    """
    conn = sqlite3.connect(f"user_{user_id}.db")
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT is_active FROM user_state WHERE id = 1')
        result = cursor.fetchone()
        return (result[0] == 1) if result else False
    except Exception as e:
        logging.error(f"Ошибка при проверке состояния пользователя {user_id}: {e}")
        return False
    finally:
        conn.close()

def activate_user(user_id):
    """
    Активирует отслеживание для пользователя.
    """
    conn = sqlite3.connect(f"user_{user_id}.db")
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT OR REPLACE INTO user_state (id, is_active) VALUES (1, 1)')
        conn.commit()
        logging.info(f"Отслеживание активировано для пользователя {user_id}.")
    except Exception as e:
        logging.error(f"Ошибка при активации отслеживания для пользователя {user_id}: {e}")
    finally:
        conn.close()

def deactivate_user(user_id):
    """
    Деактивирует отслеживание для пользователя.
    """
    conn = sqlite3.connect(f"user_{user_id}.db")
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT OR REPLACE INTO user_state (id, is_active) VALUES (1, 0)')
        conn.commit()
        logging.info(f"Отслеживание деактивировано для пользователя {user_id}.")
    except Exception as e:
        logging.error(f"Ошибка при деактивации отслеживания для пользователя {user_id}: {e}")
    finally:
        conn.close()

def mark_channel_as_old(user_id, channel_username):
    """
    Помечает канал как "не новый" после первого сканирования.
    """
    conn = sqlite3.connect(f"user_{user_id}.db")
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE channels SET is_new_channel = 0 WHERE username = ?', (channel_username,))
        conn.commit()
        logging.info(f"Канал @{channel_username} больше не считается новым для пользователя {user_id}.")
    except Exception as e:
        logging.error(f"Ошибка при обновлении статуса канала @{channel_username}: {e}")
    finally:
        conn.close()

def add_channel_description(user_id, channel_username, description):
    """
    Добавляет (или обновляет) краткое описание канала в базу данных.
    """
    conn = sqlite3.connect(f"user_{user_id}.db")
    cursor = conn.cursor()
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS channel_descriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                description TEXT
            )
        ''')
        cursor.execute('INSERT OR REPLACE INTO channel_descriptions (username, description) VALUES (?, ?)',
                       (channel_username, description))
        conn.commit()
        logging.info(f"Краткое описание канала @{channel_username} добавлено/обновлено для пользователя {user_id}.")
    except Exception as e:
        logging.error(f"Ошибка при добавлении краткого описания канала @{channel_username}: {e}")
    finally:
        conn.close()

def add_detailed_channel_description(user_id, channel_username, description):
    """
    Добавляет (или обновляет) подробное описание канала в базу данных.
    """
    conn = sqlite3.connect(f"user_{user_id}.db")
    cursor = conn.cursor()
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS detailed_channel_descriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                description TEXT
            )
        ''')
        cursor.execute('INSERT OR REPLACE INTO detailed_channel_descriptions (username, description) VALUES (?, ?)',
                       (channel_username, description))
        conn.commit()
        logging.info(f"Подробное описание канала @{channel_username} добавлено/обновлено для пользователя {user_id}.")
    except Exception as e:
        logging.error(f"Ошибка при добавлении подробного описания канала @{channel_username}: {e}")
    finally:
        conn.close()

def get_channel_description(user_id, channel_username):
    """
    Возвращает краткое описание канала из таблицы channel_descriptions.
    """
    conn = sqlite3.connect(f"user_{user_id}.db")
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT description FROM channel_descriptions WHERE username = ?', (channel_username,))
        result = cursor.fetchone()
        return result[0] if result else None
    except Exception as e:
        logging.error(f"Ошибка при получении описания канала @{channel_username}: {e}")
        return None
    finally:
        conn.close()