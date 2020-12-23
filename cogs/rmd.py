"""
Basic commands for /r/MysteryDungeon

and some more complicated stuff now, I suppose

Rescuer database format:

guild:
    guild_id:
        rmd:
            rescues:
                rescuers:
                    [set of tracked rescuer user IDs for the guild]
                active_request_ids:
                    [set of user ids with active requests]
                active_rescuers:
                requests:
                    user_id: {
                        created: [timestamp]
                        times_bumped: [int]
                        times_extended: [int]
                        taken_by: [user_id]
                        rescue_exp: [datetime]
                        message_link
                        mark_for_delete: [int, boolean]
                        marked_ts: [int], inserted when mark_for_delete set
                    }

                blacklist:
                    [set of users barred from using commands]
user:
    user_id:
        rmd:
            rescues:
                guild_id:
                    n_rescues: [int]
                    embarked: set of User IDs who the user is currently rescuing
"""
import datetime
import time
import re
from typing import List, Union

import discord
import redis
from discord.ext import commands
from discord.ext.commands import Context

from cogs.utils.utils import download_image
from cogs.utils.rate_limits import MemeCommand
from cogs.server_logs import ServerLogs
from cogs.utils import rescue_codes, checks, utils
from PIL import Image
from io import BytesIO
import logging

log = logging.getLogger()

wondermail_format = """
Wondermail text format follows a simple format:
[number/letter][shape] (x30)
Shape can be f, h, w, d, s.
These represent Fire, Heart, Water, Diamond, and Star, respectively.
Number or letter can be 1-9 and P, M, D, X

For example, a 5 with a fire icon would be represented as
`5f`
    
    
and a sample rescue code might look like:

`1f 4d 5h 3d 7s 1f 4d 5h 3d 7s 1f 4d 5h 3d 7s 1f 4d 5h 3d 7s 1f 4d 5h 3d 7s 1f 4d 5h 3d 7s`

"""

expired_msg = """
Your rescue request has expired. This is due to it having been 3 days without any rescuer claiming it. 
If you are still seeking to be rescued, please reconsider reposting your request.
"""

non_ping_msg = """
Your message was removed because it does not seem to be a rescue request.
If it was meant to be one, make sure you've pinged <@{}> in your message.
Otherwise, please keep any rescue discussion to <#{}>.

Your original message content was:
{}
"""

pre_existing_rescue_msg = """
Your message was removed because you already have an active rescue request.

The original content of your message was:
{}
"""

art_gallery_msg = """
Your message has been removed because it was posted in <#{}> without including a link or attachment.
If you were adding text to your own submission, please edit your message rather than posting a new one.

Otherwise, please keep any art discussion to <#{}>.

Your original message content was:
{}
"""

hex_out = """
    {}
    {}{}
"""


def rmd_or_testing():
    def predicate(ctx: Context) -> bool:
        return (not isinstance(ctx.message.channel, discord.DMChannel) and
                (ctx.message.guild is not None and ctx.message.guild.id in [117485575237402630, 78716585996455936]))
    return commands.check(predicate)


def rmd_mod_check(ctx: Union[Context, discord.Message]):
    return checks.has_role(ctx, lambda r: r.id == 118940358473285632)


def is_rmd_mod():
    def predicate(ctx: Context) -> bool:
        return rmd_mod_check(ctx)
    return commands.check(predicate)


class ReactionContext(Context):
    """
    Stand-in class for context when a user triggers a command by reaction.

    Functions as an actual context object might, except it only tracks the values that we care about.
    channel becomes the DMChannel for the user who posted the reaction
    guild should be the guild that the reaction took place in
    author should be the user themselves
    """

    class DummyMessage:
        def __init__(self):
            self._state = None

    def __init__(self, user: discord.User, channel: discord.TextChannel, **attrs):
        super().__init__(prefix="!", message=self.DummyMessage(), **attrs)  # dummy out prefix
        self._guild = channel.guild
        self._channel = user
        self._author = user

    @property
    def author(self):
        return self._author

    @property
    def guild(self):
        return self._guild

    @property
    def channel(self):
        return self._channel

    async def send(self, content=None, *, tts=False, embed=None, file=None, files=None, delete_after=None, nonce=None):
        await self.channel.send(content=content, tts=tts, embed=embed, file=file, files=files,
                                delete_after=delete_after, nonce=nonce)


