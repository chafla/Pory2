"""Music player functionality"""

from .utils import config, utils, checks
import logging
import discord
from discord.ext import commands
import asyncio
import traceback
from enum import Enum


class PlayerStatus(Enum):
    INACTIVE = 0
    READY = 1
    PROCESSING = 2
    PLAYING = 3

log = logging.getLogger()

ytdl_options = {
    'extractaudio': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    "ignoreerrors": False,
    "logtostderr": True,
    "quiet": False,
    "no_warnings": False,
    'audioformat': 'mp3'
}


class Playlist:

    def __init__(self, bot, voice_client, bound_text_channel):
        self.bot = bot
        self.queue = []
        self.last_song = None
        self.state = PlayerStatus.READY
        self._history = []  # All songs queued up
        self.voice_client = voice_client
        self.bound_text_channel = bound_text_channel
        self._bound_voice_channel = voice_client.channel

    def __str__(self):
        output = ""
        for n, player in enumerate(self.queue):  # List from the end of the current position
            if n == 0:
                n = "Current song"
            output += "{0}: **{1.title}** by *{1.uploader}*. Requested by {1.requested_by.display_name}\n".format(n, player)
        return output

    @property
    def length(self):
        return len(self.queue)

    @property
    def next_song(self):
        return self.queue[1] if len(self.queue) > 1 else None

    @property
    def current_song(self):
        return self.queue[0] if len(self.queue) > 0 else None

    @property
    def is_playing(self):
        return self.voice_client.is_playing()

    @staticmethod
    def format_dur(seconds):
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)

        # Roundabout way of making sure timestamps look good
        output = "{}".format(s)
        output = "{}:".format(m) + output if m > 0 else ""
        output = "{}:".format(h) + output if (m > 0 and h > 0) else ""
        return output

    def add_to_queue(self, player):
        self.queue.append(player)

    @staticmethod
    def clean_url(url):
        if "youtube" in url or "youtu.be" in url:
            url = url.split("&")[0]

        return url

    async def create_player(self, url, ctx):
        """
        Get a song's information, and create a dict that holds the basic info as well as the created song object.
        :param url: URL of a song to create the new object from
        :param ctx: Simple context
        :return: Dict containing song metadata as well as a new player object

        """
        # Parse out some problematic syntax
        self.state = PlayerStatus.PROCESSING

        url = self.clean_url(url)

        player = await self.voice_client.create_ytdl_player(url=url,
                                                            after=self.sc_after,
                                                            ytdl_options=ytdl_options)

        player.requested_by = ctx.message.author
        player.formatted_duration = self.format_dur(player.duration)

        if player.duration > 900:  # Greater than 15 mins
            raise RuntimeError("Requested songs must be less than 15 minutes.")

        self.state = PlayerStatus.READY

        return player

    def get_next_song(self):
        if len(self.queue) > 0:
            return self.queue[0]
        else:
            return None

    async def start_song(self):
        """
        Try to play the next song in the playlist.
        """
        cur_song = self.get_next_song()
        if cur_song is None:
            await self.bound_text_channel.send("Finished playing.")
            self.state = PlayerStatus.READY
            return
        else:
            log.debug("Song object ready")
            if self.voice_client is None:
                await self.bound_text_channel.send("Not bound to a voice channel.")
                return
            cur_song.start()
            log.info("Now playing: {0.title} by {0.uploader}".format(cur_song))
            self.state = PlayerStatus.PLAYING
            await self.bound_text_channel.send(
                                               "Now playing: **{0.title}** by *{0.uploader}*, requested by "
                                               "{0.requested_by.mention}.".format(cur_song))

    def sc_after(self):
        """Update player status, try to start the next song."""
        self.last_song = self.queue.pop(0)
        self.state = PlayerStatus.READY
        fut = asyncio.run_coroutine_threadsafe(self.start_song, self.bot.loop)
        try:
            fut.result()
        except Exception as e:
            # an error happened
            print("Error occured in future")
            print('{0.__class__.__name__}: {0}'.format(e))
            traceback.print_tb(e.__traceback__)
            traceback.print_last()


