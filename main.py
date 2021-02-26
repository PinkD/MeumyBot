import asyncio
import random
import threading
import time
import logging

import telegram
from telegram import Update, Bot, InputMediaPhoto, ParseMode, InlineKeyboardMarkup, \
    InlineKeyboardButton
from telegram.ext import CallbackContext
from telegram.ext import CommandHandler
from telegram.ext import Filters
from telegram.ext import Updater
from telegram.ext import run_async

from bilibili.api import Bilibili
from bilibili.model import Dynamic, DynamicType, LiveStatus, Live
from config import TOKEN, UID_LIST, BOT_NAME, MIN_SEND_DELAY, MIN_FETCH_DELAY, FETCH_INTERVAL, ADMIN_USERNAMES, \
    LOG_LEVEL, LOG_FILE
from db import Database
from utils import gen_token, async_wrap, format_time


def send_msg(update: Update, context: CallbackContext, msg: str, md=False):
    chat_id = update.effective_chat.id
    reply_id = update.message.message_id
    if md:
        context.bot.send_message(
            chat_id=chat_id,
            reply_to_message_id=reply_id,
            text=msg,
            parse_mode=ParseMode.MARKDOWN_V2)
    else:
        context.bot.send_message(chat_id=chat_id, reply_to_message_id=reply_id, text=msg)


@run_async
def cmd_start(update: Update, context: CallbackContext):
    send_msg(update, context, "I'm Meumy bot to dispatch meumy dynamics")


def strip_msg(cmd, text: str) -> str:
    text = text.lstrip(f"/{cmd}")
    text = text.lstrip(f"@{BOT_NAME}")
    return text.strip()


# register vtb for a chat
# /register token
@run_async
def cmd_register(update: Update, context: CallbackContext):
    msg = strip_msg("register", update.message.text)
    # /register@bot_name token
    if len(msg) == 0:
        send_msg(update, context, "/register token")
        return
    token = msg.strip()
    if token in tokens:
        full_name = update.effective_user.full_name
        username = update.effective_user.username
        chat_username = update.effective_chat.username
        chat_id = update.effective_chat.id
        logging.info(f"{full_name}({username}) register callback for {chat_username}({chat_id}))")
        tokens.remove(token)
        chats.add(chat_id)
        db.add_subscribe(chat_id)
        send_msg(update, context, "success, this chat will be notified when meumy post new message")
    else:
        send_msg(update, context, "please contact the bot owner to get the token")


# unregister vtb for a chat
# /unregister@bot_name token
@run_async
def cmd_unregister(update: Update, context: CallbackContext):
    msg = strip_msg("unregister", update.message.text)
    if len(msg) == 0:
        send_msg(update, context, "/unregister token")
    token = msg.strip()
    if token in tokens:
        full_name = update.effective_user.full_name
        username = update.effective_user.username
        chat_username = update.effective_chat.username
        chat_id = update.effective_chat.id
        logging.info(f"{full_name}({username}) unregister callback for {chat_username}({chat_id}))")
        tokens.remove(token)
        chats.remove(chat_id)
        db.del_subscribe(chat_id)
        send_msg(update, context, "success, this chat will not be notified")
    else:
        send_msg(update, context, "this token is invalid")


# generate a token
# only for admin
@run_async
def cmd_token(update: Update, context: CallbackContext):
    username = update.effective_user.username
    logging.info(f"{username} try to generate token")
    if username in ADMIN_USERNAMES:
        token = gen_token()
        tokens.add(token)
        logging.info(f"token generated by {username}")
        send_msg(update, context, f"one time token generated: `{token}`", md=True)
    else:
        logging.info(f"denied for {username}")
        send_msg(update, context, "permission denied, please contact the bot owner")


def origin_link(content):
    return InlineKeyboardMarkup([[InlineKeyboardButton(text="link", url=content)]])


def room_link(room_id):
    return f"https://live.bilibili.com/{room_id}"


async def send_live_to(chat_id, l: Live):
    @async_wrap
    def send(chat_id, l: Live):
        bot: Bot = updater.bot
        t = format_time(l.live_start_time)
        text = f"{l.user} is living:\n{t}\n------\n{l.title}"
        bot.send_photo(
            chat_id=chat_id,
            photo=l.cover,
            caption=text,
            reply_markup=origin_link(room_link(l.room_id))
        )

    try:
        await send(chat_id, l)
    except telegram.TelegramError as e:
        logging.warning(f"failed to send {l} to {chat_id}: {e}")


