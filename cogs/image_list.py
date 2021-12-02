"""
Commands for imgur lists and stuff.

Config lies under `img`

img:
    albums:
        album_name:ids:
            set of album IDs
    cache:


"""

import asyncio
import logging
import json
import random
import re
import sys
import time
import webbrowser

import requests

import discord

from discord.ext import commands
from discord.ext.commands import Bot, Context
from imgurpython import ImgurClient
from imgurpython.client import ImgurClientError
from redis import ResponseError
from typing import Union, List, Optional, Dict, Set

from .utils import checks, rate_limits, redis_config
from .utils.utils import check_urls

log = logging.getLogger()

config = redis_config.RedisConfig()


class ImgurAuth(commands.Cog):
    FORCE_AUTH = True

    def __init__(self) -> None:
        with open('auth.json', 'r+', encoding='utf-8') as outfile:
            self.auth = json.load(outfile)

        self.imgur_client = self.attempt_imgur_auth()

    def imgur_auth_from_pin(self) -> ImgurClient:
        # If there are no valid imgur auth tokens saved, authenticate with a pin to refresh/initialize them.
        imgur_client = ImgurClient(self.auth['client_id'], self.auth['client_secret'])
        authorization_url = imgur_client.get_auth_url('pin')
        print(authorization_url)
        webbrowser.open(authorization_url)  # Launch web browser to get pin
        pin = input("Enter OAUTH pin: ")
        try:
            credentials = imgur_client.authorize(pin, 'pin')
            imgur_client.set_user_auth(credentials['access_token'], credentials['refresh_token'])
            self.auth['access_token'] = credentials['access_token']
            self.auth['refresh_token'] = credentials['refresh_token']
            with open('auth.json', 'w') as outfile:
                json.dump(self.auth, outfile, indent=4, sort_keys=True)  # Cache keys for later use
            return imgur_client
        except Exception as e:
            log.warning("Could not connect to imgur. Retrying in 5s.")
            if self.FORCE_AUTH:
                time.sleep(5)  # This might not work with async
                self.imgur_auth_from_pin()
            else:
                raise e

    def imgur_auth_from_cache(self) -> Optional[ImgurClient]:
        # Try to authenticate with saved credentials present in auth.json.
        try:
            imgur_client = ImgurClient(**self.auth["imgur"])
            imgur_client.get_account("namen")
            return imgur_client
        except Exception as e:
            log.exception("Could not authenticate for some reason. Fetching new access/refresh tokens.",
                          exc_info=True)
            # log.info("Could not authenticate for some reason. Fetching new access/refresh tokens.")
            log.info("Error returned:({0.__class__.__name__}: {0}".format(e), file=sys.stderr)
            return None

    def attempt_imgur_auth(self) -> ImgurClient:
        try_auth = self.imgur_auth_from_cache()
        if try_auth is None:  # If client object doesn't exist for some reason
            log.info("Could not authenticate for some reason. Fetching new access/refresh tokens.")
            return self.imgur_auth_from_pin()
        else:
            log.debug("Authenticated for imgur with stored tokens.")
            return try_auth


