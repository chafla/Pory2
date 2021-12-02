"""
Cog to play some audio at random intervals.
Functions similar to micspam, except is interruptable.
"""
import logging
import os
import time
import traceback
from typing import Optional
from numpy import random
import asyncio

from discord import VoiceClient
from discord.ext import commands
import discord


# TODO: In rewrite, make a superclass cog that handles audio playing to avoid this copy-pasting
# It should ideally have:
#   - Tracking for connection and disconnection events so we don't end up stuck in a channel without knowing
#   - A global list of audio clients so we can quickly (and easily) spin up audio clients and reuse existing ones
from cogs.utils import checks
from cogs.utils.utils import check_urls
from cogs.utils.audio.audio_utils import Downloader

log = logging.getLogger()

# Durations defined in terms of seconds
MAX_AUDIO_CLIP_DURATION = 30  # No clips longer than 30s for sanity's sake
MAX_OVERALL_DURATION = 3600   # and no queues longer than an hour
# TODO We should add pause functionality for interrupted audio


class BooWompGuildManager:
    """
    Manager for boowomp functionality per-guild.
    Manages cleaning up the audio file and voice client on destruction.
    """

    def __init__(self, bot, audio_url: str, voice_client: discord.VoiceClient, text_channel: discord.TextChannel,
                 downloader: Downloader, *, max_length_seconds: int = 3600, min_delay: int = 10):
        self.bot = bot
        self.downloader = downloader
        self.audio_url = audio_url
        self.audio_path = ""
        self.voice_client = voice_client
        self.text_channel = text_channel
        self.max_length_seconds = max_length_seconds
        self.min_delay = min_delay
        self._download_future = None

        self._shut_down = False
        self._started_time = None

        if max_length_seconds > MAX_OVERALL_DURATION:
            raise RuntimeError("Total duration too long, should be less than {} seconds".format(MAX_OVERALL_DURATION))

    def _send_message(self, message: str):
        self.bot.loop.create_task(self.text_channel.send(message))

    async def _download(self) -> str:
        stats = await self.downloader.download_stats_threaded(self.audio_url, self.bot.loop)
        self.audio_path = stats["expected_filename"]
        if stats.get("duration") > MAX_AUDIO_CLIP_DURATION:
            raise RuntimeError(
                "Audio clip is too long, should be less than {} seconds.".format(MAX_AUDIO_CLIP_DURATION)
            )

        fut = self.bot.loop.create_task(self.downloader.download_audio_coro(self.audio_url))

        return fut
        # audio_source = discord.PCMVolumeTransformer(audio_source, volume)

    async def play(self):
        self._started_time = time.time()

        # start and queue up the download task.
        # don't block on it, we'll await it later
        self._download_future = self.bot.loop.create_task(self._download())

        self._after(None)

    def _seconds_to_next_proc(self) -> Optional[int]:

        # Choose a random number of seconds
        # We'll use a normal distribution with a reasonably low mean but a pretty high sigma,
        # so it's still pretty likely for it to go low, but could still result in a pretty sizable amount of time
        # between activations.

        # if you're going to tweak a value in this to adjust frequency, probably try reducing sigma.
        seconds_to_next_proc = abs(random.normal(30, 120))

        if time.time() - self._started_time >= self.max_length_seconds:
            return None

        # If we're going to go over our max length, cut it off
        time_remaining = self.max_length_seconds - (time.time() - self._started_time)
        return min(time_remaining, seconds_to_next_proc)

    def _after(self, err):

        if err:
            traceback.print_exception(type(err), err, err.__traceback__)
            self._send_message("Error occurred during playback: {}".format(err))
            raise err  # Pass it up the stack so we can clean up after ourselves

        next_proc = self._seconds_to_next_proc()

        if next_proc is None:
            self.bot.loop.create_task(self.destroy())
            return

        self.bot.loop.create_task(self._delayed_play(next_proc))

    async def _delayed_play(self, seconds: int):
        """
        Wait asynchronously for a given number of seconds, then play voice client again.
        :param seconds:
        :return:
        """

        # Start the sleep. We'll want to wait up to this many seconds.
        # While that's going asynchronously, make sure our audio client is set up and ready to play.

        await asyncio.sleep(seconds)
        # TODO Check if we've been disconnected while waiting, and clean up properly

        # If we've been shut down while waiting, just dip before playing the next audio track
        # TODO Set this up on a listener

        # Await the sleeping future, since we want to wait the full time period.
        # We should have been downloading all this time, so the download task should be done by then.

        # if not, we await it too
        if self._download_future is not None:
            await self._download_future
            self._download_future = None

        # This should be quick
        audio_source = discord.FFmpegPCMAudio(self.audio_path)

        # rarely double the volume
        # I promise loud = funny
        if random.random() > 0.99:
            audio_source = discord.PCMVolumeTransformer(audio_source, 2)

        if self._shut_down:
            return

        self.voice_client.play(audio_source, after=lambda err: self._after(err))

    async def destroy(self):
        """
        Clean up; destroy the voice client and ensure the file gets nuked as well
        :return:
        """
        self._shut_down = True

        try:
            # make sure we aren't actively reading from the file
            if self.voice_client.is_playing():
                self.voice_client.stop()

            try:
                await self.voice_client.disconnect(force=False)
            except discord.ClientException:
                await self.voice_client.disconnect(force=True)
        finally:
            try:
                os.remove(self.audio_path)
            except FileNotFoundError:
                pass


