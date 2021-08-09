import aiohttp
import random
import re
import time
import datetime

from io import StringIO, BytesIO
from typing import List, Tuple, Union

import discord
from discord.ext import commands


def extract_mentions(text: str, message: discord.Message) -> str:
    """Extract mentions in text and replace them with usernames"""

    # Extract mentions from the input
    mentions_found = re.findall(r'(<@!?&?\d{17,18}>)', text)

    # Extract mentions from the input, but get the IDs.
    ids_found = re.findall(r'(\d{17,18})', text)

    if mentions_found:
        for num, mention in enumerate(mentions_found):
            member_mentioned = discord.utils.get(
                message.guild.members, id=ids_found[num]
            )
            if member_mentioned is not None:
                # Assigning it to the str.replace was crucial here
                text = text.replace(mention, member_mentioned.name)
            else:
                text = text.replace(mention, "[somebody]")

    return text


def check_ids(text: str) -> bool:
    """Check for IDs"""
    id_found = re.search(r'(\d{17,18})', text)
    if id_found and id_found.group(0) is not None:
        return True
    else:
        return False


def check_mentions(text: str) -> Union[bool, str]:  # TODO: Update docstr for typing
    """
    Check message for mentions
    :param text: Input
    :return: True if mention found, otherwise False
    """
    mention_found = re.search(r'(<@!?&?\d{17,18}>)', text)
    if mention_found is not None and mention_found.group(0) is not None:
        return mention_found.group(0)
    else:
        return False


def check_urls(text: str) -> Union[bool, str]:  # TODO: Update docstr for typing
    """
    Check message for urls
    :param text: Input
    :return: True if link found, otherwise False
    """
    link_found = re.search(
        r'(https?://(www\.)?[-a-zA-Z0-9@:%._+~#=]{2,256}\.[a-z]{2,6}\b([-a-zA-Z0-9@:%_+.~#?&/=]*))', text)
    if link_found is not None and link_found.group(0) is not None:
        return link_found.group(0)
    else:
        return False


def check_input(text: str) -> Union[bool, str]:  # TODO: Update docstr for typing
    """
    Check text for certain components which we don't really want to end up in messages, such as mentions or urls.
    Does not do any actual parsing.
    :param text: String to check.
    :return: True if mention or link is found, otherwise false.
    """

    return check_mentions(text) or check_urls(text)


def get_timestamp() -> str:
    now = time.localtime()
    return time.strftime("%a %b %d, %Y at %H:%M %Z", now)


def format_list(items: List[str]) -> str:  # TODO: ", ".join([items])
    """Dealing with lists and commas."""
    output = ""
    for num, item in enumerate(items):
        output += item
        output += ", " if (num + 1 != len(items)) else ""

    return output


async def download_image(url: str, file_path: Union[bytes, str, BytesIO]):
    # TODO Add an argument for maximum file size
    is_bytes = False
    if isinstance(file_path, str):
        fd = open(file_path, "wb")
    else:
        is_bytes = True
        fd = file_path

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                while True:
                    chunk = await resp.content.read(10)
                    if not chunk:
                        break
                    fd.write(chunk)

        fd.seek(0)

    finally:
        if not is_bytes:
            fd.close()


class FancyTimeStamp:
    """
    Fancy timestamp display class that formats a normal timestamp into a fancy discord one.
    see: https://github.com/discord/discord-api-docs/pull/3135/files
    """

    @staticmethod
    def _as_epoch(ts):
        try:
            dt = datetime.datetime.fromtimestamp(int(ts))
        except TypeError:
            dt = ts
        return int(dt.timestamp())

    @staticmethod
    def _format(flag: str, ts: Union[datetime.datetime, int]):
        return "<t:{}:{}>".format(FancyTimeStamp._as_epoch(ts), flag)

    @staticmethod
    def full_timestamp_weekday(ts) -> str:
        """
        Sunday, 4 July 2021 20:00
        """
        return FancyTimeStamp._format("F", ts)

    @staticmethod
    def date_time(ts) -> str:
        """
        4 July 2021 20:00
        """
        return FancyTimeStamp._format("f", ts)

    @staticmethod
    def time_no_secs(ts):
        """
        20:00
        """
        return FancyTimeStamp._format("t", ts)

    @staticmethod
    def dd_mm_yyyy(ts) -> str:
        """
        07/04/2021
        """
        return FancyTimeStamp._format("d", ts)

    @staticmethod
    def relative(ts) -> str:
        """
        In an hour
        """
        return FancyTimeStamp._format("R", ts)


def embed_from_dict(obj: dict, **embed_args) -> discord.Embed:
    embed = discord.Embed(**embed_args)
    if obj is not None:
        for k, v in obj.items():
            # trim keys and values so we're less likely to make our embeds too long.
            key_trimmed = str(k) if len(str(k)) < 256 else "{}...".format(k[:253])
            value_trimmed = str(v) if len(str(v)) < 256 else "{}...".format(v[:253])
            embed.add_field(name=key_trimmed, value=value_trimmed)
    return embed


