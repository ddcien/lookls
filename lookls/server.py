from pygls.lsp.server import LanguageServer
from pygls.cli import start_server
from lsprotocol import types
import asyncio
import re
import os
from .ici import ICIFetcher


RE_END_HEAD = re.compile(r"[a-zA-Z]{3,}$")
RE_END_WORD = re.compile("^[A-Za-z]*")
RE_START_WORD = re.compile("[A-Za-z]*$")


class LookLS(LanguageServer):
    @staticmethod
    def __word_at_position(
        line: str,
        server_col: int,
        re_start_word: re.Pattern[str] = RE_START_WORD,
        re_end_word: re.Pattern[str] = RE_END_WORD,
    ):
        start = line[:server_col]
        end = line[server_col:]
        m_start = re_start_word.search(start)
        m_end = re_end_word.search(end)
        assert m_start
        assert m_end
        return m_start.group() + m_end.group(), m_start.span()[0]

    @staticmethod
    async def __look(prefix: str):
        file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "10k.txt")

        if os.path.exists(file) and os.path.isfile(file):
            args = ("-bdf", prefix, file)
        else:
            args = (prefix,)

        return (
            (
                await (
                    await asyncio.create_subprocess_exec(
                        "look",
                        *args,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.DEVNULL,
                        stdin=asyncio.subprocess.DEVNULL,
                    )
                ).communicate()
            )[0]
            .decode()
            .splitlines()
        )

    def __init__(self, ici: ICIFetcher, *args, **kwargs) -> None:
        super().__init__(name="LookLS", version="0.1.0", *args, **kwargs)
        self.__ici = ici

        @self.feature(types.TEXT_DOCUMENT_HOVER)
        async def hover(params: types.HoverParams):
            client_position = params.position
            document_uri = params.text_document.uri
            document = self.workspace.get_text_document(document_uri)

            if client_position.line >= len(document.lines):
                return

            server_position = document.position_codec.position_from_client_units(
                document.lines, client_position
            )
            word, start_col = self.__word_at_position(
                document.lines[server_position.line],
                server_position.character,
                re_start_word=RE_START_WORD,
                re_end_word=RE_END_WORD,
            )
            if not word:
                return

            hover_content = await self.__ici.translate(word)
            if not hover_content:
                return

            return types.Hover(
                contents=types.MarkupContent(
                    kind=types.MarkupKind.Markdown,
                    value=hover_content,
                ),
                range=document.position_codec.range_to_client_units(
                    document.lines,
                    types.Range(
                        start=types.Position(
                            line=server_position.line, character=start_col
                        ),
                        end=types.Position(
                            line=server_position.line, character=start_col + len(word)
                        ),
                    ),
                ),
            )

        @self.feature(
            types.TEXT_DOCUMENT_COMPLETION,
            types.CompletionOptions(
                resolve_provider=True,
            ),
        )
        async def completions(params: types.CompletionParams):
            document = self.workspace.get_text_document(params.text_document.uri)
            client_position = params.position

            if client_position.line >= len(document.lines):
                return

            server_position = document.position_codec.position_from_client_units(
                document.lines, client_position
            )

            head = document.lines[server_position.line][: server_position.character]
            if not head:
                return

            match = RE_END_HEAD.search(head)
            if not match:
                return

            return types.CompletionList(
                is_incomplete=False,
                item_defaults=types.CompletionItemDefaults(
                    insert_text_format=types.InsertTextFormat.PlainText,
                    edit_range=types.Range(
                        start=types.Position(
                            line=server_position.line, character=match.span()[0]
                        ),
                        end=types.Position(
                            line=server_position.line, character=len(head)
                        ),
                    ),
                ),
                items=[
                    types.CompletionItem(
                        label=i,
                        kind=types.CompletionItemKind.Text,
                    )
                    for i in await self.__look(match.group())
                ],
            )

        @self.feature(types.COMPLETION_ITEM_RESOLVE)
        async def completion_item_resolve(item: types.CompletionItem):
            hover_content = await self.__ici.translate(item.label)
            if not hover_content:
                item.documentation = None
            else:
                item.documentation = types.MarkupContent(
                    kind=types.MarkupKind.Markdown,
                    value=hover_content,
                )
            return item


def main():
    _ici = ICIFetcher(ici_key="E0F0D336AF47D3797C68372A869BDBC5")
    server = LookLS(ici=_ici)
    start_server(server)


if __name__ == "__main__":
    main()
