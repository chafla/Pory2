import re
import discord
import time
import aiohttp
from io import StringIO
from discord.ext import commands
import random

# from discord.ext.commands import HelpFormatter

# TODO Re-create the help formatter
"""
class Formatter(HelpFormatter):

    def __init__(self, *args, **kwargs):
        super(*args, **kwargs)
     super(*args, **kwargs)
     
"""


def extract_mentions(text, message):
    """Extract mentions in text and replace them with usernames"""
    mentions_found = re.findall(r'(<@!?&?\d{17,18}>)', text)  # Extract mentions from the input
    ids_found = re.findall(r'(\d{17,18})', text)  # Extract mentions from the input, but get the IDs.
    if mentions_found:
        for num, mention in enumerate(mentions_found):
            member_mentioned = discord.utils.get(message.guild.members, id=ids_found[num])
            if member_mentioned is not None:
                text = text.replace(mention, member_mentioned.name)  # Assigning it to the str.replace was crucial here
            else:
                text = text.replace(mention, "[somebody]")
    return text


def check_ids(text):
    """Check for IDs"""
    id_found = re.search(r'(\d{17,18})', text)
    if id_found and id_found.group(0) is not None:
        return True
    else:
        return False


def check_mentions(text):
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


def check_urls(text):
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


def check_input(text):
    """
    Check text for certain components which we don't really want to end up in messages, such as mentions or urls.
    Does not do any actual parsing.
    :param text: String to check.
    :return: True if mention or link is found, otherwise false.
    """

    return check_mentions(text) or check_urls(text)


def get_timestamp():
    now = time.localtime()
    return time.strftime("%a %b %d, %Y at %H:%M %Z", now)


def format_list(items):
    """Dealing with lists and commas."""
    output = ""
    for num, item in enumerate(items):
        output += item
        output += ", " if (num + 1 != len(items)) else ""

    return output


async def download_image(url, file_path):
    is_bytes = False
    if isinstance(file_path, str):
        fd = open(file_path, "wb")
    else:
        is_bytes = True
        fd = file_path

    try:
        with aiohttp.ClientSession() as session:
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


class UserType:

    def __init__(self, argument):

        if isinstance(argument, discord.Member):
            self.user_id = argument.id
        elif check_ids(argument):
            self.user_id = argument
        else:
            raise commands.BadArgument("User not found.")


class Paginator:

    def __init__(self, page_limit=1000, trunc_limit=2000, headers=None, header_extender=u'\u200b'):
        self.page_limit = page_limit
        self.trunc_limit = trunc_limit
        self._pages = None
        self._header_extender = header_extender
        self.set_headers(headers)

    @property
    def pages(self):
        if self._headers:
            self._extend_headers(len(self._pages))
            headers, self._headers = self._headers, None
            return [(headers[i], self._pages[i]) for i in range(len(self._pages))]
        else:
            return self.pages

    def set_headers(self, headers=None):
        self._headers = headers

    def set_header_extender(self, header_extender: str=u'\u200b'):
        self._header_extender = header_extender

    def _extend_headers(self, length: int):
        while len(self._headers) < length:
            self._headers.append(u'\u200b')

    def set_trunc_limit(self, limit: int=2000):
        self.trunc_limit = limit

    def set_page_limit(self, limit: int=1000):
        self.page_limit = limit

    def paginate(self, value):
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


def create_quick_embed(name, value, **embed_kwargs):
    embed = discord.Embed(**embed_kwargs)
    embed.add_field(name=name, value=value)
    return embed


async def get_text_from_pastebin(url):
    """Get raw text from a pastebin url"""
    url_id = re.findall("https?://pastebin\.com/(\w{8})", url)[0]  # The error will happen, let's allow it
    fd = StringIO()

    with aiohttp.ClientSession() as session:
        async with session.get("https://pastebin.com/raw/{}".format(url_id)) as resp:
            fd.write(await resp.text())

    fd.seek(0)
    return fd


async def get_text_from_upload(attachment_url):
    """Get raw text from a pastebin url"""
    fd = StringIO()

    with aiohttp.ClientSession() as session:
        async with session.get(attachment_url) as resp:
            fd.write(await resp.text())

    fd.seek(0)
    return fd


def generate_fhyr_text(string):
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
        following_str = "{}\~ {}{}".format(match.group(1),
                                           random.choice(emoji),
                                           match.group(2))
        # This grabs a chunk of the string before it along with the replace,
        # meaning that should effectively work even when matching multiple times
        string = string.replace(match.group(0), following_str, 1)

    # Add a random 'luu~
    for match in re.finditer("\w(\b)", string):
        if random.random() > 0.75:  # is 5% too high?
            string = string.replace(match.group(0), "'l{}{}{}".format("u" * random.randint(1, 10),
                                                                      "\~" * random.randint(1, 4),
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
                                                                          "\~" * random.randint(1, 4),
                                                                          match.group(1)), cur_string, count=1)

            elif rand > 0.90:
                extra_phrases = ["barklies", "barkies", "awoo", "gosh", "omaigosh"]
                updated_string = re.sub(match.group(1), "'{}{}".format(random.choice(extra_phrases),
                                                                       match.group(1)), cur_string, count=1)

            else:
                continue

            string = string.replace(cur_string, updated_string)  # huh

    mini_luc = "({0}) {1}{2}{3}{4}{5}){6}) \~"  # yuck
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
