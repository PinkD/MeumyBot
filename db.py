import json
import logging


class Database:
    def __init__(self, file: str):
        self.__file = file
        self.__data = {}
        self.__load_data()

    def __convert_to_int(self):
        # json saves key with str, we need to convert to int
        d = {}
        for k in self.__data:
            d[k] = {}
            m = self.__data[k]
            for uid in m:
                d[k][int(uid)] = m[uid]
        self.__data = d

    def __load_data(self):
        try:
            with open(self.__file) as f:
                data = f.read()
                try:
                    self.__data = json.loads(data)
                    self.__convert_to_int()
                except json.JSONDecodeError:
                    logging.warning(f"failed to load {self.__file}, content is {data}")
        except FileNotFoundError:
            logging.info("no old data file")
        keys = ["subscriber", "live"]
        for k in keys:
            if k not in self.__data:
                self.__data[k] = {}

    def __save_data(self):
        with open(self.__file, "w") as f:
            f.write(json.dumps(self.__data))

    def add_subscribe(self, chat_id: int):
        self.__data["subscriber"][chat_id] = True
        self.__save_data()

    def del_subscribe(self, chat_id: int):
        if chat_id in self.__data["subscriber"]:
            del self.__data["subscriber"][chat_id]
        self.__save_data()

    def subscriber(self) -> list:
        return self.__data["subscriber"].keys()

    def add_live(self, chat_id: int):
        self.__data["live"][chat_id] = True
        self.__save_data()

    def del_live(self, chat_id: int):
        if chat_id in self.__data["live"]:
            del self.__data["live"][chat_id]
        self.__save_data()

    def live(self) -> list:
        return self.__data["live"].keys()

