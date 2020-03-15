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
                    }
user:
    user_id:
        rmd:
            rescues:
                guild_id:
                    n_rescues: [int]
                    embarked: [user id of rescuee]
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
from .utils.rate_limits import MemeCommand
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


hex_out = """
    {}
    {}{}
"""


class RMD(commands.Cog):

    # RESCUE_CHANNEL_ID = 117861475569106949
    # REAL VALUES
    # BULLETIN_BOARD_ID = 687364910530691074
    # GUILD_ID = 117485575237402630

    # FAKE VALUES
    BULLETIN_BOARD_ID = 198526174735892480
    GUILD_ID = 78716585996455936

    RESCUE_TTL_SECONDS = 604800  # 7 days in seconds, time until rescues SD
    RESCUES_EXPIRE = False

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self._guild = bot.get_guild(self.GUILD_ID)
        # self._rescue_channel = bot.get_channel(self.RESCUE_CHANNEL_ID)

    @property
    def emoji_guild(self) -> discord.Guild:
        return self.bot.get_guild(78716585996455936)

    @property
    def open_mail_emoji(self) -> discord.Emoji:
        return self.bot.get_emoji(688775724722946176)

    @property
    def closed_mail_emoji(self) -> discord.Emoji:
        return self.bot.get_emoji(688775725003702281)

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

    @commands.command()
    async def screenshot(self, ctx):
        """Guide on screenshotting rescue QR codes for PSMD."""
        await ctx.send("https://www.reddit.com/r/MysteryDungeon/comments/3ts6mm/how_to_take_a_screenshot_of"
                       "_rescue_mail_because/")

    @commands.command(hidden=True, pass_context=True, enabled=False)
    async def reshcycle(self, ctx):
        if MemeCommand.check_rate_limit(ctx):
            await ctx.send("http://i.imgur.com/1tgZCIs.png")

    @commands.command(hidden=True, pass_context=True)
    async def levels(self, ctx):
        if MemeCommand.check_rate_limit(ctx):
            await ctx.send("http://i.imgur.com/tD009K4.png")

    @commands.command(hidden=True, aliases=["wm"])
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

    # @checks.r_md()
    @commands.group()
    async def rescue(self, ctx: Context):
        pass

    @rescue.command()
    async def init(self, ctx: Context):
        """
        Set up the guild for dealing with rescues.
        """

    def _create_rescue_request(self, guild_id: Union[int, str], user_id: str, message_link: str):
        # TODO Verify message url is actually a discord url
        guild_key = "guild:{}:rmd:rescues".format(guild_id)

        if self.config.exists("{}:requests:{}".format(guild_key, user_id)):
            raise RuntimeError("You already have an active rescue.")
        else:
            new_rescue = {
                "created": time.time(),
                "times_bumped": 0,
                "times_extended": 0,
                "message_link": message_link
            }

            rescue_key = "{}:requests:{}".format(guild_key, user_id)
            self.config.hmset(rescue_key, new_rescue)
            self.config.expire(rescue_key, time=self.RESCUE_TTL_SECONDS)
            self.config.sadd("{}:active_request_ids".format(guild_key), user_id)

    @rescue.command()
    async def respond(self, ctx: Context, user: discord.Member):
        """
        Respond to an active rescue request. Will only work if the job is not yet claimed by another user, or if you
        have not currently claimed a job yourself.
        """

        # First, check that the request that the user is responding to exists

        # If it does, check that the user is not currently on a rescue and that the job is open.

        guild_key = "guild:{}:rmd:rescues".format(ctx.message.guild.id)
        user_key = "user:{}:rmd:rescues:{}".format(ctx.message.author.id, ctx.message.guild.id)

        if self.config.exists("{}:requests:{}".format(guild_key, user.id)):
            rescue = self.config.hgetall("{}:requests:{}".format(guild_key, user.id))

            if rescue.get("taken_by"):
                await ctx.send("Someone else has already claimed this rescue.")
                return
        else:
            await ctx.send("This user hasn't requested a rescue!")
            return

        if self.config.sismember("{}:rescuers".format(guild_key), ctx.message.author.id):
            # User has rescued before, check if they're embarked on one
            if self.config.exists("{}:embarked".format(user_key)):  # auto-booleaned
                await ctx.send("You are already embarked on a rescue. You can only claim one rescue at a time.")
                return

            # fall through, they're good

        else:

            # user hasn't rescued before, we'll create their keys
            self.config.set("{}:n_rescues".format(user_key), 0)
            self.config.set("{}:embarked".format(user_key),
                            user.id,
                            ex=self.RESCUE_TTL_SECONDS if self.RESCUES_EXPIRE else None
                            )

            self.config.sadd("{}:rescuers".format(guild_key), ctx.message.author.id)

        self.config.hset("{}:requests:{}".format(guild_key, user.id), "taken_by", ctx.message.author.id)
        self.config.hset("{}:requests:{}".format(guild_key, user.id), "rescue_exp", time.time())

        await ctx.send("You've accepted this rescue request! Good luck!")

    @rescue.command()
    async def give_up(self, ctx: Context):
        """
        Give up on attempting a rescue, freeing it for other users to take on.
        Will automatically happen if the rescuee doesn't call !rescue extend when the rescue is about to expire.
        """
        user_key = "user:{}:rmd:rescues:{}".format(ctx.message.author.id, ctx.message.guild.id)
        guild_key = "guild:{}:rmd:rescues".format(ctx.message.guild.id)

        embarked_id = self.config.get("{}:embarked".format(user_key))
        if embarked_id is None:
            await ctx.send("You aren't currently embarked on a rescue.")

        else:
            rescuee_id = str(embarked_id)
            rescue_key = "{}:requests:{}".format(guild_key, rescuee_id)
            if self.config.exists(rescue_key):
                if self.config.hget(rescue_key, "taken_by") == str(ctx.message.author.id):
                    self.config.hdel(rescue_key, "taken_by")
                    self.config.hdel(rescue_key, "rescue_exp")
                    self.config.delete("{}:embarked".format(user_key))
                else:
                    await ctx.send("You aren't the one on this rescue!")
                    return

                await ctx.send("You've successfully removed yourself from this rescue.")
                return
            await ctx.send("The rescue doesn't seem to exist for some reason. Poke Luc.")

    @rescue.command(hidden=True)
    async def list(self, ctx: Context):
        """
        List all of the active rescues. This shouldn't be used! Check the pinned message instead.
        """
        await ctx.send(embed=self.create_rescue_list(ctx.message.guild.id))

    def create_rescue_list(self, guild_id: Union[str, int]) -> discord.Embed:
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

            new_output = "{} - [link]({} - {}".format(member.name, req["message_link"],
                                                      datetime.datetime.fromtimestamp(int(float(req["created"]))))
            if "taken_by" in req:
                output["in_progress"].append("{} ".format(str(self.closed_mail_emoji)) + new_output)
            else:
                output["incomplete"].append("{} ".format(str(self.open_mail_emoji)) + new_output)

        sorted_output = sorted(output["incomplete"]) + sorted(output["in_progress"])
        embed = discord.Embed(color=discord.Color.blue(), description="\n".join(sorted_output))
        embed.set_author(name="Current active rescues", icon_url=self.bot.user.avatar_url)
        embed.set_footer(text="Last updated {}".format(utils.get_timestamp()))

        return embed

    @rescue.command()
    async def extend(self, ctx: Context):
        """
        Extend the amount of time that the current rescuer has to complete your rescue. Can be called up to 5 times.
        """
        # TODO

    @rescue.command()
    async def bump(self, ctx: Context):
        """
        Refresh your rescue request. This can only be called up to 3 times.
        """
        # TODO

    def _delete_rescue_request(self, guild_id, user_id):
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
                self.config.delete("{}:embarked".format(user_key))
            self.config.srem("{}:active_request_ids".format(guild_key), user_id)
            self.config.delete(rescue_key)

    @rescue.command()
    async def cancel(self, ctx: Context):
        """
        Remove a rescue request that you have posted.
        """
        guild_key = "guild:{}:rmd:rescues".format(ctx.message.guild.id)

        rescue_key = "{}:requests:{}".format(guild_key, ctx.message.author.id)
        if self.config.exists(rescue_key):
            self._delete_rescue_request(ctx.message.guild.id, ctx.message.author.id)
            await ctx.send("Your rescue request has been cancelled.")
        else:
            await ctx.send("You don't seem to have an active rescue.")

    @rescue.command()
    async def mark_complete(self, ctx: Context):
        """
        Mark a rescue as having been completed. Should be called by the user who started the rescue.
        """
        guild_key = "guild:{}:rmd:rescues".format(ctx.message.guild.id)

        rescue_key = "{}:requests:{}".format(guild_key, ctx.message.author.id)
        if self.config.exists(rescue_key):
            completer = self.config.hget(rescue_key, "taken_by")
            user_key = "user:{}:rmd:rescues:{}".format(completer, ctx.message.guild.id)
            self.config.incr("{}:n_rescues".format(user_key), 1)
            self._delete_rescue_request(ctx.message.guild.id, ctx.message.author.id)
            await ctx.send("Your rescue request has been marked as complete!")
        else:
            await ctx.send("You don't seem to have an active rescue. Only the requester can call this command.")

    @checks.sudo()
    @rescue.command()
    async def a_remove(self, ctx: Context, user: discord.Member):
        """
        Admin command to remove a rescue request.
        """
        guild_key = "guild:{}:rmd:rescues".format(ctx.message.guild.id)

        rescue_key = "{}:requests:{}".format(guild_key, user.id)
        if self.config.exists(rescue_key):
            self._delete_rescue_request(ctx.message.guild.id, user.id)
            await ctx.send("Your rescue request has been cancelled.")
        else:
            await ctx.send("You don't seem to have an active rescue.")

    @checks.sudo()
    @rescue.command()
    async def a_giveup(self, ctx: Context, user: discord.Member):
        """
        Admin command to force a user to give up a rescue request
        """
        user_key = "user:{}:rmd:rescues:{}".format(user.id, ctx.message.guild.id)
        guild_key = "guild:{}:rmd:rescues".format(ctx.message.guild.id)

        embarked_id = self.config.get("{}:embarked".format(user_key))
        if embarked_id is None:
            await ctx.send("This user is not embarked on a rescue.")

        else:
            rescuee_id = str(embarked_id)
            rescue_key = "{}:requests:{}".format(guild_key, rescuee_id)
            if self.config.exists(rescue_key):
                if self.config.hget(rescue_key, "taken_by") == str(user.id):
                    self.config.hdel(rescue_key, "taken_by")
                    self.config.hdel(rescue_key, "rescue_exp")
                    self.config.delete("{}:embarked".format(user_key))
                else:
                    return

                await ctx.send("User removed from this rescue..")
                return
            await ctx.send("The rescue doesn't seem to exist for some reason. Poke Luc.")

    @checks.sudo()
    @rescue.command()
    async def a_list(self, ctx: Context):
        """
        Admin command to list out all users and their rescue statistics
        """
        # user_key = "user:{}:rmd:rescues:{}".format(user.id, ctx.message.guild.id)
        rank = []
        guild_key = "guild:{}:rmd:rescues".format(ctx.message.guild.id)

        for mem_id in self.config.smembers("{}:rescuers".format(guild_key)):
            mem = ctx.guild.get_member(mem_id)
            if mem is None:
                continue
            else:
                user_key = "user:{}:rmd:rescues:{}".format(mem_id, ctx.message.guild.id)
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

    @commands.Cog.listener()
    async def on_message(self, message):
        # If a user wants to summon pory for their rescue, they just have to ping pory in the
        # rescue channel and it'll try to scan the user's qr code.
        if message.channel.id == self.BULLETIN_BOARD_ID:
            if self.bot.user in message.mentions:
                try:
                    self._create_rescue_request(self.GUILD_ID, message.author.id,
                                                "https://discordapp.com/channels/{}/{}/{})"
                                                .format(message.guild.id, message.channel.id, message.id))
                except RuntimeError as e:
                    await message.channel.send(e, delete_after=5)
                else:
                    await message.channel.send("I've registered your new rescue.", delete_after=5)

    @commands.Cog.listener()
    async def on_timer_update(self, secs):
        if secs % 60 == 0:
            chan = self.bot.get_channel(self.BULLETIN_BOARD_ID)
            rescue_message_id = self.config.get("config:rmd:rescue_message_id")
            if rescue_message_id is None:
                new_msg = await chan.send(embed=self.create_rescue_list(self.GUILD_ID))
                await new_msg.pin()
                self.config.set("config:rmd:rescue_message_id", new_msg.id)
            else:
                try:
                    msg = await chan.fetch_message(int(rescue_message_id))
                except AttributeError:  # Usually pops up during debugging as chan is None
                    log.exception("Exception when reading channel")
                    return

                try:
                    await msg.edit(embed=self.create_rescue_list(self.GUILD_ID))
                except (discord.HTTPException, discord.Forbidden):
                    try:
                        await chan.delete_message(msg)
                    except (discord.HTTPException, discord.Forbidden):
                        await msg.unpin()
                    msg = await chan.send(embed=self.create_rescue_list(self.GUILD_ID))
                    await msg.pin()
                    self.config.set("config:rmd:rescue_message_id", msg.id)


def setup(bot):
    bot.add_cog(RMD(bot))
