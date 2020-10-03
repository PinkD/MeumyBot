import asyncio
import hashlib
import random
import time

from functools import wraps, partial


def gen_token():
    data = f"{time.time()}_{random.randint(0, 1024)}".encode()
    key = hashlib.md5(data).hexdigest()
    return f"key_{key[4:]}"


def async_wrap(func):
    @wraps(func)
    async def run(*args, loop=None, executor=None, **kwargs):
        if loop is None:
            loop = asyncio.get_event_loop()
        f = partial(func, *args, **kwargs)
        return await loop.run_in_executor(executor, f)

    return run


def format_time(t: int):
    t = time.localtime(t)
    return time.strftime("%Y-%m-%d %H:%M:%S %z", t)
