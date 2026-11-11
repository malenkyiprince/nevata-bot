"""Объединяем одновременные одинаковые проверки внутри одного процесса Vercel."""
import asyncio
import hashlib


class BusyError(Exception):
    pass


def request_key(user_id, kind, text, photo):
    digest = hashlib.sha256()
    for value in (str(user_id).encode(), kind.encode(), text.encode(), photo or b""):
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)
    return digest.digest()


class Inflight:
    def __init__(self, limit=8):
        self.tasks = {}
        self.limit = limit

    async def run(self, key, factory):
        # Никогда не ожидаем Task, принадлежащий другому event loop.
        scoped = (asyncio.get_running_loop(), key)
        task = self.tasks.get(scoped)
        if task is None:
            if len(self.tasks) >= self.limit:
                raise BusyError
            async def execute():
                try:
                    return await factory()
                finally:
                    self.tasks.pop(scoped, None)
            task = asyncio.create_task(execute())
            # Получаем исключение даже если все HTTP-клиенты отключились.
            task.add_done_callback(lambda finished: None if finished.cancelled() else finished.exception())
            self.tasks[scoped] = task
        # Отключение одного клиента не отменяет общий запрос второго клиента.
        return await asyncio.shield(task)
