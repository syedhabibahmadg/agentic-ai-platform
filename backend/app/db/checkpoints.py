import asyncio

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.db.session import postgres_dsn


async def setup():
    async with AsyncPostgresSaver.from_conn_string(postgres_dsn()) as saver:
        await saver.setup()


if __name__ == "__main__":
    asyncio.run(setup())
