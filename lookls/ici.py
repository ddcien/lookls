import asyncio
import plyvel
import os
import appdirs
import aiohttp
from typing import Any
import orjson as json


class ICIFetcher:
    _URL: str = "http://dict-co.iciba.com/api/dictionary.php"

    def __init__(
        self,
        ici_key: str,
        cache_lldb: str | None = None,
    ):
        self.__key = ici_key
        self.__cache_lldb = cache_lldb or os.path.join(
            appdirs.user_config_dir("ici"), "ici.db"
        )

    async def __lldb_get(self, key: bytes) -> bytes:
        with plyvel.DB(self.__cache_lldb, create_if_missing=True) as db:
            return db.get(key)

    async def __lldb_put(self, key: bytes, value: bytes) -> None:
        with plyvel.DB(self.__cache_lldb, create_if_missing=True) as db:
            db.put(key, value, sync=True)

    async def __ici_get(self, word: str) -> bytes:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url=ICIFetcher._URL,
                params={"type": "json", "key": self.__key, "w": word},
            ) as res:
                return await res.read()

    async def translate(self, word: str) -> str | None:
        word = word.lower()
        data: bytes = await self.__lldb_get(word.encode())
        if data:
            return "\n".join(self.parse(json.loads(data)))

        data = await self.__ici_get(word)
        content = json.loads(data)
        word_name: str = content.get("word_name")
        if not word_name:
            return None
        await self.__lldb_put(word_name.encode(), data)
        return "\n".join(self.parse(content))

    @staticmethod
    def parse_symbols_part(p) -> str:
        return "`{}`: {}".format(p["part"], "; ".join(p["means"]))

    @staticmethod
    def parse_symbol(s) -> list[str]:
        lines = []
        lines.append(
            "US: {}; UK: {}".format(s["ph_am"], s["ph_en"]),
        )
        for p in s["parts"]:
            lines.append(ICIFetcher.parse_symbols_part(p))

        return lines

    @staticmethod
    def parse_exchange(e) -> str:
        x = {
            "word_pl": "Plural Form",
            "word_past": "Past Tense",
            "word_done": "Past Participle",
            "word_ing": "Present Participle",
            "word_third": "Simple Present",
            "word_er": "Comparative Degree",
            "word_est": "Superlative",
        }
        return ";".join("{}: {}".format(x[k], ",".join(v)) for k, v in e.items() if v)

    @staticmethod
    def parse(data: dict[str, Any]) -> list[str]:
        try:
            lines = ["### {}".format(data.get("word_name"))]
        except Exception:
            return [""]

        # lines.append(ICIFetcher.parse_exchange(data["exchange"]))
        # for s in data["symbols"]:
        #     lines += ICIFetcher.parse_symbol(s)
        # return lines

        for symbol in data.get("symbols", []):
            lines.append("")
            ph = "-"
            if symbol.get("ph_am"):
                ph += " US:\\[{}\\]".format(symbol.get("ph_am"))

            if symbol.get("ph_en"):
                ph += " UK:\\[{}\\]".format(symbol.get("ph_en"))

            if len(ph) > 1:
                lines.append(ph)

            for part in symbol["parts"]:
                lines.append("\t- " + ICIFetcher.parse_symbols_part(part))

        extbl = {
            "word_pl": "复数",
            "word_ing": "现在分词",
            "word_done": "过去分词",
            "word_past": "过去式",
            "word_third": "第三人称单数",
            "word_er": "比较级",
            "word_est": "最高级",
        }
        exchange_lines = []
        for k, v in data.get("exchange", {}).items():
            if v:
                exchange_lines.append("\t- {}: {}".format(extbl[k], "; ".join(v)))

        if exchange_lines:
            lines.append("")
            lines.append("- 词态变化:")
            lines += exchange_lines

        for sent in data.get("sent", []):
            lines.append("> {}".format(sent["orig"]))
            lines.append("> {}".format(sent["trans"]))
            lines.append("")

        return lines