class ImageList:
    _auth = ImgurAuth()
    imgur_client = _auth.attempt_imgur_auth()
    bot = None

    def __init__(
            self, name: str, album_ids: List[str],
            image_list: Optional[List[str]] = None, added_msg: Optional[str] = None
    ) -> None:
        """
        Handles image lists, for meme commands such as fug and nonya. Allows for images to be added to albums and then
        extracted when needed.

        :param name: Name of the command the list belongs to
        :param album_ids: A list of imgur album IDs.
        """
        self.album_list = album_ids
        self.name = name
        self.images = []  # List of URLs from the related imgur albums.

        self.images = self.load_from_imgur(*album_ids) if not image_list else image_list

        self._blacklisted_images = set()

        self.msg_on_add = added_msg

    def __len__(self) -> int:
        return len(self.images)

    @property
    def image_count(self) -> int:
        return len(self)

    def save_to_cache(self) -> None:
        """Create a task to update the instance as well as writing to cache."""
        self.bot.loop.create_task(self.to_cache())

    def load_from_imgur(self, *album_ids: str) -> List[str]:
        """Load image urls from imgur."""
        image_urls = []
        if not album_ids:
            album_ids = self.album_list

        for album in album_ids:
            try:
                image_list = self.imgur_client.get_album_images(album)
            except Exception as e:
                log.warning('Encountered exception when fetching album {}\n {}: {}'.format(album, type(e).__name__, e))
                continue
            for image in image_list:
                image_urls.append(image.link)

        return image_urls

    # Best guess at `blacklist` type. Param never used.
    def get_image(self, blacklist: Optional[List[str]] = None):
        # Allow for blacklisting to occur since deleting is a pita
        if blacklist is not None:
            while True:
                img = random.choice(self.images)
                if img not in blacklist:
                    return img
        else:
            return random.choice(self.images)

    async def add_to_list(
            self,
            ctx: Context,
            url: str,
            user_whitelist: List[int] = None,
            target_album_id: str = None
    ) -> None:  # Needs to pass in global client
        """
        Add an image to an imgur album.
        Note that the album does need to have been created by the user acct the bot uses.
        """
        message = ctx.message
        if (user_whitelist is not None and message.author.id in user_whitelist) or checks.sudo_check(message):
            img = self.imgur_client.upload_from_url(url, anon=False)
            target = target_album_id if target_album_id else self.album_list[-1]
            self.imgur_client.album_add_images(target, img["id"])  # Pull from the last album to add to it
            self.images.append(img["link"])
            added_msg = "{} added successfully".format(self.name) if self.msg_on_add is None else self.msg_on_add
            log.info("New {} added by {}.".format(self.name, ctx.message.author.name))
            await ctx.send(added_msg)

            self.save_to_cache()

    async def remove_album(self, album_id: str) -> 'ImageList':
        """Remove an album and all its images from the image list."""
        config.srem("img:albums:{}:ids".format(self.name), album_id)  # Expected to raise an error
        return ImageList.from_cache(self.name)

    def to_dict(self) -> Dict[str, Union[str, Dict[str, Union[List[str], int]]]]:
        """Write the object to a dictionary form for use in caching. Update it from imgur as well."""

        images = []
        output = {
            "name": self.name,
            "albums": {}
        }

        for album_id in self.album_list:
            album_image_urls = [i.link for i in self.imgur_client.get_album_images(album_id)]
            images.extend(album_image_urls)
            output["albums"][album_id] = {
                "image_urls": album_image_urls,
                "image_count": len(album_image_urls)
            }

        # Since we're going to be fetching all images from imgur anyway, we might as well update the instance here too
        # so that we catch any new images that might have been added in the meantime.
        self.images = images

        return output

    async def to_cache(self) -> None:
        images = []
        config.set("img:cache:{}:name".format(self.name), value=self.name)
        for album_id in self.album_list:
            album_image_urls = self.load_from_imgur(album_id)  # safe function
            if album_image_urls:
                images.extend(album_image_urls)
                config.sadd("img:cache:{}:albums:{}:urls".format(self.name, album_id), *album_image_urls)
        try:
            config.sadd("img:cache:{}:imgs".format(self.name), *images)
        except ResponseError:
            log.exception("Could not add images for album {}: is it empty?".format(self.name))

        self.images = images  # Since we're pulling them all from imgur again anyway

    @classmethod
    def from_cache(cls, image_list_name: str) -> 'ImageList':
        album_ids = list(config.smembers("img:albums:{}:ids".format(image_list_name)))
        image_list = list(config.smembers("img:cache:{}:imgs".format(image_list_name)))
        return cls(image_list_name, album_ids, image_list=image_list)


