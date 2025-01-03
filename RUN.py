import asyncio
import logging

# Настройка логирования
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

async def run_script(script_name):
    """Запускает Python-скрипт асинхронно."""
    try:
        logging.info(f"Запуск скрипта: {script_name}")
        process = await asyncio.create_subprocess_exec("python", script_name)
        await process.wait()
        if process.returncode == 0:
            logging.info(f"Скрипт {script_name} завершен успешно.")
        else:
            logging.error(f"Скрипт {script_name} завершен с ошибкой (код: {process.returncode}).")
    except Exception as e:
        logging.error(f"Ошибка при запуске скрипта {script_name}: {e}")

async def main():
    """Запускает все скрипты одновременно."""
    await asyncio.gather(
        run_script("AI_main.py"),
        run_script("bot.py"),
        run_script("ai_analyzer.py"),
        run_script("channel_analyzer.py"),
        run_script("database.py")
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Программа завершена пользователем.")
    except Exception as e:
        logging.error(f"Ошибка в главной функции: {e}")