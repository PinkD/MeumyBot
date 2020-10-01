import json


class Database:
    def __init__(self, file: str):
        self.__file = file
        self.__data = {}
        self.__load_data()

    def __load_data(self):
        try:
            with open(self.__file) as f:
                data = f.read()
                try:
                    self.__data = json.loads(data)
                    # json saves key with str, we need to convert to int
                    d = {}
                    m = self.__data["subscriber"]
                    for k in m:
                        d[int(k)] = m[k]
                    self.__data["subscriber"] = d
                    return
                except json.JSONDecodeError:
                    print(f"failed to load {self.__file}, content is {data}")
        except FileNotFoundError:
            print("no old data file")
        self.__data["subscriber"] = {}

    def __save_data(self):
        with open(self.__file, "w") as f:
            f.write(json.dumps(self.__data))

    def add_subscribe(self, chat_id: int):
        self.__data["subscriber"][chat_id] = True
        self.__save_data()

    def del_subscribe(self, chat_id: int):
        del self.__data["subscriber"][chat_id]
        self.__save_data()

    def subscriber(self) -> list:
        return self.__data["subscriber"].keys()
