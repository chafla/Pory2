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
    async def translate(text: str) -> str:
        params = {"translatetext": text,
                  "translate": "Tranzizzle Dis Shiznit"}

        url = "http://www.gizoogle.net/textilizer.php"
        async with aiohttp.ClientSession() as session:
            with aiohttp.Timeout(10):
                async with session.post(url,
                                        data=params) as resp:
                    # the html returned normally is in poor form
                    soup_input = re.sub(r"/name=translatetext[^>]*>/",
                                        r'name="translatetext" >', await resp.text())
                    soup = bs4.BeautifulSoup(soup_input, "lxml")
                    giz = (soup.find_all(text=True))
                    giz_text = giz[37].strip("\r\n")  # Hacky, but consistent.
                    return giz_text


class Website:

    @staticmethod
    async def translate(dest_url: str) -> str:
        text = dest_url
        params = {"search": text}
        new_url = urllib.parse.urlencode(params)
        url = "http://www.gizoogle.net/tranzizzle.php?{0}".format(new_url)
        return url
