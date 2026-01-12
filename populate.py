import asyncio

from database.general import populate_db

if __name__ == "__main__":
    asyncio.run(populate_db())