class UserType:

    def __init__(self, argument: Union[discord.Member, str, int]) -> None:

        if isinstance(argument, discord.Member):
            self.user_id = argument.id
        elif check_ids(argument):
            self.user_id = argument
        else:
            raise commands.BadArgument("User not found.")


class Paginator:

    def __init__(
            self, page_limit: int = 1000, trunc_limit: int = 2000,
            headers=None, header_extender: str = u'\u200b'
    ) -> None:
        self.page_limit = page_limit
        self.trunc_limit = trunc_limit
        self._pages = None
        self._headers = None
        self._header_extender = header_extender
        self.set_headers(headers)

    @property
    def pages(self) -> Union[List[str], List[Tuple[str, str]]]:
        if self._headers:
            self._extend_headers(len(self._pages))
            headers, self._headers = self._headers, None
            return [(headers[i], self._pages[i]) for i in range(len(self._pages))]
        else:
            return self.pages

    def set_headers(self, headers: str = None):
        self._headers = headers

    def set_header_extender(self, header_extender: str = u'\u200b') -> None:
        self._header_extender = header_extender

    def _extend_headers(self, length: int) -> None:
        while len(self._headers) < length:
            self._headers.append(u'\u200b')

    def set_trunc_limit(self, limit: int = 2000) -> None:
        self.trunc_limit = limit

    def set_page_limit(self, limit: int = 1000) -> None:
        self.page_limit = limit

    def paginate(self, value: str) -> Union[List[str], List[Tuple[str, str]]]:
        """
        To paginate a string into a list of strings under
        `self.page_limit` characters. Total len of strings
        will not exceed `self.trunc_limit`.
        :param value: string to paginate
        :return list: list of strings under 'page_limit' chars
        """
        spl = str(value).split('\n')
        ret = []
        page = ''
        total = 0
        for i in spl:
            if total + len(page) < self.trunc_limit:
                if (len(page) + len(i)) < self.page_limit:
                    page += '\n{}'.format(i)
                else:
                    if page:
                        total += len(page)
                        ret.append(page)
                    if len(i) > (self.page_limit - 1):
                        tmp = i
                        while len(tmp) > (self.page_limit - 1):
                            if total + len(tmp) < self.trunc_limit:
                                total += len(tmp[:self.page_limit])
                                ret.append(tmp[:self.page_limit])
                                tmp = tmp[self.page_limit:]
                            else:
                                ret.append(tmp[:self.trunc_limit - total])
                                break
                        else:
                            page = tmp
                    else:
                        page = i
            else:
                ret.append(page[:self.trunc_limit - total])
                break
        else:
            ret.append(page)
        self._pages = ret
        return self.pages


def create_quick_embed(name: str, value: str, **embed_kwargs) -> discord.Embed:
    embed = discord.Embed(**embed_kwargs)
    embed.add_field(name=name, value=value)
    return embed


async def get_text_from_pastebin(url: str) -> StringIO:
    """Get raw text from a pastebin url"""
    url_id = re.findall("https?://pastebin\.com/(\w{8})", url)[0]  # The error will happen, let's allow it
    fd = StringIO()

    async with aiohttp.ClientSession() as session:
        async with session.get("https://pastebin.com/raw/{}".format(url_id)) as resp:
            fd.write(await resp.text())

    fd.seek(0)
    return fd


async def get_text_from_upload(attachment_url: str) -> StringIO:
    """Get raw text from a pastebin url"""
    fd = StringIO()

    async with aiohttp.ClientSession() as session:
        async with session.get(attachment_url) as resp:
            fd.write(await resp.text())

    fd.seek(0)
    return fd


def generate_furry_text(string: str) -> str:
    """
    Generate some fuwwy speech uwu
    """

    string = re.sub("[rl]", "w", string, re.IGNORECASE)
    string = re.sub("th", "ff", string, re.IGNORECASE)
    string = re.sub("v", "b", string, re.IGNORECASE)
    string = re.sub(" the ", " da ", string, re.IGNORECASE)


