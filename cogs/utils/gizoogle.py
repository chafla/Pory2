"""
Retrieve a gizoogled string. Mostly adapted from a library written in ruby.
Requires lxml.
"""


import aiohttp
import re
import bs4
import urllib.parse


class String:

    @staticmethod
    async def translate(text):
        params = {"translatetext": text}
        url = "http://www.gizoogle.net/textilizer.php"
        with aiohttp.ClientSession() as session:
            with aiohttp.Timeout(10):
                async with session.post(url,
                                        data=params) as resp:
                    # the html returned normally is in poor form
                    soup_input = re.sub(r"/name=translatetext[^>]*>/",
                                        r'name="translatetext" >', await resp.text())
                    soup = bs4.BeautifulSoup(soup_input, "lxml")
                    giz = (soup.find_all(text=True))
                    giz_text = giz[39].strip("\r\n")  # Hacky, but consistent.
                    return giz_text


class Website:

    @staticmethod
    async def translate(dest_url):
        text = dest_url
        params = {"search": text}
        new_url = urllib.parse.urlencode(params)
        url = "http://www.gizoogle.net/tranzizzle.php?{0}".format(new_url)
        return url