class ImageListCommands(commands.Cog):
    REVERSE_SEARCH_PFX = "https://www.google.com/searchbyimage?image_url={}"

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        ImageList.bot = bot
        self.list_objs = []
        self._cache_updating = False

        self._external_commands = []  # Commands which are not hardcoded but generated from redis

        self.config = self.bot.config
        # self.raw_album_dict = config.scan(match="img:albums")[1]  # This one's updated with manual commands.
        for set_name in config.scan_iter(match="img:albums:*"):  # scan over all of the image lists
            command_name = set_name.split(":")[-2]

            # Try to load from the cache.
            if config.exists("img:cache:{}:imgs".format(command_name)):
                new_image_list = ImageList.from_cache(command_name)

            else:
                # If it doesn't exist in the cache yet, load it from imgur, then cache it.
                new_image_list = ImageList(command_name, list(config.smembers(set_name)))
                log.info("Album {} was not in cache, adding.".format(command_name))
                # new_image_list.save_to_cache()  # They all get cached later anyway

            # If a command is already defined as a function in the class, we'll ignore it here
            if not hasattr(self, command_name):
                self.create_new_command(command_name)

            self.list_objs.append(new_image_list)

        log.info("Image lists initialized.")
        self.bot.loop.create_task(self.update_cache())

    def get_blacklist(self, cmd_name) -> Set[str]:
        return self.config.smembers("img:{}:blacklist".format(cmd_name))

    async def new_command_func(self, cog, ctx):
        await self.process_command(ctx)

    def create_new_command(self, name: str):
        new_cmd = commands.Command(self.new_command_func, name=name)
        # new_cmd = commands.command(name=name, pass_context=True)(self.new_command_func)
        new_cmd.cog = self
        # new_cmd.cog_name
        self._external_commands.append(new_cmd)
        self.bot.add_command(new_cmd)

    def update_commands(self):

        # @commands.command()

        # new_cmd = commands.command(name="test")(self.new_command_func)

        for cmd in self._external_commands:
            cmd.cog_name = self.__class__.__name__

        print("a")

        # self.bot.add_command(new_cmd)

    def update_external_commands(self, cog):
        """
        Update the external commands so they reflect the current cog.
        This should be called after the cog is generated.
        """
        # for cmd in self._external_commands:
        #     cmd.cog_name = self.__class__.__name__

        print("a")

    def retro_load_albums_to_redis(self) -> None:
        n = self.config.get("album_lists")
        for name, album_ids in n.items():
            config.sadd("img:albums:{}:ids".format(name), *album_ids)

    def _get_source_embed(self, image_link: str) -> discord.Embed:
        original_source = False
        source_link = self.REVERSE_SEARCH_PFX.format(requests.utils.quote(image_link))
        try:
            imgur_img = ImageList.imgur_client.get_image(image_link.split("/")[-1].split(".")[0])

            if imgur_img and imgur_img.description is not None:
                # For this to work, image desc should only be a url with the dot surrounded by spaces
                source_link = imgur_img.description.replace(" . ", ".")
                original_source = True

        except ImgurClientError:
            # Just fall through and make the source link run through tineye
            log.exception("Couldn't find imgur image")
            pass

        if not original_source:
            footer_msg = "[Source (Google Reverse Search)]({})"
        else:
            footer_msg = "[Original Source]({})"

        embed = discord.Embed(description=footer_msg.format(source_link))
        embed.set_image(url=image_link)

        # embed.set_footer(text=footer_msg.format(source_link))

        return embed

    async def process_command(self, ctx: Context) -> None:
        """
        Automatically handle a basic image list. Take context as a kwarg so we can use it as a Command
        This may or may not work
        """
        if rate_limits.MemeCommand.check_rate_limit(ctx,
                                                    cooldown_group="image_list",
                                                    priority_blacklist=[319309336029560834]):  # #mature_chat

            if random.random() < 0.0005:
                await ctx.send("https://i.imgur.com/AYoDloF.jpg")  # LUL
            else:
                obj = discord.utils.get(self.list_objs, name=ctx.command.name)
                blacklist = self.get_blacklist(ctx.command.name)
                await ctx.send(embed=self._get_source_embed(obj.get_image(blacklist)))

    async def add(
            self, name: str, ctx: Context, url: str,
            whitelist: List[int] = None, target_album_id: str = None
    ) -> None:
        obj = discord.utils.get(self.list_objs, name=name)

        # Try to remove it, but fail silently if it's NoneType (meaning we might have passed in an embed)
        try:
            url = url.strip("<>")
        except AttributeError:
            pass

        if url is None:
            if ctx.message.attachments:
                url = ctx.message.attachments[0].url
                if url.endswith(":large"):
                    url = url[:-6]
                elif url.endswith("large"):  # Twitter images suck
                    url = url[:-5]
            else:
                raise commands.MissingRequiredArgument("url")
        elif url == "^":
            async for msg in ctx.message.channel.history(limit=1, before=ctx.message):
                try:
                    url = msg.attachments[0].url
                except IndexError:
                    url = check_urls(msg.clean_content)
                    if not url:
                        raise commands.BadArgument("Previous message contains no actionable data.")

        await obj.add_to_list(ctx, url, whitelist, target_album_id)

    async def update_cache(self) -> None:
        """
        Update all cache files.
        Must be called as a task, otherwise it blocks the event loop.
        """
        # Could use a lock here but the feedback is probably more valuable
        if not self._cache_updating:
            self._cache_updating = True
            for image_list in self.list_objs:
                log.debug("Updating cache entry for {}.".format(image_list.name))
                await image_list.to_cache()  # Write to the cache
                await asyncio.sleep(3)  # wait for 2s to write the next one to cache so we don't clog the event loop
            log.info("Image list cache updated.")
            self._cache_updating = False
        else:
            log.warning("Cache updating, please wait.")

    @checks.sudo()
    @commands.command()
    async def write_datafiles_to_json(self, ctx: Context) -> None:
        """Manual command to initialize the datafile"""
        await self.update_cache()
        await ctx.send("\N{OK HAND SIGN}")

    @checks.sudo()
    @commands.command(aliases=["add_album"])
    async def add_image_list(
            self, ctx: Context, list_name: str, list_id: str
    ) -> None:
        """Add an image list for a command."""
        command_exists = True
        if not config.exists("img:albums:{}:ids".format(list_name)):
            command_exists = False
        config.sadd("img:albums:{}:ids".format(list_name), list_id)
        if not command_exists:
            self.list_objs.append(ImageList(list_name, [list_id]))
            self.create_new_command(list_name)
        else:
            obj = discord.utils.get(self.list_objs, name=list_name)
            if obj is None:
                obj = ImageList(list_name, [list_id])
            else:
                obj.images.append(list_id)
            obj.save_to_cache()

        await ctx.send("Image list added to datafile successfully.")
        if not command_exists:
            await ctx.send("**Command new to DB, may need to be added or may be incorrect.**")

    @checks.sudo()
    @commands.command()
    async def remove_album(
            self, ctx: Context, command_name: str, album_id: str
    ) -> None:
        """Remove an album from an image list command"""
        obj = discord.utils.get(self.list_objs, name=command_name)

        if obj is not None:
            self.list_objs.remove(obj)
            try:
                new_obj = await obj.remove_album(album_id)
            except ResponseError:
                await ctx.send("Album not part of command.")
                return
            else:
                self.list_objs.append(new_obj)
                await ctx.send("Album removed")

    @commands.command()
    async def sauce(self, ctx, previous: int = 1):
        """
        Get a link to the source of a picture posted by Porygon2.
        Will only search back through the past 100 messages at most.

        :param previous: Optional value for the number of pory posts to search back through.
            Internally maxed at 10.
        """

        previous = min(previous, 10)  # cap at 10
        # TODO Add note to the user that their search was capped at 10

        own_posts_seen = 0

        source_link = ""
        target_msg = None

        reverse_search_pfx = "https://www.google.com/searchbyimage?image_url={}"

        # Run back through the channel history and find up to previous
        async for message in ctx.message.channel.history(limit=100):
            if message.author.id == self.bot.user.id:
                own_posts_seen += 1
                target_msg = message
                if own_posts_seen == previous:
                    # Pull out the image ID
                    match = re.match("https?://i\.imgur\.com/(\w+)", message.content)

                    # Require that the found message is just an imgur url.
                    if match:
                        try:
                            # If our image comes from imgur, then it might have come from an image with a desc
                            imgur_img = ImageList.imgur_client.get_image(match.group(1))

                            if imgur_img and imgur_img.description is not None:
                                # For this to work, image desc should only be a url with the dot surrounded by spaces
                                source_link = imgur_img.description.replace(" . ", ".")
                                break

                        except ImgurClientError:
                            # Just fall through and make the source link run through tineye
                            pass
                    else:
                        await ctx.send("The message found was not an image command.")
                        return

                    # Generate Google image reverse search and jump out
                    reverse_link = reverse_search_pfx.format(requests.utils.quote(message.content))
                    source_link = "No direct source found.\n[Google Reverse Search Link]({})".format(reverse_link)
                    break

                elif own_posts_seen > previous:
                    await ctx.send("Could not find the image you specified.")
                    return

        embed = discord.Embed(title="Image source results",
                              description=source_link)
        embed.set_image(url=target_msg.content)

        await ctx.send(embed=embed)

    @checks.not_in_oaks_lab()
    @commands.command()
    async def nonya(self, ctx: Context) -> None:
        if not isinstance(ctx.channel, discord.DMChannel) and ctx.guild.id == 111504456838819840:
            return
        if rate_limits.MemeCommand.check_rate_limit(ctx,
                                                    cooldown_group="image_list",
                                                    priority_blacklist=[278043765082423296]):
            # Little easter egg
            if random.random() < .005:  # 0.5% chance of it happening
                await ctx.send("kanto….hahahahaha idiot braixen and fox smell so bad..wow i can smell it. "
                               "REMOVE BRAIXEN FROM THE PREMISES. you will get caught. kanto+johto+hoenn+alola=kill"
                               " kalos…you will war/ ash alive in kanto, ash making gym of kanto . fast team ash"
                               " kanto. we are rich and have nuggets now hahahaha ha because of ash… you are ppoor"
                               " stink fox… you live in a hovel hahahaha, you live in a yurt\n ash alive numbr one"
                               " 1 in kanto ….fuck the kalos ,..FUCKk ashol braixens no good i spit﻿ in the mouth"
                               " eye of ur flag and region. ash aliv and real strong wizard kill all the braixen"
                               " farm aminal with rap magic now we the katno rule .ape of the zoo champion diantha"
                               " fukc the great satan and lay egg this egg hatch and braixen wa;s born. stupid baby"
                               " form the eggn give bak our clay we will crush u lik a skull of pig. hoenn greattst"
                               " region")
            else:
                obj = discord.utils.get(self.list_objs, name="nonya")
                await ctx.send(embed=self._get_source_embed(obj.get_image(self.get_blacklist("nonya"))))

    @commands.command(aliases=["shep"])
    async def loreal(self, ctx: Context) -> None:
        await self.process_command(ctx)

    @commands.command(aliases=["myau"])
    async def espurr(self, ctx: Context) -> None:
        await self.process_command(ctx)

    @commands.command()
    async def pmdnd(self, ctx: Context) -> None:
        if ctx.message.guild.id in [274060630170927114,
                                    283101596806676481,
                                    239125949122215952,
                                    344285545742204940]:
            await self.process_command(ctx)

    @commands.command()
    async def backstory(self, ctx: Context) -> None:
        if not isinstance(ctx.message.channel, discord.DMChannel) and ctx.message.guild.id in [283101596806676481,
                                                                                               239125949122215952]:
            await self.process_command(ctx)

    @commands.command(aliases=["wish"])
    async def jirachi(self, ctx: Context) -> None:
        await self.process_command(ctx)

    @commands.command(hidden=True)
    async def esparoo(self, ctx: Context) -> None:
        if not isinstance(ctx.message.channel, discord.DMChannel) and ctx.message.guild.id in [283101596806676481]:
            await self.process_command(ctx)

    @commands.command()
    async def espy(self, ctx: Context) -> None:
        if not isinstance(ctx.message.channel, discord.DMChannel) and ctx.message.guild.id in [283101596806676481]:
            await self.process_command(ctx)

    @checks.in_cj()
    @commands.command()
    async def cursejerk(self, ctx: Context) -> None:
        await self.process_command(ctx)

    @checks.in_mez_server()
    @commands.command()
    async def mez(self, ctx: Context) -> None:
        await self.process_command(ctx)

    @checks.in_mez_server()
    @commands.command()
    async def furriend(self, ctx: Context) -> None:
        await self.process_command(ctx)

    # Adding commands

    @commands.command(hidden=True)
    async def addfug(self, ctx: Context, url: str = None) -> None:
        await self.add("fug", ctx, url, [125788490007838720, 78716152653553664])

    @commands.command(hidden=True)
    async def addnonya(self, ctx: Context, url: str = None) -> None:
        await self.add("nonya", ctx, url)

    @commands.command(hidden=True)
    async def addloss(self, ctx: Context, url: str = None) -> None:
        await self.add("loss", ctx, url, [118599124156284929, 78716152653553664, 122661718974398468])

    @commands.command(hidden=True)
    async def addloreal(self, ctx: Context, url: str = None) -> None:
        await self.add("loreal", ctx, url, [98245271313481728, 114994340320903175])

    @commands.command(hidden=True)
    async def addmenace(self, ctx: Context, url: str = None) -> None:
        await self.add("salesmenace", ctx, url, [184516140872105984])

    @commands.command(hidden=True)
    async def addluc(self, ctx: Context, url: str = None) -> None:
        await self.add("luc", ctx, url, [78716152653553664])

    @commands.command(hidden=True)
    async def adddelet(self, ctx: Context, url: str = None) -> None:
        await self.add("delet", ctx, url, [78716152653553664], target_album_id="11UlN")

    @commands.command(hidden=True)
    async def addfurriend(self, ctx: Context, url: str = None) -> None:
        await self.add("furriend", ctx, url, [78716152653553664, 170969550332887040])

    @checks.sudo()
    @commands.command()
    async def blacklist_img(self, ctx: Context, command_name: str, image_url: str):
        self.config.sadd("img:{}:blacklist".format(command_name), image_url)
        await ctx.send("Image has been blacklisted for command {}".format(command_name))

    @commands.Cog.listener()
    async def on_timer_update(self, secs: int) -> None:
        if secs % 21600 == 0 and secs != 0:  # 6 hrs of uptime
            self.bot.loop.create_task(self.update_cache())


def setup(bot: Bot):
    cog = ImageListCommands(bot)
    # cog.update_commands()
    bot.add_cog(cog)