def generate_fhyr_text(string: str) -> str:
    """
    Translate a string of text into fhyr lucario
    """
    heart = "\N{BLUE HEART}"
    notes = "\N{MULTIPLE MUSICAL NOTES}"
    sparkles = "\N{SPARKLES}"
    star = "\N{GLOWING STAR}"

    emoji = [heart, notes, sparkles, star]

    arms = [("/", "/"), ("9", "9"), ("/", "\\\\")]
    mouths = ["o", "w", "n", "^", "\~", "ω"]
    eyes = [(";", ";"), ("^", "^"), ("x", "x"), ("o", "o"), ("n", "n"), ("'", "'"), ("u", "u"),
            (">", "<"), ("è", "é"), ("ò", "ó")]

    translations = {
        "thicc": "t h i c c",
        "barcc": "b a r c c",
        "bark": "b a r c c",
        "thick": "t h i c c",
        "-": "'",
        "song": "howlie",
        "sing": "howl"
    }

    # suffix changes
    string = re.sub("ly(\W)", "lie\g<1>", string, re.IGNORECASE)
    string = re.sub("s(\W)", "z\g<1>", string, re.IGNORECASE)

    # Word subs
    string = re.sub("(\W)me(\W)", "\g<1>luu\g<2>", string, re.IGNORECASE)

    # Specific early subs
    string = string.replace("I'm", "luu's")
    string = string.replace("I've", "luu's")
    string = re.sub("(\W)I(\W)", "\g<1>luu\g<2>", string)

    string = re.sub("(\W)my(\W)", "\g<1>luu's\g<2>", string, re.IGNORECASE)

    string = re.sub("(\W)(?:okay|ok)(\W)",
                    "\g<1>okie{}".format("s" if random.random() > 0.5 else ""),
                    string,
                    re.IGNORECASE)

    for orig, translation in translations.items():
        string = string.replace(orig, translation)

    # TODO: Find better way to iterate than re

    # adding tildae and emoji strings

    for match in re.finditer("(\w)[.!?\n](\B)", string):
        # determine the string that will follow
        following_str = "{}\\~ {}{}".format(match.group(1),
                                           random.choice(emoji),
                                           match.group(2))
        # This grabs a chunk of the string before it along with the replace,
        # meaning that should effectively work even when matching multiple times
        string = string.replace(match.group(0), following_str, 1)

    # Add a random 'luu~
    for match in re.finditer("\w(\b)", string):
        if random.random() > 0.75:  # is 5% too high?
            string = string.replace(match.group(0), "'l{}{}{}".format("u" * random.randint(1, 10),
                                                                      "\\~" * random.randint(1, 4),
                                                                      match.group(1)), 1)

    for i in range(len(string)):
        cur_string = string[i:]

        # Things that come between words
        match = re.match("\w(\s)", cur_string)
        rand = random.random()
        if match:
            if 0.85 > rand > 0.75:
                updated_string = re.sub(match.group(1), "'", cur_string, count=1)

            elif 0.90 > rand > 0.85:
                updated_string = re.sub(match.group(1), "'l{}{}{}".format("u" * random.randint(1, 10),
                                                                          "\\~" * random.randint(1, 4),
                                                                          match.group(1)), cur_string, count=1)

            elif rand > 0.90:
                extra_phrases = ["barklies", "barkies", "awoo", "gosh", "omaigosh"]
                updated_string = re.sub(match.group(1), "'{}{}".format(random.choice(extra_phrases),
                                                                       match.group(1)), cur_string, count=1)

            else:
                continue

            string = string.replace(cur_string, updated_string)  # huh

    mini_luc = "({0}) {1}{2}{3}{4}{5}){6}) \\~"  # yuck
    mini_luc += "".join([random.choice(emoji) for _ in range(random.randint(4, 15))])

    blushes = random.randint(1, 2)

    chosen_arms = random.choice(arms)
    chosen_eyes = random.choice(eyes)

    mini_luc = mini_luc.format(chosen_arms[0],
                               chosen_eyes[0],
                               "/" * (blushes + 1),
                               random.choice(mouths),
                               "/" * blushes,
                               chosen_eyes[1],
                               chosen_arms[1])

    string += "\n" + mini_luc

    return string


def owo(input_str: str) -> str:
    """
    owoify a stwing. fuww cwedit to https://github.com/zuzak/owo/ fow the idea.
    """

    output = input_str
    prefixes = [
        '<3 ',
        'H-hewwo?? ',
        'HIIII! ',
        'Haiiii! ',
        'Huohhhh. ',
        'OWO ',
        'OwO ',
        'UwU '
    ]

    suffixes = [
        ' :3',
        ' UwU',
        ' ʕʘ‿ʘʔ',
        ' >_>',
        ' ^_^',
        '..',
        ' Huoh.',
        ' ^-^',
        ' ;_;',
        ' ;-;',
        ' xD',
        ' x3',
        ' :D',
        ' :P',
        ' ;3',
        ' XDDD',
        ', fwendo',
        ' ㅇㅅㅇ',
        ' (人◕ω◕)',
        '（＾ｖ＾）',
        ' Sigh.',
        ' ._.',
        ' (• o •)',
        ' >_<'
    ]

    substitutions = {
        'r': 'w',
        'l': 'w',
        'R': 'W',
        'L': 'W',
        'no': 'nu',
        'has': 'haz',
        'have': 'haz',
        'you': 'uu',
        'the ': 'da ',
        'The ': 'Da '
    }

    for old, sub in substitutions.items():
        output = output.replace(old, sub)

    return random.choice(prefixes) + output + random.choice(suffixes)
