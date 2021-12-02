"""Micspam"""
import asyncio
import glob
import logging
from typing import List, Union, Optional
import re
import requests.utils

import discord
from discord import VoiceClient
from discord.ext import commands
from discord.ext.commands import Context

from .utils import checks
from cogs.utils.audio import audio_utils
from sys import stderr
from .utils.utils import check_ids, check_urls
from .utils.audio.voiceloader_async import VoiceLoaderAsync
from os import remove
import random


log = logging.getLogger()


class CtxMessageWrapper:

    def __init__(self, message: discord.Message):
        self.message = message
        self.channel = message.channel
        self.author = message.author

    def send(self, *args, **kwargs):
        return self.channel.send(*args, **kwargs)


class Micspam(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.downloader = audio_utils.Downloader()
        self.config = bot.config

        # Guilds we're currently micspamming
        # If a guild in here has a pory voice client, then we are okay to disconnect the existing
        # voice client, since it'd just be interrupting more micspam.
        self._currently_active_guilds = set()

    @staticmethod
    def get_micspam(clip_chosen, song_list):
        try:
            return song_list[clip_chosen]
        except IndexError:
            return None

    def micspam_after(self, voice_client: VoiceClient, err, song_path, song_downloaded=False):

        coro = voice_client.disconnect()
        fut = asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
        self._currently_active_guilds.remove(voice_client.guild.id)

        if song_downloaded:
            remove(song_path)

        if err is not None:
            print("Error occured in future")
            print('{0.__class__.__name__}: {0}'.format(err), file=stderr)

        try:
            fut.result()
        except Exception as e:
            # an error happened
            print("Error occured in future")
            print('{0.__class__.__name__}: {0}'.format(e), file=stderr)

    async def _connect_cleanly(self, voice_channel) -> Optional[VoiceClient]:
        current_connection = voice_channel.guild.voice_client
        if current_connection and current_connection.guild.id in self._currently_active_guilds:
            await current_connection.disconnect()
        elif current_connection and current_connection.guild.id not in self._currently_active_guilds:
            return None
        self._currently_active_guilds.add(voice_channel.guild.id)
        return await voice_channel.connect()

    async def play_micspam(self, channel, clip_chosen, ctx, volume: float = 1.0):
        """Formerly are_you_capping()"""
        voice_client = None
        downloaded = False

        meme_list = glob.glob("micspam/*.*")

        try:

            if hasattr(ctx.author, "voice") and ctx.author.voice is not None:
                voice_client = await self._connect_cleanly(ctx.author.voice.channel)
            elif check_ids(str(channel)):
                chan = self.bot.get_channel(int(channel))
                voice_client = await self._connect_cleanly(chan)
            else:
                try:
                    for guild in self.bot.guilds:
                        if guild.id in [111504456838819840, 110373943822540800, 155800402514673664,
                                        78716585996455936, 78469422049665024, 344285545742204940]:
                            chan = discord.utils.get(guild.voice_channels, name=str(channel))
                            if chan is None:
                                continue
                            else:
                                voice_client = await self._connect_cleanly(chan)
                                log.info("Micspam bound successfully to {.name}".format(voice_client.channel))
                                break

                except Exception as e:
                    log.exception("Error in micspam")
                    try:
                        await ctx.send("Couldn't find that channel or already connected")
                    except discord.ClientException:
                        pass
                    return

            if not voice_client:
                await ctx.send("Already connected to voice in the same guild for another cog.")
                return

            if check_urls(str(clip_chosen)):
                await self.downloader.download_audio_threaded(clip_chosen, self.bot.loop)
                stats = await self.downloader.download_stats_threaded(clip_chosen, self.bot.loop)
                micspam_path = stats["expected_filename"]
                downloaded = True
            else:
                micspam_path = self.get_micspam(int(clip_chosen), meme_list)

            if micspam_path is not None:
                audio_source = discord.FFmpegPCMAudio(micspam_path)
                audio_source = discord.PCMVolumeTransformer(audio_source, volume)
                voice_client.play(audio_source, after=lambda err: self.micspam_after(voice_client, err, micspam_path,
                                                                                     downloaded))
            else:
                try:
                    await ctx.message.channel.send("That micspam value doesn't exist.")
                except discord.ClientException:
                    pass
                return

        except Exception as e:
            # Ensure we don't get pory stuck in here
            if voice_client:
                await voice_client.disconnect(force=True)
            raise e

    @checks.sudo()
    @commands.command()
    async def reset(self, ctx: Context):
        """
        Reset all voice clients in the current guild.
        """
        if ctx.guild.voice_client is not None:
            await ctx.guild.voice_client.disconnect(force=True)

    @checks.sudo()
    @commands.command(hidden=True, pass_context=True, aliases=["spam"])
    async def capp(self, ctx, file: str, *, channel_name: str):
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

    @commands.command(hidden=True)
    async def moonbase(self, ctx, *, message: str):
        if ctx.message.author.voice is not None:
            endpoint = "http://tts.cyzon.us/tts?text={}".format(requests.utils.quote(message))
            await self.play_micspam(ctx.message.author.voice.channel, endpoint, ctx, 3)

    @commands.command(hidden=True)
    async def tts(self, ctx, *, message: str):
        if ctx.message.author.voice is not None:
            voice_loader = VoiceLoaderAsync()
            if len(message) > 300:
                await ctx.send("Message too long, trimmed to 300 chars")
            url = await voice_loader.process_text(message[:300], "WillFromAfar")
            await self.play_micspam(ctx.message.author.voice.channel.id, url, ctx)

    @commands.command(hidden=True)
    async def randtts(self, ctx, *, message: str):
        if ctx.message.author.voice is not None:
            voice_loader = VoiceLoaderAsync()
            voice = random.choice(voice_loader.voices)
            url = await voice_loader.process_text(message[:300], voice.name)
            if len(message) > 300:
                await ctx.send("Message too long, trimmed to 300 chars")
            await self.play_micspam(ctx.message.author.voice.channel.id, url, ctx)

    @commands.command(hidden=True)
    async def choice_tts(self, ctx, voice: str, *, message: str):
        if ctx.message.author.voice is not None:
            voice_loader = VoiceLoaderAsync()
            url = await voice_loader.process_text(message[:300], voice)
            if len(message) > 300:
                await ctx.send("Message too long, trimmed to 300 chars")
            await self.play_micspam(ctx.message.author.voice.channel.id, url, ctx)

    @commands.command(hidden=True)
    async def yoda(self, ctx, *, message: str):
        if ctx.message.author.voice is not None:
            voice_loader = VoiceLoaderAsync()
            url = await voice_loader.process_text(message[:300], "WillLittleCreature")
            if len(message) > 300:
                await ctx.send("Message too long, trimmed to 300 chars")
            await self.play_micspam(ctx.message.author.voice.channel.id, url, ctx)

    @commands.command(hidden=True)
    async def up_close(self, ctx, *, message: str):
        if ctx.message.author.voice is not None:
            voice_loader = VoiceLoaderAsync()
            url = await voice_loader.process_text(message[:300], "WillUpClose")
            if len(message) > 300:
                await ctx.send("Message too long, trimmed to 300 chars")
            await self.play_micspam(ctx.message.author.voice.channel.id, url, ctx)

    async def kill_voice_connections(self):
        for voice_obj in self.bot.voice_clients:
            if voice_obj.channel.guild.id in self._currently_active_guilds:
                await voice_obj.disconnect(force=True)

    async def respond_to_keyword(self, message, allowed_guilds: List[int], response: int):
        if message.guild is not None and message.guild.id in allowed_guilds and \
                message.author.voice is not None:
            await self.play_micspam(message.author.voice.channel.id,
                                    response,
                                    CtxMessageWrapper(message))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # TODO FIX THIS NASTY HACK
        if " owo " in message.content or message.content == "owo":
            await self.respond_to_keyword(message,
                                          [274731851661443074, 283101596806676481, 401182039421747210, 78716585996455936, 146626123990564864, 392161981261545473, 484966083795746816],
                                          random.choice([2, 11, 20, 23, 30, 36, 40]))
        elif " goo " in message.content or (message.content == "goo" and not message.content == "!goo"):
            await self.respond_to_keyword(message,
                                          [78716585996455936, 344285545742204940],
                                          31)
        elif "quagf" in message.content:
            await self.respond_to_keyword(message,
                                          [78716585996455936, 344285545742204940],
                                          3)

    def __unload(self):
        if self._currently_active_guilds:
            n = len(self._currently_active_guilds)
            self.bot.loop.create_task(self.kill_voice_connections())
            log.info("Terminated {} voice connection(s) on bot reload.".format(n))


def setup(bot):
    bot.add_cog(Micspam(bot))