class RMD(commands.Cog):
    # RESCUE_CHANNEL_ID = 117861475569106949
    # REAL VALUES
    BULLETIN_BOARD_ID = 693159700371472444
    GUILD_ID = 117485575237402630
    DISCUSSION_CHANNEL_ID = 687364994072838194
    LOG_CHANNEL_ID = 693956476892348478

    ART_GALLERY_CHANNEL_ID = 502906125826654248
    ART_DISCUSSION_ID = 146102797711048704

    # FAKE VALUES
    # BULLETIN_BOARD_ID = 262993960035680256
    # GUILD_ID = 78716585996455936
    # LOG_CHANNEL_ID = 198526174735892480
    # DISCUSSION_CHANNEL_ID = 262993960035680256

    RESCUE_TTL_SECONDS = 259200
    RESCUES_EXPIRE = False
    MARK_FOR_DELETE_TTL = 10800  # 3 hours in seconds
    MAX_EMBARKED_RESCUES = 10

    ACCEPT_RESCUE_EMOJI_ID = 230509241163579392
    MARK_COMPLETE_EMOJI_ID = 692399443562987550
    # MARK_AOK_EMOJI_ID = 371517420642238465
    RELEASE_EMOJI_ID = 237769208275009536

    # ACCEPT_RESCUE_EMOJI_ID = 244535443272499201
    # MARK_COMPLETE_EMOJI_ID = 653814527691063336
    # MARK_AOK_EMOJI_ID = 371517420642238465
    # RELEASE_EMOJI_ID = 352265652968488962

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self._guild = bot.get_guild(self.GUILD_ID)
        self._reaction_cache = set()  # Cache used when removing reactions to ensure that we don't act on our own rxns
        # self._rescue_channel = bot.get_channel(self.RESCUE_CHANNEL_ID)

    @property
    def emoji_guild(self) -> discord.Guild:
        return self.bot.get_guild(78716585996455936)

    @property
    def open_mail_emoji(self) -> discord.Emoji:
        return self.bot.get_emoji(688775725003702281)

    @property
    def closed_mail_emoji(self) -> discord.Emoji:
        return self.bot.get_emoji(688775724722946176)

    @staticmethod
    def _get_id_from_url(url: str) -> int:
        return int(url.split("/")[-1].strip("()"))

    @staticmethod
    def _insert_emoji(codes: List[str], output_fp: Union[str, BytesIO]):
        job_board_image = Image.open("wonder_mail/job_board_transparent.png")

        codes = list(reversed(codes))  # Flip them around so we can treat it like a stack

        icon_size = 71  # Size to make each pasted sprite
        x_between_spaces = 101  # Amount to offset x for each space
        y_between_spaces = 130  # Same for y
        boundary_x_offset = 18  # Amount to shift x when we hit a larger boundary (5, 10)

        for i in range(2):
            x_offset_initial = y_offset_initial = 142
            for j in range(15):
                letter_img = Image.open("wonder_mail/{}.png".format(
                    codes.pop()
                ))

                letter_img = letter_img.resize((icon_size, icon_size), Image.BILINEAR)

                dropped_box = 4 < j < 10  # Use the integer value of this to determine whether or not to adjust for it
                drop_offset = 16  # Amount of pixels to drop the middle section

                if j % 5 == 0 and j != 0:
                    x_offset_initial += boundary_x_offset  # Add 6 every time we cross a boundary
                # Use the ternary in the following line to add an offset based on the dip for half
                x_offset = x_offset_initial + (x_between_spaces * j)
                y_offset = y_offset_initial + (y_between_spaces * i) + (dropped_box * drop_offset)

                job_board_image.paste(letter_img,
                                      (x_offset, y_offset,
                                       x_offset + icon_size, y_offset + icon_size),
                                      letter_img
                                      )

        job_board_image.save(output_fp, format="PNG")

        if isinstance(output_fp, BytesIO):
            output_fp.seek(0)

    @staticmethod
    def _parse_rescue_code(input_str: str) -> List[str]:

        input_str = input_str.lower()

        match = re.search("(?:([1-9pmdx][fdswh]) ?){30}", input_str)

        if not match:
            raise ValueError("Invalid wondermail format.")

        codes = match.group().split()

        return codes

    async def log(self, user: discord.User, action: str, target: Union[discord.User, discord.Member] = None):
        """Log rescue information to a given channel."""
        try:
            embed = discord.Embed(title="New bulletin board action")
            if user is not None:
                embed = ServerLogs.format_embed(embed, user)
            embed.add_field(name="Action", value=action)

            if target:
                embed.add_field(name="Target", value=target.mention)

            chan = self.bot.get_channel(self.LOG_CHANNEL_ID)

            await chan.send(embed=embed)
        except Exception:
            log.exception("Ignoring failure to log a bulletin-board message")

    @commands.command()
    async def faq(self, ctx):
        """Link to the /r/MysteryDungeon FAQ."""
        await ctx.send('Please check the FAQ! https://www.reddit.com/r/MysteryDungeon/wiki/psmdfaq')

    # Leaving this here for posterity because it was actually one of pory's first commands
    @commands.command(hidden=True)
    async def old_wm(self, ctx):
        """Link to wonder mail passwords in PSMD."""
        await ctx.send('http://www.cpokemon.com/2015/11/24/todas-las-contrasenas-wonder-mail-de-'
                       'pokemon-super-mystery-dungeon/')

    @checks.sudo()
    @commands.command(hidden=True, pass_context=True)
    async def reshcycle(self, ctx):
        if MemeCommand.check_rate_limit(ctx):
            await ctx.send("http://i.imgur.com/1tgZCIs.png")

    @commands.command(hidden=True, pass_context=True)
    async def levels(self, ctx):
        if MemeCommand.check_rate_limit(ctx):
            await ctx.send("http://i.imgur.com/tD009K4.png")

    @commands.command(aliases=["wm"])
    async def wondermail(self, ctx, *, code_or_ref: str):
        """
        Convert a message into a wondermail image that pory will post.
        code_or_ref: Either a wondermail code (see pins for formatting), or a ^ to wondermail the previous message.
        """

        if code_or_ref in ["help", "format"]:
            # Show a help message
            await ctx.send(wondermail_format)
            return

        elif code_or_ref == "^":
            # Check the last message for a wondermail code
            rescue_code = None  # Shutting up the linter
            async for msg in ctx.message.channel.history(limit=1, before=ctx.message):
                try:
                    rescue_code = self._parse_rescue_code(msg.content)
                except ValueError:
                    await ctx.send("The above message does not contain a valid wonder mail code.")
                    return

        else:
            # Parse the current message for a valid code.
            try:
                rescue_code = self._parse_rescue_code(code_or_ref)
            except ValueError:
                await ctx.send("Your wonder mail code does not seem to be formatted correctly. Call "
                               "`!wondermail format` for formatting help.")
                return
        async with ctx.typing():
            output_img = BytesIO()  # Saving as BytesIO means we never need to write to the filesystem

            self._insert_emoji(rescue_code, output_img)
        await ctx.send(file=discord.File(output_img, filename="wondermail.png"))

    @commands.command()
    async def read_mail(self, ctx, *, img_url: str = None):
        """
        Read in a QR code and convert it to a rescue code.
        region should be eu or na.
        """

        ret = await self._read_qr_code(ctx.message, ctx.channel, img_url)

        if ret:
            await ctx.send(ret)

    @commands.command(hidden=True)
    async def qr_to_bin(self, ctx, *, img_url: str = None):
        """
        Nasty hack of a command
        """

        if not img_url and ctx.message.attachments:
            img_url = ctx.message.attachments[0].url

        if not img_url:
            await ctx.channel.send("Image could not be found.")
            return

        async with ctx.channel.typing():
            # Resp is either holding None or (code, region)
            url = rescue_codes.convert_url(img_url)

            # Download image from url

            img_bytes = BytesIO()

            await download_image(url, img_bytes)

            # Open and compress the qr code here
            img = Image.open(img_bytes)
            img = img.resize((400, 400))
            img.save(img_bytes, format="PNG")
            img_bytes.seek(0)

            orig_bytes = await rescue_codes.get_qr_code_bytes(img_bytes)

        if not orig_bytes:
            await ctx.channel.send("Could not fetch a code from the image. Make sure the QR code is "
                                   "clearly in focus.")
            return

        fp = BytesIO()

        fp.write(orig_bytes)
        fp.seek(0)

        output_bytes = list(orig_bytes)
        output_ls = []
        i = 0
        while i < len(output_bytes):
            b = output_bytes[i]
            # if b == 0xC2:
            #     output_bytes.pop(i)
            #     continue
            if i % 16 == 0:
                output_ls.append("\n{:02x} |".format(i // 16))
            else:
                output_ls.append(" ")

            output_ls.append("{:02x}".format(int(b)))

            i += 1

        output_str = hex_out.format(
            " ".join(["{:02x}".format(i) for i in range(16)]),
            "-" * 48,
            "".join(output_ls)
        )

        await ctx.send("```\n{}```".format(output_str), file=discord.File(fp, filename="qr_bytes.bin"))

    @commands.command()
    async def convert_qr(self, ctx, *, img_url: str = None):
        if not img_url and ctx.message.attachments:
            img_url = ctx.message.attachments[0].url

        if not img_url:
            await ctx.channel.send("Image could not be found.")
            return

        async with ctx.channel.typing():
            # Resp is either holding None or (code, region)
            resp = await rescue_codes.convert_qr_code(img_url)

            if not resp:
                await ctx.channel.send("Could not fetch a code from the image. Make sure the QR code is "
                                       "clearly in focus.")
                return

            img, region = resp

            msg = "⬆️ {}\n\n⬇️ {} (converted)".format("EU" if region == "na" else "NA",
                                                      region.upper())

            await ctx.send(msg, file=discord.File(img, filename="qr.png"))

    async def _read_qr_code(self, message, channel, img_url: str = None):

        if not img_url and message.attachments:
            img_url = message.attachments[0].url

        if not img_url:
            await channel.send("Image could not be found.")
            return

        async with channel.typing():
            # Resp is either holding None or (code, region)
            resp = await rescue_codes.read_qr_code(img_url)

        if not resp:
            await channel.send("Could not fetch a code from the image. Make sure the QR code is "
                               "clearly in focus.")
            return

        else:
            code, region = resp

        if not re.match(r"[CFHJKMNPQRSTWXY0-9&\-#%+=@]{80}", code):
            await channel.send("The QR code returned an invalid rescue code.")
            return

        # pretty-print the code

        # This is kind of a weird way to go about it but I think it's
        # honestly better than just pulling the string apart haphazardly

        out_of_region_code = rescue_codes.convert_rescue_code(code)

        other_region = "EU" if region == "na" else "NA"

        output = "{} (detected region):\n{}\n{}:\n{}".format(
            region.upper(),
            self._pprint_rescue_code(code),
            other_region,
            self._pprint_rescue_code(out_of_region_code)
        )

        return output

    @commands.command()
    async def convert_wm(self, ctx, region: str, *, code: str):
        """
        Convert a psmd wonder mail code from one region to another.
        """
        code = code.replace(" ", "").replace("\n", "")
        out_of_region_code = rescue_codes.convert_rescue_code(code)

        if not re.match(r"[CFHJKMNPQRSTWXY0-9&\-#%+=@]{80}", code):
            await ctx.send("The input code seems to be invalid.")
            return

        other_region = "EU" if region == "na" else "NA"

        output = "{}:\n{}\n{}:\n{}".format(
            region.upper(),
            self._pprint_rescue_code(code),
            other_region,
            self._pprint_rescue_code(out_of_region_code)
        )

        await ctx.send(output)

    @staticmethod
    def _pprint_rescue_code(code: str) -> str:

        output = ["```\n"]

        for i, char in enumerate(code):

            cur_scan = i % 20
            if cur_scan == 6 or cur_scan == 12:
                output.append(char)
                output.append("  ")
            elif cur_scan == 0:
                output.append("\n" + char)
            else:
                output.append(char)
        output.append("```")

        return "".join(output)

    @rmd_or_testing()
    @commands.group()
    async def rescue(self, ctx: Context):
        """
        Use !help rescue for rescue commands.
        """
        pass

    async def check_blacklist(self, channel, guild_id, user_id):
        guild_key = "guild:{}:rmd:rescues".format(guild_id)
        if self.config.sismember("{}:blacklist".format(guild_key), user_id):
            await channel.send("You are blacklisted from using rescue commands.")
            return False
        else:
            return True

    @checks.sudo()
    @rescue.command(enabled=False)
    async def init(self, ctx: Context):
        """
        Set up the guild for dealing with rescues.
        """

    async def _create_rescue_request(self, guild_id: Union[int, str], user_id: str, message_link: str):
        """
        Standard method to create a new rescue request.
        If the user has a rescue request that's marked for deletion, delete the old one.

        TODO Add regex checks for game tags or checks for rescuer pings
        """
        guild_key = "guild:{}:rmd:rescues".format(guild_id)
        rescue_key = "{}:requests:{}".format(guild_key, user_id)

        if self.config.exists(rescue_key):
            # if the message marked for delete, nuke it
            marked_for_del = self.config.hget(rescue_key, "mark_for_delete")
            if marked_for_del is None or not int(marked_for_del):
                raise RuntimeError("You already have an active rescue.")
            else:
                await self._delete_rescue_request(guild_id, user_id, True)

        new_rescue = {
            "created": time.time(),
            "times_bumped": 0,
            "times_extended": 0,
            "message_link": message_link,
            "mark_for_delete": 0
        }

        self.config.hmset(rescue_key, new_rescue)
        # self.config.expire(rescue_key, time=self.RESCUE_TTL_SECONDS)
        self.config.sadd("{}:active_request_ids".format(guild_key), user_id)

        await self.log(self.bot.get_user(int(user_id)), "Created rescue request")
        await self._update_bulletin_board()

    async def _respond(self, ctx: Context, user: discord.Member) -> bool:
        """
        Respond to a rescue request.
        :param ctx: Context from the original message. Represents the user who called this command.
        :param user: User who the command was called on; the user who made the rescue request
        :return:
        """
        # First, check that the request that the user is responding to exists

        # If it does, check that the user is not currently on a rescue and that the job is open.

        guild_key = "guild:{}:rmd:rescues".format(ctx.guild.id)
        user_key = "user:{}:rmd:rescues:{}".format(ctx.author.id, ctx.guild.id)

        if not await self.check_blacklist(ctx.channel, ctx.guild.id, ctx.author.id):
            return False

        if self.config.exists("{}:requests:{}".format(guild_key, user.id)):
            rescue = self.config.hgetall("{}:requests:{}".format(guild_key, user.id))

            if rescue.get("taken_by") is not None and rescue.get("taken_by") != str(ctx.author.id):
                await ctx.send("Someone else has already claimed this rescue.")
                return False
            elif rescue.get("taken_by") == str(ctx.author.id):
                await ctx.send("You've already accepted this rescue!")
                return True
        else:
            await ctx.send("This user hasn't requested a rescue!")
            return False

        if self.config.sismember("{}:rescuers".format(guild_key), ctx.author.id):
            # User has rescued before, check if they're embarked on one
            embarked = self.config.smembers("{}:embarked".format(user_key))
            if str(user.id) in embarked:
                await ctx.send("You're already embarked on this rescue.")
                return True
            # elif embarked is not None:
            #     await ctx.send("You are already embarked on a rescue. You can only claim one rescue at a time.")
            #     return False
            elif len(embarked) > self.MAX_EMBARKED_RESCUES:
                await ctx.send("You are already embarked on the maximum number of rescues ({})."
                               "".format(self.MAX_EMBARKED_RESCUES))
                return False

            # fall through, they're good

        else:

            # user hasn't rescued before, we'll create their keys
            self.config.set("{}:n_rescues".format(user_key), 0)
            self.config.sadd("{}:rescuers".format(guild_key), ctx.author.id)

        self.config.sadd("{}:embarked".format(user_key),
                         user.id,
                         # ex=self.RESCUE_TTL_SECONDS if self.RESCUES_EXPIRE else None
                         )

        self.config.hset("{}:requests:{}".format(guild_key, user.id), "taken_by", ctx.author.id)
        self.config.hset("{}:requests:{}".format(guild_key, user.id), "rescue_exp", time.time())
        await ctx.send("You've accepted this rescue request! Good luck!")
        await self._update_bulletin_board()
        await self.log(ctx.author,
                       "Accepted a rescue request", target=user)
        return True

    @rescue.command(aliases=["accept", "claim", "take"])
    async def respond(self, ctx: Context, user: discord.Member):
        """
        Respond to an active rescue request. Will only work if the job is not yet claimed by another user, or if you
        have not currently claimed a job yourself.
        """

        await self._respond(ctx, user)

    async def _give_up(self, ctx: Context, user_id: int) -> bool:
        user_key = "user:{}:rmd:rescues:{}".format(ctx.author.id, ctx.guild.id)
        guild_key = "guild:{}:rmd:rescues".format(ctx.guild.id)

        if not await self.check_blacklist(ctx.channel, ctx.guild.id, ctx.author.id):
            return False

        embarked = self.config.smembers("{}:embarked".format(user_key))
        if not embarked:
            await ctx.send("You aren't currently embarked on a rescue.")
            return False
        elif str(user_id) not in embarked:
            await ctx.send("You aren't embarked on this rescue.")
            return False

        else:
            rescuee_id = user_id
            rescue_key = "{}:requests:{}".format(guild_key, rescuee_id)
            if self.config.exists(rescue_key):
                if self.config.hget(rescue_key, "marked_ts"):
                    await ctx.send("You can't give up on a completed rescue request.")
                    return False
                elif self.config.hget(rescue_key, "taken_by") == str(ctx.author.id):
                    self.config.hdel(rescue_key, "taken_by")
                    self.config.hdel(rescue_key, "rescue_exp")
                    self.config.srem("{}:embarked".format(user_key), user_id)
                else:
                    await ctx.send("You aren't the one on this rescue!")
                    return False

                await ctx.send("You've successfully removed yourself from this rescue.")
                await self._update_bulletin_board()
                await self.log(ctx.author, "Gave up on a rescue")
                return True
            await ctx.send("The rescue doesn't seem to exist for some reason. Poke Luc.")

    @rescue.command()
    async def give_up(self, ctx: Context, user: discord.Member):
        """
        Give up on attempting a rescue, freeing it for other users to take on.
        Will automatically happen if the rescuee doesn't call !rescue extend when the rescue is about to expire.
        """
        await self._give_up(ctx, user.id)

    @rescue.command(hidden=True)
    async def list(self, ctx: Context):
        """
        List all of the active rescues. This shouldn't be used! Check the pinned message instead.
        """
        if not await self.check_blacklist(ctx.channel, ctx.guild.id, ctx.author.id):
            return

        await ctx.send(embed=await self.create_rescue_list(ctx.guild.id))

    async def create_rescue_list(self, guild_id: Union[str, int]) -> discord.Embed:
        output = {
            "incomplete": [],
            "in_progress": []
        }
        guild_key = "guild:{}:rmd:rescues".format(guild_id)

        guild = self.bot.get_guild(int(guild_id))

        active_requests = self.config.smembers("{}:active_request_ids".format(guild_key))

        for mem_id in active_requests:
            try:
                req = self.config.hgetall("{}:requests:{}".format(guild_key, mem_id))
            except redis.RedisError:
                self.config.srem("{}:active_request_ids".format(guild_key), mem_id)  # Key probs expired
                continue
            member = guild.get_member(int(mem_id))

            if not member:
                try:
                    member = await guild.fetch_member(mem_id)
                except discord.NotFound:
                    # If we can't find the user at all, we have to do something.
                    await self._delete_rescue_request(guild_id, mem_id, True)
                    await self.log(self.bot.user, "Removed a request from user with ID {} due to"
                                                  "apparently not being in server?".format(mem_id))
                    continue

            # Check to see if our current item is marked for deletion.
            # if it is, we'll ignore it on the list
            # also, if its time has expired, we'll delete it.

            rescue_created = float(req.get("created", time.time()))

            marked_for_deletion = int(req.get("mark_for_delete", 0))

            time_left = time.time() - rescue_created

            if marked_for_deletion:

                ts = datetime.datetime.fromtimestamp(float(req["marked_ts"]))
                td = datetime.datetime.now() - ts

                if td.total_seconds() > self.MARK_FOR_DELETE_TTL:
                    await self._delete_rescue_request(guild_id, mem_id, True)

                continue

            elif time_left > self.RESCUE_TTL_SECONDS:

                await member.send(expired_msg)
                await self._delete_rescue_request(guild_id, mem_id, True)
                continue

            # We also want to check to see if the message has been deleted or not.
            # If the message no longer exists, try to delete it.
            # TODO This is a little spurious here and may be better moved elsewhere

            try:
                chan = self.bot.get_channel(self.BULLETIN_BOARD_ID)
                await chan.fetch_message(self._get_id_from_url(req["message_link"]))
            except discord.NotFound:
                await self._delete_rescue_request(guild_id, mem_id, False)
                continue

            dt = datetime.datetime.fromtimestamp(float(req["created"]))

            tdelta = datetime.datetime.now() - dt

            td_secs = int(tdelta.total_seconds())

            # Create a nice message

            if tdelta.days >= 1:
                time_msg = "{} day{} ago".format(tdelta.days, "s" if tdelta.days != 1 else "")
            elif td_secs >= 3600:
                time_msg = "{} hour{} ago".format(td_secs // 3600, "s" if td_secs // 3600 != 1 else "")
            elif td_secs >= 60:
                time_msg = "{} minute{} ago".format(td_secs // 60, "s" if td_secs // 60 != 1 else "")
            else:
                time_msg = "{} second{} ago".format(td_secs, "s" if td_secs != 1 else "")

            new_output = "{} - [link]({} - {}".format(member.name, req["message_link"],
                                                      time_msg)
            if "taken_by" in req:
                output_str = "{} ".format(str(self.closed_mail_emoji)) + new_output
                taker = guild.get_member(int(req["taken_by"]))
                output_str = output_str + " - **claimed by {}**".format(taker)
                output["in_progress"].append((tdelta, output_str))

            else:
                output["incomplete"].append((tdelta, "{} ".format(str(self.open_mail_emoji)) + new_output))

        sorted_output_ts = list(reversed(sorted(output["incomplete"]))) + list(reversed(sorted(output["in_progress"])))
        sorted_output = [i[1] for i in sorted_output_ts]

        # Jam them all into an embed
        # The description has a text limit, so we'll just try to fit it across multiple fields
        # We can also only have up to 1024 characters per rescue list item

        embed = discord.Embed(color=discord.Color.gold())
        embed.set_author(name="Current active rescues", icon_url=self.bot.user.avatar_url)
        embed.set_footer(text="Need help with rescue commands? "
                              "Call !help rescue.\nLast updated {}.".format(utils.get_timestamp()))

        cur_embed_field = []
        total_len = 5800
        cur_embed_len = 0
        n_embed_fields = 1

        # while cur_embed_len < total_len:

        if len(sorted_output) == 0:
            # No rescue requests
            embed.add_field(name="1", value="No rescue requests currently exist!")
            return embed

        for text in sorted_output:

            if len(text) + cur_embed_len > total_len:
                embed.add_field(name="Some more recent requests omitted.", value="")
                return embed

            if len(text) + cur_embed_len > 960:
                embed.add_field(name=str(n_embed_fields), value="\n".join(cur_embed_field), inline=True)
                cur_embed_field = []
                cur_embed_field.append(text)
                cur_embed_len = 0
                n_embed_fields += 1
            else:
                cur_embed_field.append(text)
            cur_embed_len += len(text)

        else:
            embed.add_field(name=str(n_embed_fields), value="\n".join(cur_embed_field), inline=True)

        return embed

    @rescue.command(enabled=False)
    async def extend(self, ctx: Context):
        """
        Extend the amount of time that the current rescuer has to complete your rescue. Can be called up to 5 times.
        """
        # TODO

    @rescue.command(enabled=False)
    async def bump(self, ctx: Context):
        """
        Refresh your rescue request. This can only be called up to 3 times.
        Doing so will remove the active rescuer, so be careful using it!
        """

    async def _release(self, ctx: Context):
        if not await self.check_blacklist(ctx.channel, ctx.guild.id, ctx.author.id):
            return False

        guild_key = "guild:{}:rmd:rescues".format(ctx.guild.id)
        rescue_key = "{}:requests:{}".format(guild_key, ctx.author.id)

        # embarked = self.config.smembers("{}:embarked".format(user_key))

        if self.config.exists(rescue_key):
            taken_by_id = self.config.hget(rescue_key, "taken_by")
            if not taken_by_id:
                await ctx.send("You don't have a rescuer on your request.")
                return False

            # Clean up all necessary business
            rescuee_id = str(taken_by_id)
            user_key = "user:{}:rmd:rescues:{}".format(taken_by_id, ctx.guild.id)
            rescue_key = "{}:requests:{}".format(guild_key, rescuee_id)
            # Remove data from the rescue
            self.config.hdel(rescue_key, "taken_by")
            self.config.hdel(rescue_key, "rescue_exp")
            # And ensure the rescuer is cleaned up as well
            self.config.srem("{}:embarked".format(user_key), ctx.author.id)
            await ctx.send("You've successfully released the active rescuer from your request.")
            await self.log(ctx.author, "Released rescuers from their request.")
            await self._update_bulletin_board()
            return True
        else:
            await ctx.send("You don't have an active rescue.")
            return False

    @rescue.command()
    async def release(self, ctx: Context):
        """
        Release the current rescuer from your rescue request.
        """
        await self._release(ctx)

    async def _delete_rescue_request(self, guild_id, user_id, delete_message: bool = False):
        """
        Formalized method to delete a rescue request.
        :param guild_id: guild ID the rescue is tracked in
        :param user_id: user who created the rescue request
        """
        guild_key = "guild:{}:rmd:rescues".format(guild_id)
        rescue_key = "{}:requests:{}".format(guild_key, user_id)
        if self.config.exists(rescue_key):
            embarked_user_id = self.config.hget(rescue_key, "taken_by")
            if embarked_user_id is not None:
                # Clear user specific details so the user doesn't get stuck
                user_key = "user:{}:rmd:rescues:{}".format(embarked_user_id, guild_id)
                self.config.srem("{}:embarked".format(user_key), user_id)

            if delete_message:
                message_url = self.config.hget(rescue_key, "message_link")
                message_id = self._get_id_from_url(message_url)
                rescue_chan = self.bot.get_channel(self.BULLETIN_BOARD_ID)
                try:
                    rescue_msg = await rescue_chan.fetch_message(message_id)
                    await rescue_msg.delete()
                except discord.ClientException:
                    log.exception("Couldn't delete the message, do I have the perms I need?")
                except discord.NotFound:
                    log.exception("Couldn't find the message to delete. Removing rescue request.")

            self.config.srem("{}:active_request_ids".format(guild_key), user_id)
            self.config.delete(rescue_key)
            await self.log(self.bot.get_user(int(user_id)), "Had a rescue request deleted.")

    async def _cancel(self, ctx: Context) -> bool:
        if not await self.check_blacklist(ctx.channel, ctx.guild.id, ctx.author.id):
            return False

        guild_key = "guild:{}:rmd:rescues".format(ctx.guild.id)

        rescue_key = "{}:requests:{}".format(guild_key, ctx.author.id)

        if self.config.exists(rescue_key):
            await self._delete_rescue_request(ctx.guild.id, ctx.author.id, True)
            await ctx.send("Your rescue request has been cancelled.")
            await self.log(ctx.author, "Cancelled their rescue request.")
            return True
        else:
            await ctx.send("You don't seem to have an active rescue.")
            return False

    @rescue.command(aliases=["clear"])
    async def cancel(self, ctx: Context):
        """
        Remove a rescue request that you have posted.
        """
        await self._cancel(ctx)

    async def _mark_complete(self, ctx: Context) -> bool:
        if not await self.check_blacklist(ctx.channel, ctx.guild.id, ctx.author.id):
            return False

        guild_key = "guild:{}:rmd:rescues".format(ctx.guild.id)

        rescue_key = "{}:requests:{}".format(guild_key, ctx.author.id)
        if self.config.exists(rescue_key):
            completer = self.config.hget(rescue_key, "taken_by")
            user_key = "user:{}:rmd:rescues:{}".format(completer, ctx.guild.id)
            self.config.incr("{}:n_rescues".format(user_key), 1)
            await self._delete_rescue_request(ctx.guild.id, ctx.author.id, True)
            await ctx.send("Your rescue request has been marked as complete!")
            await self.log(ctx.author, "Marked their own rescue request as complete.")
            return True
        else:
            await ctx.send("You don't seem to have an active rescue. Only the requester can call this command.")

    @rescue.command()
    async def mark_complete(self, ctx: Context):
        """
        Mark a rescue as having been completed. Should be called by the user who started the rescue.
        """
        await self._mark_complete(ctx)

    async def _cancel_deletion_mark(self, guild: discord.Guild, user_id: Union[str, int]):
        """
        Cancel a message's marking for deletion.
        Can be triggered by a mod reacting with a checkmark.
        :param guild:
        :param user_id:
        """

    async def _mark_for_deletion(self, guild: discord.Guild, channel: discord.TextChannel, user_id: Union[str, int]):
        """
        Mark a request for deletion. The message will be marked with a sentinel emoji, and will be deleted shortly
        after.
        :param guild: guild to delete the message from
        :param user_id: creator of the rescue request.
        """

        guild_key = "guild:{}:rmd:rescues".format(guild.id)

        rescue_key = "{}:requests:{}".format(guild_key, user_id)
        if self.config.exists(rescue_key):
            self.config.hset(rescue_key, "mark_for_delete", 1)
            # pull the message ID, last item on the url
            link = self.config.hget(rescue_key, "message_link")
            self.config.hset(rescue_key, "marked_ts", int(time.time()))
            message_id = link.split("/")[-1].strip("()")
            msg = await channel.fetch_message(int(message_id))
            await msg.add_reaction("\N{CROSS MARK}")

    async def _aok(self, ctx: Context, user: discord.Member) -> bool:

        if not await self.check_blacklist(ctx.channel, ctx.guild.id, ctx.author.id):
            return False

        guild_key = "guild:{}:rmd:rescues".format(ctx.guild.id)

        rescue_key = "{}:requests:{}".format(guild_key, user.id)
        if self.config.exists(rescue_key):

            if self.config.hget(rescue_key, "marked_ts"):
                await ctx.send("You can't AOK a completed rescue.")
                return False

            completer = self.config.hget(rescue_key, "taken_by")
            if not completer or int(completer) != ctx.author.id:
                await ctx.send("You can't AOK a request you didn't take on!")
                return False
            # user_key = "user:{}:rmd:rescues:{}".format(completer, ctx.guild.id)
            # self.config.incr("{}:n_rescues".format(user_key), 1)
            # self._delete_rescue_request(ctx.guild.id, ctx.author.id)

            user_key = "user:{}:rmd:rescues:{}".format(ctx.author.id, ctx.guild.id)

            self.config.srem("{}:embarked".format(user_key), user.id)

            await self._mark_for_deletion(ctx.guild, self.bot.get_channel(self.BULLETIN_BOARD_ID), user.id)
            await ctx.send("The rescue has been marked as complete!")
            try:
                await user.send("Your rescue request has been completed by {}!".format(ctx.author))
            except discord.DiscordException:
                # Try and silently fail if we can't send the message.
                pass
            await self.log(ctx.author, "Completed a rescue request", target=user)
            return True
        else:
            await ctx.send("That user doesn't seem to have an active request.")
            return False

    @rescue.command()
    async def aok(self, ctx: Context, user: discord.Member):
        """
        Mark a rescue as having been completed. Should be called by the user who completed a rescue.
        Note that this does not instantly delete your request, but will mark it for deletion.
        If you try to make a new rescue, it will delete the one that's marked.
        A user marking an AOK will be instatly freed to perform another rescue.
        """
        await self._aok(ctx, user)

    @checks.sudo()
    @rescue.command()
    async def a_remove(self, ctx: Context, user: discord.Member):
        """
        Admin command to remove a rescue request.
        """
        guild_key = "guild:{}:rmd:rescues".format(ctx.guild.id)

        rescue_key = "{}:requests:{}".format(guild_key, user.id)
        if self.config.exists(rescue_key):
            await self._delete_rescue_request(ctx.guild.id, user.id)
            await ctx.send("This rescue request has been cancelled.")
        else:
            await ctx.send("You don't seem to have an active rescue.")

    @checks.sudo()
    @rescue.command()
    async def a_unmark(self, ctx: Context, user: discord.Member):
        """
        Unmark a user's rescue from deletion
        """
        guild_key = "guild:{}:rmd:rescues".format(ctx.guild.id)

        rescue_key = "{}:requests:{}".format(guild_key, user.id)
        if self.config.exists(rescue_key) and self.config.hget(rescue_key, "marked_ts"):
            self.config.hdel(rescue_key, "mark_for_delete")
            self.config.hdel(rescue_key, "marked_ts")
            # Pardon the mess
            message_id = self.config.hget(rescue_key, "message_link").split("/")[-1].strip("()")
            msg = await self.bot.get_channel(self.BULLETIN_BOARD_ID).fetch_message(int(message_id))
            await msg.remove_reaction("\N{CROSS MARK}")
            await self._cancel_deletion_mark(ctx.guild, user.id)
            await ctx.send("The request has been unmarked.")
        else:
            await ctx.send("That user doesn't seem to have an active rescue.")

    # @checks.sudo()
    # @rescue.command()
    # async def a_giveup(self, ctx: Context, user: discord.Member):
    #     """
    #     Admin command to force a user to give up a rescue request
    #     """
    #     user_key = "user:{}:rmd:rescues:{}".format(user.id, ctx.guild.id)
    #     guild_key = "guild:{}:rmd:rescues".format(ctx.guild.id)
    #
    #     embarked_id = self.config.get("{}:embarked".format(user_key))
    #     if embarked_id is None:
    #         await ctx.send("This user is not embarked on a rescue.")
    #
    #     else:
    #         rescuee_id = str(embarked_id)
    #         rescue_key = "{}:requests:{}".format(guild_key, rescuee_id)
    #         if self.config.exists(rescue_key):
    #             if self.config.hget(rescue_key, "taken_by") == str(user.id):
    #                 self.config.hdel(rescue_key, "taken_by")
    #                 self.config.hdel(rescue_key, "rescue_exp")
    #                 self.config.delete("{}:embarked".format(user_key))
    #             else:
    #                 return
    #
    #             await ctx.send("User removed from this rescue.")
    #             return
    #         await ctx.send("The rescue doesn't seem to exist for some reason. Poke Luc.")

    @checks.sudo()
    @rescue.command()
    async def a_list(self, ctx: Context):
        """
        Admin command to list out all users and their rescue statistics
        """
        # user_key = "user:{}:rmd:rescues:{}".format(user.id, ctx.guild.id)
        rank = []
        guild_key = "guild:{}:rmd:rescues".format(ctx.guild.id)

        for mem_id in self.config.smembers("{}:rescuers".format(guild_key)):
            mem = ctx.guild.get_member(mem_id)
            if mem is None:
                continue
            else:
                user_key = "user:{}:rmd:rescues:{}".format(mem_id, ctx.guild.id)
                user_score = self.config.get("{}:n_rescues".format(user_key))
                if user_score > 0:
                    rank.append((user_score, mem))

        rank = sorted(rank)  # Sort by score

        output = []

        i = 1

        for score, mem in rank:
            if i > 25:  # We can only take so many names
                break
            output.append("{}) {}: {} rescues".format(i, mem, score))
            i += 1

        emb = discord.Embed(description="\n".join(output), title="Rescue scores")
        await ctx.send(embed=emb)

    @checks.sudo()
    @rescue.command()
    async def blacklist(self, ctx: Context, user: discord.Member):
        """
        Admin command to blacklist a user from using the rescue commands. Functions as a toggle.
        """

        guild_key = "guild:{}:rmd:rescues".format(ctx.guild.id)
        blacklist_key = "{}:blacklist".format(guild_key)

        if self.config.sismember(blacklist_key, user.id):
            self.config.srem(blacklist_key, user.id)
            await ctx.send("User {} is now allowed to use rescue commands.".format(user))
        else:
            self.config.sadd(blacklist_key, user.id)
            await ctx.send("User {} has been blacklisted from rescue commands.".format(user))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # If a user wants to summon pory for their rescue, they just have to ping pory in the
        # rescue channel and it'll try to scan the user's qr code.
        if message.author.id == self.bot.user.id:
            return
        if message.channel.id == self.BULLETIN_BOARD_ID:
            if self.bot.user in message.mentions:
                if not await self.check_blacklist(message.channel, message.guild.id, message.author.id):
                    return
                try:
                    await self._create_rescue_request(self.GUILD_ID, message.author.id,
                                                      "https://discordapp.com/channels/{}/{}/{})"
                                                      .format(message.guild.id, message.channel.id, message.id))
                except RuntimeError as e:
                    await message.channel.send(e, delete_after=5)
                    await message.delete()
                    await message.author.send(pre_existing_rescue_msg.format(message.content))
                else:
                    await message.channel.send("I've registered your new rescue.", delete_after=5)

            else:
                # Prevent non-mods from posting non-request messages in the channel.
                if not rmd_mod_check(message):
                    try:
                        await message.author.send(non_ping_msg.format(self.bot.user.id,
                                                                      self.DISCUSSION_CHANNEL_ID,
                                                                      message.content))
                    finally:
                        # Ensure the message at least gets deleted
                        await message.delete()

        elif message.channel.id == self.ART_GALLERY_CHANNEL_ID:
            if not rmd_mod_check(message) and (not message.attachments and not utils.check_urls(message.content)):
                try:
                    await message.author.send(art_gallery_msg.format(self.ART_GALLERY_CHANNEL_ID,
                                                                     self.ART_DISCUSSION_ID,
                                                                     message.content))
                finally:
                    await message.delete()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """
        An alternate entry method for the commands is through reactions.
        Users can react to a rescue request with a given emoji to:
            - Mark it as tracked by Porygon2
            - Mark it as accepted
            - Mark it as taken

        Our procedure should be
            - Perform checks to see if we care about it
            - Run the operation
            - Add/remove a reaction as needed
        """

        if payload.user_id == self.bot.user.id or payload.channel_id != self.BULLETIN_BOARD_ID:
            return

        if payload.user_id in self._reaction_cache:
            self._reaction_cache.remove(payload.user_id)
            return

        # TODO Allow tracking to start from a message

        # Check that the message reacted to contains a rescue request

        chan = self.bot.get_channel(payload.channel_id)

        msg = await chan.fetch_message(payload.message_id)

        guild_key = "guild:{}:rmd:rescues".format(payload.guild_id)

        rescue_key = "{}:requests:{}".format(guild_key, msg.author.id)

        if not self.config.exists(rescue_key):
            # We could get into an emoji edit-war but that'll just rate limit us
            return

        req_url = self.config.hget(rescue_key, "message_link")

        req_id = self._get_id_from_url(req_url)

        member = chan.guild.get_member(payload.user_id)

        if not member:
            member = await chan.guild.fetch_member(payload.user_id)

        # if not member.dm_channel:
        #     await member.create_dm()

        if req_id != payload.message_id:
            await member.send("Please only react to active rescue requests.")
            await msg.remove_reaction(payload.emoji, member)
            self._reaction_cache.add(member.id)
            return

        fake_ctx = ReactionContext(member, chan)

        if payload.emoji.id == self.ACCEPT_RESCUE_EMOJI_ID:
            result = await self._respond(fake_ctx, msg.author)

            if result:  # Successfully accepted
                return
            else:
                await msg.remove_reaction(payload.emoji, member)

        elif payload.emoji.id == self.MARK_COMPLETE_EMOJI_ID:
            if member.id == msg.author.id:
                # Marking complete
                await self._mark_complete(fake_ctx)
                # This will delete the message so there's no need to worry
            else:
                result = await self._aok(fake_ctx, msg.author)
                if not result:
                    await msg.remove_reaction(payload.emoji, member)

        elif payload.emoji.id == self.RELEASE_EMOJI_ID:
            if member.id == msg.author.id:
                result = await self._release(fake_ctx)
                if result:
                    await msg.clear_reactions()
                else:
                    self._reaction_cache.add(member.id)
                    await msg.remove_reaction(payload.emoji, member)
            else:
                await fake_ctx.send("You can't release a message that isn't your own.")
                self._reaction_cache.add(member.id)
                await msg.remove_reaction(payload.emoji, member)
        else:
            self._reaction_cache.add(member.id)
            await msg.remove_reaction(payload.emoji, member)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        """
        Check a removed reaction to see if it impacts the channels that we're working with.
        """
        if payload.user_id == self.bot.user or payload.channel_id != self.BULLETIN_BOARD_ID:
            return

        if payload.user_id in self._reaction_cache:
            # Use a cache to ensure that we don't end up getting stuck in a cycle of adding/removing emoji
            self._reaction_cache.remove(payload.user_id)
            return

        chan = self.bot.get_channel(payload.channel_id)

        msg = await chan.fetch_message(payload.message_id)

        member = payload.member

        if not member:
            member = await chan.guild.fetch_member(payload.user_id)

        guild_key = "guild:{}:rmd:rescues".format(payload.guild_id)

        rescue_key = "{}:requests:{}".format(guild_key, msg.author.id)

        if not self.config.exists(rescue_key):
            # We could get into an emoji edit-war but that'll just rate limit us
            return

        req_url = self.config.hget(rescue_key, "message_link")

        req_id = self._get_id_from_url(req_url)

        if req_id != payload.message_id:
            return

        fake_ctx = ReactionContext(member, chan)

        if payload.emoji.id == self.ACCEPT_RESCUE_EMOJI_ID and \
                self.config.hget(rescue_key, "taken_by") == str(member.id):

            await self._give_up(fake_ctx, msg.author.id)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        """
        Check to see if the deleted message was one that we're tracking.
        """
        if message.channel.id == self.BULLETIN_BOARD_ID and message.author.id != self.bot.user.id:
            guild_key = "guild:{}:rmd:rescues".format(message.guild.id)

            rescue_key = "{}:requests:{}".format(guild_key, message.author.id)

            if self.config.exists(rescue_key):
                # Before we get too excited, let's make sure that it's the right message
                msg_id = int(self._get_id_from_url(self.config.hget(rescue_key, "message_link")))
                if msg_id == message.id:
                    await self._delete_rescue_request(message.guild.id, message.author.id, False)
                    await self.log(message.author, "Deleted their rescue request.")

    async def _update_bulletin_board(self):
        chan = self.bot.get_channel(self.BULLETIN_BOARD_ID)
        rescue_message_id = self.config.get("config:rmd:rescue_message_id")
        if rescue_message_id is None:
            new_msg = await chan.send(embed=await self.create_rescue_list(self.GUILD_ID))
            await new_msg.pin()
            self.config.set("config:rmd:rescue_message_id", new_msg.id)
        else:
            try:
                msg = await chan.fetch_message(int(rescue_message_id))
            except AttributeError:  # Usually pops up during debugging as chan is None
                log.exception("Exception when reading channel")
                return
            except discord.NotFound:
                new_msg = await chan.send(embed=await self.create_rescue_list(self.GUILD_ID))
                await new_msg.pin()
                self.config.set("config:rmd:rescue_message_id", new_msg.id)
                return

            try:
                await msg.edit(embed=await self.create_rescue_list(self.GUILD_ID))
            except (discord.HTTPException, discord.Forbidden):
                try:
                    await msg.delete(reason="Updating bulletin board")
                except (discord.HTTPException, discord.Forbidden):
                    await msg.unpin()
                msg = await chan.send(embed=await self.create_rescue_list(self.GUILD_ID))
                await msg.pin()
                self.config.set("config:rmd:rescue_message_id", msg.id)

    @commands.Cog.listener()
    async def on_timer_update(self, secs):
        if secs % 120 == 0:
            await self._update_bulletin_board()


def setup(bot):
    bot.add_cog(RMD(bot))
