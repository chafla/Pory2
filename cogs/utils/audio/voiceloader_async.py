import random
import re

from .tts_utils import VoiceLoader
import aiohttp
import asyncio
import requests


class VoiceLoaderAsync(VoiceLoader):

    @staticmethod
    async def parse(text: str, voice_id: str) -> str:
        email_len = random.randint(10, 20)
        email = ""
        for i in range(email_len):
            email += str(chr(random.randint(1, 26) + 64))

        email += "@gmail.com"

        content = {
            "json": {
                "googleid": email
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post("https://acapelavoices.acapela-group.com/index/getnonce", data=content) as resp:

                if not resp.status == 200:
                    resp.raise_for_status()

                # match = re.match(r'"^\{\""nonce\""\:\""(.+)\""\}$"', resp.text)
                nonce = (await resp.json())["nonce"]

        req_url = "http://www.acapela-group.com:8080/webservices/1-34-01-Mobility/Synthesizer"

        enc = "req_voice={}&cl_pwd=&cl_vers=1-30&req_echo=ON&cl_login=AcapelaGroup&req_comment=%7B%22nonce%22%3A%22{}%22%2C%22user%22%3A%22{}%22%7D&req_text={}&cl_env=ACAPELA_VOICES&prot_vers=2&cl_app=AcapelaGroup_WebDemo_Android".format(
            voice_id,
            nonce,
            email,
            requests.utils.quote(text)
        )

        payload = enc.encode("ascii")

        content_type = "application/x-www-form-urlencoded"

        headers = {
            "Content-Type": content_type
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(req_url, data=payload, headers=headers) as resp:

                resp_content = await resp.text(encoding="utf-8")

                regs = re.search("snd_url=(.+)&snd_size", resp_content)

        if regs:
            return regs.group(1)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    voice_loader = VoiceLoaderAsync()
    res = loop.run_until_complete(voice_loader.process_text("Hello world", "WillFromAfar"))
    print(res)