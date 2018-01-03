"""Micspam"""
import asyncio
import glob
import logging
import discord
from discord.ext import commands
from .utils import checks
from sys import stderr
from .utils.utils import check_ids


log = logging.getLogger()


class Micspam:

    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def get_micspam(clip_chosen, song_list):
        try:
            return song_list[clip_chosen]
        except IndexError:
            return None

    def micspam_after(self, voice_client, err):
        coro = voice_client.disconnect()
        fut = asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

        if err is not None:
            print("Error occured in future")
            print('{0.__class__.__name__}: {0}'.format(err), file=stderr)

        try:
            fut.result()
        except Exception as e:
            # an error happened
            print("Error occured in future")
            print('{0.__class__.__name__}: {0}'.format(e), file=stderr)

    async def _connect_cleanly(self, voice_channel):
        current_connection = discord.utils.find(lambda c: c.channel == voice_channel or c.channel.guild == voice_channel.guild,
                                                self.bot.voice_clients)
        if current_connection is not None:
            current_connection.disconnect()
        return await voice_channel.connect()

    async def play_micspam(self, channel, song_id, ctx):
        """Formerly are_you_capping()"""
        clip_chosen = song_id
        voice_client = None

        meme_list = glob.glob("micspam/*.*")

        if hasattr(ctx.author, "voice") and ctx.author.voice is not None:
            voice_client = await self._connect_cleanly(ctx.author.voice.channel)
        elif check_ids(str(channel)):
            chan = self.bot.get_channel(int(channel))
            voice_client = await self._connect_cleanly(chan)
        else:
            try:
                for guild in self.bot.guilds:
                    if guild.id in [111504456838819840, 110373943822540800, 155800402514673664,
                                    78716585996455936, 78469422049665024]:
                        chan = discord.utils.get(guild.voice_channels, name=str(channel))
                        if chan is None:
                            continue
                        else:
                            voice_client = await self._connect_cleanly(chan)
                            log.info("Micspam bound successfully to {.name}".format(voice_client.channel.name))
                            break

            except Exception as e:
                log.exception("Error in micspam")
                await ctx.send("Couldn't find that channel or already connected")
                return

        micspam_path = self.get_micspam(clip_chosen, meme_list)
        if micspam_path is not None:
            audio_source = discord.FFmpegPCMAudio(micspam_path)
            voice_client.play(audio_source, after=lambda err: self.micspam_after(voice_client, err))
        else:
            await ctx.message.channel.send("That micspam value doesn't exist.")
            return

    @checks.sudo()
    @commands.command(hidden=True, pass_context=True, aliases=["spam"])
    async def capp(self, ctx, file: int, *, channel_name: str):
        """
        Micspam a certain channel
        :param ctx: Context
        :param channel_name: Voice channel name
        :param file: File (digit) found by %micspam
        :return: None
        """
        await self.play_micspam(channel_name, file, ctx)

    @commands.command(hidden=True, pass_context=True)
    async def grand_dad(self, ctx):
        """Fleenstones!?"""
        if ctx.message.author.voice is not None:
            await self.play_micspam(ctx.message.author.voice.voice_channel.name, 9, ctx)

    @checks.sudo()
    @commands.command(hidden=True)
    async def micspam(self, ctx):
        meme_list = glob.glob("micspam/*.*")
        output_msg = ""
        for n, file in enumerate(meme_list):
            output_msg += "{0}: {1}\n".format(n, file)

        await ctx.send(output_msg)


def setup(bot):
    bot.add_cog(Micspam(bot))
