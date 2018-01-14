"""Music player functionality"""

from .utils import config, checks
import logging
import discord
from discord.ext import commands
import traceback
from cogs.utils.audio.playlist import Playlist

log = logging.getLogger()


class MusicPlayer:

    def __init__(self, bot):
        self.bot = bot
        self.active_playlists = {}
        self.saved_songs = config.Config("saved_songs.json")

    async def kill_voice_connections(self):
        for voice_obj in self.bot.voice_clients:
            await voice_obj.disconnect()

    def get_playlist(self, ctx) -> Playlist:
        """Shorthand for getting the current bound playlist."""
        return self.active_playlists.get(ctx.message.guild.id)

    @commands.group(aliases=["sc"])
    async def mp(self):
        pass

    @mp.command(aliases=["init", "bind"])
    async def join(self, ctx, *, voice_channel_name: str=None):
        """Bind to a voice channel."""
        if ctx.guild.id in self.active_playlists.keys():
            await ctx.send("Already connected to a channel!")
            return
        if voice_channel_name is not None:
            voice_channel = discord.utils.get(ctx.guild.channels, name=voice_channel_name)
        elif ctx.message.author.voice is not None:
            voice_channel = ctx.author.voice.channel
        else:
            await ctx.send("Could not find a channel to bind to.")
            return

        voice_client = await voice_channel.connect()
        self.active_playlists[ctx.guild.id] = Playlist(self.bot, voice_client, ctx.message.channel)

        await ctx.send("`Bound to voice channel {0.name}`".format(voice_channel))
        log.info("Bound to voice channel {0.name}".format(voice_channel))

    @mp.command(aliases=["add"])
    async def queue(self, ctx, *, url: str):
        """Queue a song to be played, and play it if the playlist is empty."""
        if self.get_playlist(ctx) is None:
            if ctx.author.voice is not None:
                # TODO this is repeated above
                voice_client = await ctx.author.voice.channel.connect()
                await ctx.send("`Bound to voice channel {0.name}`".format(ctx.author.voice.channel))
                self.active_playlists[ctx.guild.id] = Playlist(self.bot, voice_client, ctx.message.channel)

            elif ctx.guild.id not in self.active_playlists.keys():
                await ctx.send("Not bound to a voice channel. Use `!sc init` to connect me.")
                return

        playlist = self.get_playlist(ctx)

        # Queue the last song in the playlist if it's requested
        if url.lower() == "last":
            url = playlist.last_song["url"]  # The last active song

        # Try to load from the saved list
        elif self.saved_songs.get(url) is not None:
            saved_song = self.saved_songs.get(url)
            url = saved_song
        try:
            async with ctx.typing():
                # Pull the track info first to check if it's a playlist or not
                info_dict = await playlist.get_track_info(url)
                if info_dict.get("_type") == "playlist":
                    index = await playlist.queue_playlist(info_dict)
                    await ctx.send("Playlist {} ({} items) queued successfully.".format(info_dict["title"],
                                                                                        len(info_dict["entries"])))
                else:
                    info_dict, index = await playlist.add_to_queue(url, ctx)
            if index == 0 and not playlist.is_playing:
                playlist.play_song()
                # TODO NOW PLAYING MESSAGE
            else:
                await ctx.send("Successfully queued song.")
        except Exception as e:
            traceback.print_exc()
            await ctx.send("Error when adding song: {}".format(type(e)))

    @checks.sudo()
    @mp.command(aliases=["skip"], hidden=True)
    async def next(self, ctx):
        """Skip a currently playing song"""
        playlist = self.get_playlist(ctx)
        # TODO: Find out why this hangs the bot
        # player = self.playlist[self.playlist_index - 1]["object"]  # The currently active song
        # if player.is_playing():
        #     player.stop()
        await playlist.skip()

    @checks.sudo()
    @mp.command()
    async def shuffle(self, ctx):
        playlist = self.get_playlist(ctx)
        playlist.shuffle()
        await ctx.send("Playlist shuffled!")

    @mp.command()
    async def list(self, ctx):
        playlist = self.get_playlist(ctx)
        # TODO Make this also show history
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
            del playlist  # Needed so we don't run into garbage collection issues
            await ctx.send("Disconnected.")
            log.info("Voice player killed forcefully by {.message.author.name}".format(ctx))

    # @mp.command(hidden=True)
    # # TODO: Test this
    # async def save(self, ctx, url: str, *, name: str):
    #     if utils.check_urls(url):
    #         url = Playlist.clean_url(url)
    #     elif url == "last":
    #         playlist = self.get_playlist(ctx)
    #         url = playlist.last_song.frontend_url
    #     else:
    #         await ctx.send("Bad input. !sc save <url> <name>")
    #         return
    #     await self.saved_songs.put(name, url)
    #     await ctx.send("Song saved successfully")

    # @mp.command()
    # async def saved(self, ctx):
    #     """List the saved songs"""
    #     output = "Saved songs:\n"
    #     for key in self.saved_songs:
    #         url = self.saved_songs.get(key)
    #         output += "`{}`: <{}>\n".format(key, url)
    #
    #     await ctx.send(output)

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
        for playlist in self.active_playlists.values():
            del playlist


def setup(bot):
    bot.add_cog(MusicPlayer(bot))
