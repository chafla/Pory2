import random
import requests
import re
from .voices import Voices


class VoiceLoader:

    def __init__(self):
        self.voices = Voices.load()
        self.voices_map = {}
        self._build_voices_map()

    def _build_voices_map(self):
        for voice in self.voices:
            self.voices_map[voice.name] = voice

    def process_text(self, text: str, voice_name: str):
        active_voice = self.voices_map[voice_name]

        return self.parse(text, active_voice.voice_file)

    @staticmethod
    def parse(text: str, voice_id: str) -> str:
        """
        :param text:
        :param voice_id:
        :return:
        """

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

        resp = requests.post("https://acapelavoices.acapela-group.com/index/getnonce", content)

        if not resp.status_code == 200:
            resp.raise_for_status()

        # match = re.match(r'"^\{\""nonce\""\:\""(.+)\""\}$"', resp.text)
        nonce = resp.json()["nonce"]

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

        resp = requests.post(req_url, payload, headers=headers)
        regs = re.search("snd_url=(.+)&snd_size", resp.content.decode("utf-8"))

        if regs:
            return regs.group(1)


class VoiceLoaderAsync(VoiceLoader):

    @staticmethod
    def parse(text: str, voice_id: str) -> str:
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

        resp = requests.post("https://acapelavoices.acapela-group.com/index/getnonce", content)

        if not resp.status_code == 200:
            resp.raise_for_status()

        # match = re.match(r'"^\{\""nonce\""\:\""(.+)\""\}$"', resp.text)
        nonce = resp.json()["nonce"]

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

        resp = requests.post(req_url, payload, headers=headers)
        regs = re.search("snd_url=(.+)&snd_size", resp.content.decode("utf-8"))

        if regs:
            return regs.group(1)


if __name__ == '__main__':
    loader = VoiceLoader()

    audio_url = loader.process_text("Hello world", "WillFromAfar")
    print(audio_url)
