import datetime
import json
import logging

from typing import List, Optional

from urllib.request import build_opener, HTTPCookieProcessor, Request

from utils import async_wrap
from .model import Dynamic, DynamicType


def parse_card(c) -> Optional[Dynamic]:
    try:
        card = json.loads(c["card"])
    except json.JSONDecodeError:
        logging.error(f"Malformed Bilibili dynamic card: {c}")
        return None

    dt = DynamicType.from_int(c["desc"]["type"])
    did = c["desc"]["dynamic_id"]

    if dt == DynamicType.FORWARD:
        dyn = card["item"]
        user = card["user"]["uname"]

        origin_card = {
            "desc": {
                "type": dyn["orig_type"],
                "dynamic_id": dyn["orig_dy_id"]
            },
            "card": card["origin"]
        }
        origin = parse_card(origin_card)
        if origin is None:
            return None

        text = f'{dyn["content"]}\n------\nRT\n{origin.text}'
        link = f"https://t.bilibili.com/{did}"
        img = origin.photos
        t = dyn["timestamp"]
    elif dt == DynamicType.PHOTO:
        dyn = card["item"]
        user = card["user"]["name"]

        text = dyn["description"]
        link = f"https://t.bilibili.com/{did}"
        img = [entry["img_src"] for entry in dyn["pictures"]]
        t = dyn["upload_time"]
    elif dt == DynamicType.PLAIN:
        dyn = card["item"]
        user = card["user"]["uname"]

        text = dyn["content"]
        link = f"https://t.bilibili.com/{did}"
        img = []
        t = dyn["timestamp"]
    elif dt == DynamicType.VIDEO:
        text = card["title"]
        user = card["owner"]["name"]
        link = f'https://www.bilibili.com/video/av{card["aid"]}'
        img = [card["pic"]]
        t = card["ctime"]
    else:
        return None

    return Dynamic(user, dt, text, img, link, t)


class Bilibili:
    def __init__(self):
        self.disabled_until: Optional[datetime.datetime] = None

    async def request(self, url: str, payload: dict):
        @async_wrap
        def open_req(r):
            if not hasattr(open_req, "_opener"):
                open_req._opener = build_opener(HTTPCookieProcessor())
                open_req._opener.addheaders.clear()
                open_req._opener.addheaders.append(("User-Agent",
                                                    "Dalvik/2.1.0 (Linux; U; Android 7.1.2; Test Build/Test)"))
            opener = open_req._opener
            return opener.open(r)

        data = json.dumps(payload).encode()
        req = Request(url, data=data, headers={"Content-Type": "application/json"})
        return await open_req(req)

    async def fetch(self, user_id: int, timestamp: int = 0) -> List[Dynamic]:
        print(f"fetch {user_id}")
        if self.disabled_until:
            if self.disabled_until < datetime.datetime.now():
                logging.info("Bilibili crawler resumed.")
                self.disabled_until = None
            else:
                return []

        url = "https://api.vc.bilibili.com/dynamic_svr/v1/dynamic_svr/space_history"
        payload = {
            "visitor_uid": 0,
            "host_uid": user_id,
            "offset_dynamic_id": 0,
            "need_top": 0
        }
        resp = await self.request(url, payload)
        code = resp.getcode()
        if code == -412:
            logging.error("Bilibili API Throttled. Crawler paused.")
            self.disabled_until = datetime.datetime.now() + datetime.timedelta(minutes=30)
            return []
        resp = resp.read().decode()
        resp = json.loads(resp)
        cards = resp["data"]["cards"]

        dyn_list = []

        counter = 0

        for c in cards:
            dyn = parse_card(c)
            if dyn is None:
                continue
            if dyn.timestamp <= timestamp:
                break
            dyn_list.append(dyn)
            counter += 1
            if counter == 6:
                print(f"total {len(cards)}, but only return 6")
                break
        return dyn_list