class MusicPlayer:

    def __init__(self, bot):
        self.bot = bot
        self.active_playlists = {}
        self.saved_songs = config.Config("saved_songs.json")

    # TODO: Add playlist support (?)

    async def kill_voice_connections(self):
        for voice_obj in self.bot.voice_clients:
            await voice_obj.disconnect()

    def get_playlist(self, ctx):
        """Shorthand for getting the current bound playlist."""
        return self.active_playlists.get(ctx.message.channel.id)

    @commands.group(aliases=["sc"])
    async def mp(self):
        pass

    @mp.command(aliases=["init", "bind"])
    async def join(self, ctx, *, voice_channel_name: str=None):
        """Bind to a voice channel."""
        if self.bot.is_voice_connected(ctx.message.guild):
            await ctx.send("Already connected to a voice channel.")
            return
        message = ctx.message
        if voice_channel_name is not None:
            voice_channel = discord.utils.get(message.guild.channels, name=voice_channel_name)
        elif ctx.message.author.voice is not None:
            voice_channel = ctx.message.author.voice.voice_channel
        else:
            await ctx.send("Could not find a channel to bind to.")
            return

        voice_client = await self.bot.join_voice_channel(voice_channel)
        self.active_playlists[ctx.message.channel.id] = Playlist(self.bot, voice_client, message.channel)

        await ctx.send("`Bound to voice channel {0.name}`".format(voice_channel))
        log.info("Bound to voice channel {0.name}".format(voice_channel))

    @mp.command(aliases=["add"])
    async def queue(self, ctx, url: str):
        """Queue a song to be played, and play it if the playlist is empty."""
        if not self.bot.is_voice_connected(ctx.message.guild):
            await ctx.send("Not bound to a voice channel. Use `!sc init` to connect me.")
            return

        playlist = self.get_playlist(ctx)

        # Queue the last song in the playlist if it's requested
        if url.lower() == "last":
            url = playlist.last_song.frontend_url  # The last active song

        # Try to load from the saved list
        elif self.saved_songs.get(url) is not None:
            saved_song = self.saved_songs.get(url)
            url = saved_song

        player = await playlist.create_player(url, ctx)  # TODO: Move this
        if player is not None:
            playlist.add_to_queue(player)
            await ctx.send("Successfully queued song.")

            if playlist.length == 1 and playlist.state == PlayerStatus.READY:  # Start next song if empty playlist
                await playlist.start_song()

        else:
            await ctx.send("Error adding song.")
            return

    @checks.sudo()
    @mp.command(aliases=["skip"], hidden=True, enabled=False, )
    async def next(self, ctx):
        """Skip a currently playing song"""
        playlist = self.active_playlists[ctx.message.channel.id]
        # TODO: Find out why this hangs the bot
        # player = self.playlist[self.playlist_index - 1]["object"]  # The currently active song
        # if player.is_playing():
        #     player.stop()
        await playlist.start_song()

    @mp.command()
    async def list(self, ctx):
        playlist = self.active_playlists[ctx.message.channel.id]
        if playlist:
            await ctx.send(str(playlist))
        else:
            await ctx.send("The queue is currently empty.")

    @checks.is_pokemon_mod()
    @mp.command(invoke_without_command=True)
    async def kill(self, ctx):
        playlist = self.get_playlist(ctx)
        """Kill the voice connection"""
        if playlist.voice_client is not None:
            # Clean up
            await playlist.voice_client.disconnect()
            del self.active_playlists[ctx.message.channel.id]  # Needed so we don't run into garbage collection issues
            await ctx.send("Disconnected.")
            log.info("Voice player killed forcefully by {.message.author.name}".format(ctx))

    @mp.command(hidden=True)
    # TODO: Test this
    async def save(self, ctx, url: str, *, name: str):
        if utils.check_urls(url):
            url = Playlist.clean_url(url)
        elif url == "last":
            playlist = self.get_playlist(ctx)
            url = playlist.last_song.frontend_url
        else:
            await ctx.send("Bad input. !sc save <url> <name>")
            return
        await self.saved_songs.put(name, url)
        await ctx.send("Song saved successfully")

    @mp.command()
    async def saved(self, ctx):
        """List the saved songs"""
        output = "Saved songs:\n"
        for key in self.saved_songs:
            url = self.saved_songs.get(key)
            output += "`{}`: <{}>\n".format(key, url)

        await ctx.send(output)

    @mp.error
    async def sc_error(self, error, ctx):
        if type(error) in [commands.BadArgument, commands.MissingRequiredArgument]:
            await ctx.send(error)
        log.warning('{0.__class__.__name__}: {0}'.format(error))
        log.warning(str(error.__traceback__))
        traceback.print_tb(error.__traceback__)
        # TODO: 403 errors are sometimes thrown by ytdl; catch those

    def __unload(self):
        if self.bot.voice_clients:
            n = len(self.bot.voice_clients)
            self.bot.loop.create_task(self.kill_voice_connections())
            log.info("Terminated {} voice connection(s) on bot reload.".format(n))


def setup(bot):
    bot.add_cog(MusicPlayer(bot))
