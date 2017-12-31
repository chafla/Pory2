"""Randomly drop in on some unsuspecting people in voice and quack :eyes:"""

import discord
import random
import logging
import asyncio
from sys import stderr

log = logging.getLogger()


class QuackBot:

    def __init__(self, bot):
        self.bot = bot
        self._voice_client = None

    def quack_after(self, voice_client):
        coro = voice_client.disconnect()
        fut = asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
        try:
            fut.result()
        except Exception as e:
            # an error happened
            print("Error occured in future")
            print('{0.__class__.__name__}: {0}'.format(e), file=stderr)

    async def quack(self, channel):
        if len(self.bot.voice_clients) > 0:  # TODO: Won't be a prob. w/ bot acct
            log.info("Micspam failed. Already connected.")
            return
        self._voice_client = await self.bot.join_voice_channel(channel)

        player = self._voice_client.create_ffmpeg_player("micspam/quack.mp3",
                                                         after=lambda: self.quack_after(self._voice_client))
        player.start()

    async def on_timer_update(self, seconds):
        # Let's make it really not trigger that often
        rand = random.random()
        if seconds % 300 == 0 and ((rand < 0.005 and self.bot.instance == "Porygon2") or
                                   rand < 0.005) and self.bot.instance == "PorygonLounge":
            for guild in self.bot.guilds:
                quack_channel = discord.utils.find(lambda c: (len(c.members) > 1) and
                                                   isinstance(c, discord.VoiceChannel), guild.channels)
                if quack_channel is not None:
                    break
            else:
                log.debug("Tried to quack but found no suitable voice channels.")
                return

            await self.quack(quack_channel)
            log.info("Quacked {0.name} in {0.server.name}".format(quack_channel))


def setup(bot):
    bot.add_cog(QuackBot(bot))