class BooWomp(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.downloader = Downloader()

        # holds references to the "playlists" for each channel
        # each playlist will only be one song looped with a random delay in the after()
        self._active_guild_managers = {}

    @commands.group(aliases=["bw"], hidden=True)
    async def boowomp(self, ctx):
        """
        Play an audio url at random times over random intervals.
        """

    @boowomp.command()
    async def play(self, ctx, audio_url: str, length_in_minutes: int = 5):
        length_seconds = length_in_minutes * 60
        if length_seconds > MAX_OVERALL_DURATION and not checks.sudo_check(ctx.message):
            await ctx.send("Total length can't be longer than {} minutes.".format(MAX_OVERALL_DURATION // 60))

        await self._activate_clip(ctx, audio_url, length_in_minutes * 60)

    @boowomp.command()
    async def stop(self, ctx):
        if ctx.guild.id not in self._active_guild_managers:
            return
        await self.close(ctx.guild)

    async def join(self, voice_channel: discord.VoiceChannel, force=False) -> Optional[discord.VoiceProtocol]:
        """Bind to a voice channel. Will bind by default to the channel.
        TODO In the rewrite, this should absolutely be a base method for the new audio utilities
        """

        current_connection = voice_channel.guild.voice_client
        if force and current_connection and current_connection.guild.id in self._active_guild_managers:
            await current_connection.disconnect()
        elif current_connection and current_connection.guild.id not in self._active_guild_managers:
            return None

        voice_client = await voice_channel.connect()

        return voice_client

    def _loop_after(self, voice_client: VoiceClient, err, song_path, song_downloaded=False):
        pass

    async def close(self, guild: discord.Guild):
        """
        Close an audio connection in a guild.
        If we're moved or disconnected, make sure we clean up after ourselves.
        """
        manager = self._active_guild_managers[guild.id]
        await manager.destroy()
        del self._active_guild_managers[guild.id]  # I still hate this syntax

    async def _activate_clip(self, ctx: commands.Context, url: str, length_seconds: int):

        connected_successfully = False
        voice_client = None

        if isinstance(ctx.message.channel, discord.DMChannel):
            return

        if not check_urls(str(url)):
            await ctx.send("Non-url input passed in!")
            return

        try:
            # connect to the channel a user is currently connected to
            if hasattr(ctx.author, "voice") and ctx.author.voice is not None:
                try:
                    voice_client = await self.join(ctx.author.voice.channel)
                except discord.ClientException as e:
                    await ctx.send("Connecting failed: {}".format(e))
                    return

                connected_successfully = True

                await ctx.send(
                    "Bound to voice channel `{0.name}`, use `!bw stop` to stop.".format(ctx.author.voice.channel)
                )
                # linter will complain, but we're almost exclusively going to be getting the right type here
                new_manager = BooWompGuildManager(self.bot, url, voice_client, ctx.message.channel, self.downloader,
                                                  max_length_seconds=length_seconds)
                self._active_guild_managers[ctx.guild.id] = new_manager

            else:
                await ctx.send("Connect to a voice channel first!")
                return

            if not voice_client:
                # Failed for some unknown reason I suppose
                return

            # Finally, play the audio itself
            await new_manager.play()

        finally:
            if not connected_successfully and voice_client:
                await voice_client.disconnect(force=False)

    async def _kill_all(self):
        for manager in self._active_guild_managers.values():
            await manager.destroy()
        self._active_guild_managers = {}

    def __unload(self):
        if self._active_guild_managers:
            n_voice_connections = len(self._active_guild_managers)
            self.bot.loop.create_task(self._kill_all())
            log.info("Terminated {} boowomp connection(s) on bot reload.".format(n_voice_connections))


def setup(bot):
    bot.add_cog(BooWomp(bot))
