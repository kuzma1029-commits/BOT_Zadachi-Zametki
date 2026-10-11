import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from bot.handlers import commands, messages
from config.settings import settings
from services.gigachat.client import giga_client
from services.grist.mcp_client import grist_client

logger = logging.getLogger("grist_bot")


async def on_startup() -> None:
    await grist_client.connect()
    await grist_client.warmup()
    logger.info("Grist MCP подключён, таблицы найдены")


async def on_shutdown() -> None:
    await grist_client.close()
    giga_client.close()
    logger.info("Соединения закрыты")


def create_bot() -> Bot:
    return Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
    )


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(commands.router)
    dp.include_router(messages.router)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    return dp


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("mcp.client.streamable_http").setLevel(logging.WARNING)
    bot = create_bot()
    dp = create_dispatcher()
    logger.info("Запуск бота...")
    dp.run_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    main()