async def send_dynamic_to(chat_id, d: Dynamic):
    @async_wrap
    def send(chat_id, d: Dynamic):
        bot: Bot = updater.bot
        t = format_time(d.timestamp)
        text = f"{d.user}:\n{t}\n------\n{d.text}"
        try:
            if d.type == DynamicType.FORWARD and len(d.photos) != 0 or \
                    d.type == DynamicType.PHOTO:
                if len(d.photos) == 1:
                    if d.photos[0].endswith(".gif"):
                        bot.send_animation(
                            chat_id=chat_id,
                            animation=d.photos[0],
                            caption=text,
                            reply_markup=origin_link(d.link)
                        )
                    else:
                        bot.send_photo(
                            chat_id=chat_id,
                            photo=d.photos[0],
                            caption=text,
                            reply_markup=origin_link(d.link)
                        )
                else:
                    medias = [
                        InputMediaPhoto(photo) for photo in d.photos
                    ]
                    bot.send_media_group(
                        chat_id=chat_id,
                        media=medias,
                    )
                    bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        reply_markup=origin_link(d.link),
                    )
            elif d.type == DynamicType.FORWARD and len(d.photos) == 0 or \
                    d.type == DynamicType.PLAIN:
                bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=origin_link(d.link),
                )
            elif d.type == DynamicType.VIDEO:
                bot.send_photo(
                    chat_id=chat_id,
                    photo=d.photos[0],
                    caption=text,
                    reply_markup=origin_link(d.link),
                )
        except telegram.error.TimedOut:
            logging.warning(f"send message to {chat_id} time out, dynamic is {d}")

    await asyncio.sleep(MIN_SEND_DELAY)
    try:
        await send(chat_id, d)
    except telegram.TelegramError as e:
        logging.warning(f"failed to send {d} to {chat_id}: {e}")


async def send_to_all(d: Dynamic = None, l: Live = None):
    tasks = []
    if d is not None:
        for chat_id in chats:
            tasks.append(send_dynamic_to(chat_id, d))
    if l is not None:
        for chat_id in chats:
            tasks.append(send_live_to(chat_id, l))
    await asyncio.gather(*tasks)


async def fetch_and_send_single(uid: int):
    try:
        dyn = await fetcher.fetch(uid, fetch_record[uid])
    except KeyError as e:
        print(f"fetch dynamic for {uid}: {e}")
        return
    dyn.sort(key=lambda d: d.timestamp)

    if (l := len(dyn)) != 0:
        logging.info(f"fetched {l} dynamics for {uid}")
    tasks = []
    for d in dyn:
        logging.info(f"send_to_all {d}")
        tasks.append(send_to_all(d=d))
        fetch_record[uid] = d.timestamp
    await asyncio.gather(*tasks)
    last_status = live_record[uid]
    try:
        l = await fetcher.live(uid, last_status)
    except (KeyError, TypeError) as e:
        print(f"fetch live for {uid}: {e}")
        return
    if l is None:
        return
    if last_status == LiveStatus.PREPARE and l.status == LiveStatus.LIVE:
        logging.info(f"{uid} is now living")
        logging.debug(f"send_to_all {l}")
        await send_to_all(l=l)
        db.add_live(uid)
    else:
        db.del_live(uid)
    live_record[uid] = l.status


async def fetch_all():
    for uid in fetch_record:
        start = time.time()
        await fetch_and_send_single(uid)
        min_interval = MIN_FETCH_DELAY
        t = random.random()
        t += 1
        t *= min_interval
        t -= time.time() - start
        if t <= 0:
            logging.warning(f"sleep time {t} less than 0, skip")
        else:
            logging.debug(f"short sleep {t}")
            await asyncio.sleep(t)


def fetch_loop():
    while True:
        start = time.time()
        if len(chats) != 0:
            asyncio.run(fetch_all())
        t = FETCH_INTERVAL
        t -= time.time() - start
        if t <= 0:
            logging.warning(f"sleep time {t} less than 0, skip")
        else:
            logging.debug(f"long sleep {t}")
            if event.wait(t):
                # `wait` return true if event is set
                return


if __name__ == '__main__':
    event = threading.Event()

    chats = set()
    tokens = set()
    fetch_record = dict()
    live_record = dict()

    fetcher = Bilibili()
    now = int(time.time())
    for uid in UID_LIST:
        fetch_record[uid] = now
        live_record[uid] = LiveStatus.PREPARE

    db = Database("data.json")
    for s in db.subscriber():
        chats.add(s)
    for uid in db.live():
        live_record[uid] = LiveStatus.LIVE

    updater = Updater(TOKEN, use_context=True)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler("start", cmd_start, filters=Filters.private))
    dispatcher.add_handler(CommandHandler("register", cmd_register))
    dispatcher.add_handler(CommandHandler("unregister", cmd_unregister))
    dispatcher.add_handler(CommandHandler("token", cmd_token, filters=Filters.private))
    t = threading.Thread(target=fetch_loop)

    logging.basicConfig(format='%(asctime)s %(message)s', level=LOG_LEVEL, filename=LOG_FILE)
    logging.info("start fetch loop")
    t.start()
    logging.info("start polling telegram messages")
    updater.start_polling()
    logging.info("bot is now running")

    from signal import SIGABRT, SIGINT, SIGTERM, signal


    def stop():
        logging.info("bot exiting")
        updater.stop()
        event.set()


    for sig in (SIGINT, SIGTERM, SIGABRT):
        signal(sig, lambda signum, frame: stop())

    logging.info("join async thread")
    try:
        t.join()
    except Exception as e:
        logging.warning(f"async thread exit with err: {e}")
        stop()
        # exit with non-zero code can tell systemd to restart this
        exit(1)
    logging.info("bot exited")
