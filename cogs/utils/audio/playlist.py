"""
Playlist setup for the music player.

Procedure should be like this:
    - Connect to voice channel, initializing a new playlist which is saved per vc.
    - Wait on further action.
    - When a new song is queued up, create a new `Entry` object which contains the song info. Could even just be the dict.
    - Fetch stats first for the entry. After, create a future object that is tracked as an instance variable. The player
        will wait for this to proceed before playing the next song.
        - If another song is queued up while the current one is queueing/playing; create the object, try to download it
            in the background, and add it to the queue.
    - Play the song once it's ready, removing it from the queue and adding it to an instance var `current_song` as well
        as a `history` queue. The track should never be in the playing queue if it has been touched.
    - Proceed to the next one.

"""
from cogs.utils.audio.audio_utils import Downloader
import concurrent.futures
import logging
import os
import discord
import traceback
from random import shuffle


log = logging.getLogger()


base_ytdl_options = {
    "format": "bestaudio/best",
    "outtmpl": ".tmp/%(title)s-%(id)s.%(ext)s",
    "noplaylist": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "no_warnings": True,
    "source_address": "0.0.0.0",
    # "quiet": True
}


class Playlist:

    def __init__(self, bot, voice_client, bound_text_channel, executor=None):
        """
        Playlist for dealing with entries for
        :param bot:
        :param voice_client:
        :param bound_text_channel:
        """
        self.bot = bot
        self.voice_client = voice_client
        self.bound_text_channel = bound_text_channel
        self._bound_voice_channel = voice_client.channel
        self.downloader = Downloader()
        if executor is None:
            self.executor = self.downloader.executor
        else:
            self.executor = executor

        self.active_song = None
        self.live_queue = []
        self._history_queue = []
        self._skipped_last = False

    def __len__(self):
        return len(self.live_queue)

    def __repr__(self):
        return "Playlist\nBound to channel {}\n{} items\n{}".format(
            self._bound_voice_channel.name,
            len(self.live_queue),
            "\n".join([i["title"] for i in self.live_queue])
        )

    def __str__(self):
        return "\n".join([i["title"] for i in self.live_queue])

    @property
    def last_song(self):
        try:
            return self._history_queue[-1]
        except IndexError:
            return None

    @property
    def is_playing(self):
        return self.voice_client.is_playing()

    @property
    def current_playlist(self):
        output = "**Current song:** {}\n".format(self._build_track_message(self.active_song))
        output += "\n".join([self._build_track_message(i) for i in self.live_queue])
        return output

    async def _create_new_entry(self, song_url):
        """Download and initialize a new song/track."""
        # Start the music download first
        audio_future = self.executor.submit(self.downloader.download_audio, song_url)
        # Get the track info while that's going on, since it might take longer
        info_future = self.executor.submit(self.downloader.download_stats, song_url)

        concurrent.futures.wait([audio_future, info_future], 30, return_when=concurrent.futures.ALL_COMPLETED)

        return info_future.result()  # Might be able to do something with this at this point, maybe emit an event

    async def get_track_info(self, song_url):
        info_future = self.executor.submit(self.downloader.download_stats, song_url)
        return info_future.result()

    def _send_message(self, message_content):
        """Send a message to the bound text channel from a non-async context"""
        self.bot.loop.create_task(self.bound_text_channel.send(message_content))

    @staticmethod
    def _build_track_message(info_dict, mention_requester=False):
        """Most we are sure to get is url, title, and ID. Create a song repr that doesn't crash out."""
        ret = "**{}**".format(info_dict["title"])
        if info_dict.get("uploader"):
            ret += " by {}\n".format(info_dict["uploader"])

        if info_dict.get("requester"):
            ret += "\nrequested by {}".format(info_dict["requester"].mention if mention_requester else
                                              str(info_dict["requester"]))

        return ret.format(info_dict)

    def shuffle(self):
        shuffle(self.live_queue)

    async def add_to_queue(self, url, ctx=None, **extra_info_tags):
        # TODO add basic playlist support
        """
        Add a new song to the queue.
        Returns the track's info dict and the position in the queue.
        """
        info_dict = await self._create_new_entry(url)

        if ctx:
            info_dict["requester"] = ctx.message.author

        if extra_info_tags:
            info_dict = {**info_dict, **extra_info_tags}

        self.live_queue.append(info_dict)
        index = self.live_queue.index(info_dict)

        if index == 0 and self.active_song is None:
            # As soon as it pops up, set it to be active. This avoids any leftovers.
            self.active_song = self.live_queue.pop(0)

        # If the index is 0, then we'd play
        return info_dict, index

    async def queue_playlist(self, playlist_info_dict, ctx=None):
        # TODO Consider making this a generator function which just sits in the playlist and yields items
        # Implement this to reduce the initial load time so we don't just kill off pory
        first_index = 2e1000

        for i, entry in enumerate(playlist_info_dict["entries"]):
            # The downloaded_url is a little different
            entry["expected_filename"] = self.downloader.client.prepare_filename(entry)
            if ctx:
                entry["requester"] = ctx.message.author

            if i < 3:
                await self._create_new_entry(entry["url"])  # Download the track
            else:
                entry["not_downloaded"] = True
            # info_dict, index = await self.add_to_queue(entry["url"])
            self.live_queue.append(entry)
            index = self.live_queue.index(entry)
            if i == 0 and self.active_song is None and index == 0:
                first_index = index
                self.active_song = self.live_queue.pop(0)

        return first_index

    def after_song(self, err):

        if err:
            traceback.print_exception(type(err), err, err.__traceback__)
            self._send_message("Error occurred during playback: {}".format(err))

        self._history_queue.append(self.active_song)
        try:
            # We need to check to see if the last one was skipped because it seems that sometimes a skip will have
            # already executed the after_song in its after
            self.active_song = self.live_queue.pop(0)
            # if not self._skipped_last:
            #     self.active_song = self.live_queue.pop(0)
            # else:
            #     self.active_song = self.live_queue.pop(0)
            #     self._skipped_last = False

            if self.active_song.get("not_downloaded"):
                future = self.executor.submit(self.downloader.download_audio, self.active_song["url"])
                concurrent.futures.wait([future], 30, return_when=concurrent.futures.FIRST_COMPLETED)
                future.result()
            # self.bot.loop.create_task(self.play_song())
            self.play_song()
        except IndexError:
            # It's empty: end of playlist
            self.active_song = None
            self._send_message("End of queue reached.")

    def play_song(self):
        # TODO: Give more info
        # We are only guaranteed url, title, id, filename
        audio_source = discord.FFmpegPCMAudio(self.active_song["expected_filename"])
        self.voice_client.play(audio_source, after=lambda err: self.after_song(err))
        self._send_message("Now playing: {}".format(self._build_track_message(self.active_song)))

    async def skip(self):
        self.voice_client.stop()  # automatically calling the after fn
        # self._skipped_last = True
        self._send_message("Skipping.")

    def __del__(self):
        """Clean up any remaining cache files that we're keeping track of"""
        for info in self.live_queue:
            os.remove(info["expected_filename"])
        for info in self._history_queue:
            os.remove(info["expected_filename"])
        if self.active_song is not None:
            os.remove(self.active_song["expected_filename"])

        self.bot.loop.create_task(self.voice_client.disconnect())
