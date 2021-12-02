"""Music player functionality"""
from typing import Optional

from .utils import config, checks
import logging
import discord
from discord.ext import commands
import traceback
from cogs.utils.audio.playlist import Playlist

log = logging.getLogger()


class MusicPlayer(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.active_playlists = {}
        self.saved_songs = config.Config("saved_songs.json")

    def kill_voice_connections(self):
        for active_playlist in self.active_playlists:
            del active_playlist

    def get_playlist(self, ctx) -> Optional[Playlist]:
        """Shorthand for getting the current bound playlist."""
        return self.active_playlists.get(ctx.message.guild.id)

    @commands.group(aliases=["sc"])
    async def mp(self, ctx):
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

    async def _queue_song(self, ctx: commands.Context, url: str) -> bool:
        """
        Queue a song to be played, and play it if the playlist is empty.
        Returns true if the song was queued successfully, or false otherwise.
        """
        if self.get_playlist(ctx) is None:
            if ctx.author.voice is not None:
                # TODO this is repeated above
                voice_client = await ctx.author.voice.channel.connect()
                await ctx.send("`Bound to voice channel {0.name}`".format(ctx.author.voice.channel))
                self.active_playlists[ctx.guild.id] = Playlist(self.bot, voice_client, ctx.message.channel)

            elif ctx.guild.id not in self.active_playlists.keys():
                await ctx.send("Not bound to a voice channel. Use `!mp init` to connect me.")
                return False

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
                queued_msg = "Successfully queued song."
                if playlist.loop_count != 0:
                    queued_msg += "\n\nNote: loop is enabled, the queue will loop on the current song until looping " \
                                  "is disabled."
                await ctx.send(queued_msg)

            return True
        except Exception as e:
            traceback.print_exc()
            await ctx.send("Error when adding song: {}".format(type(e)))
            return False

    @mp.command(aliases=["add"])
    async def queue(self, ctx, *, url: str):
        await self._queue_song(ctx, url)

    @mp.command()
    async def loop(self, ctx, loop_count: int = None, *, url: str = None):
        """Set the current song to loop, or if the current song is looping, stop it from looping"""

        if loop_count is None:
            loop_count = -1

        playlist = self.get_playlist(ctx)
        if playlist is None or not playlist.active_song:
            # There's not a song playing right now
            # if the user passed in a song, queue it up and loop it
            # otherwise, let them know we won't track (since we might not have a playlist set up)
            if not url:
                await ctx.send("No song is playing right now.\n"
                               "Either call this command while a song is playing, "
                               "or call this command with a song URL.")
                return
            else:
                # playlist is initialized within this function
                song_queued = await self._queue_song(ctx, url)
                if not song_queued:
                    return

                playlist = self.get_playlist(ctx)

        elif playlist.loop_count != 0:
            playlist.loop_count = 0
            await ctx.send("This song will no longer loop.")
            return

        playlist.loop_count = loop_count - 1  # Zero counts too

        loop_message = "The current song will be looped"

        if loop_count > 0:
            loop_message += " {} time{}.".format(loop_count, "s" if loop_count != 1 else "")
        elif loop_count == 0:
            loop_message += "...not at all. It'll play once!"
        else:
            loop_message += " infinitely."
        await ctx.send(loop_message)

    @checks.has_manage_guild()
    @mp.command(aliases=["skip"], hidden=True)
    async def next(self, ctx):
        """Skip a currently playing song"""
        playlist = self.get_playlist(ctx)
        # TODO: Find out why this hangs the bot
        # player = self.playlist[self.playlist_index - 1]["object"]  # The currently active song
        # if player.is_playing():
        #     player.stop()
        await playlist.skip()

    @checks.has_manage_guild()
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

    @checks.has_manage_guild()
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
        if self.active_playlists:
            n = len(self.active_playlists)
            self.kill_voice_connections()
            log.info("Terminated {} voice connection(s) on bot reload.".format(n))


def setup(bot):
    bot.add_cog(MusicPlayer(bot))


# def unload(bot):
#     """
#     Just here as a failsafe
#     """
#     if bot.voice_clients:
#         n = len(bot.voice_clients)
#         bot.loop.create_task(MusicPlayer.kill_voice_connections(bot))
#         log.info("Terminated {} voice connection(s) on bot reload.".format(n))

