import datetime
import glob
import random
import re
import os
import traceback

from os import path
from datetime import datetime, timedelta
from typing import Dict, Tuple, Union, Optional, List

import discord
from asyncio import sleep
from discord import Guild, Message, Role, Member, DMChannel
from discord.ext import commands
from discord.ext.commands import Context, Bot

from .utils import messages, checks, config, rate_limits, utils
from urllib.parse import urlencode


def num_emoji(num: int) -> str:
    return "{}⃣".format(num)


dice_pattern = re.compile(r"(\d*)d(\d+)(?:\+(\d+))?")


class Rollable:
    """
    Small type to allow for a few different inputs, and for the value to be created automatically
    as an argument
    """

    MAX_ROLLS = 30

    def __init__(self, argument: str) -> None:
        if argument == "rick":
            raise commands.BadArgument("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

        # Use regex to be smart about it
        match = re.search(dice_pattern, argument)

        if not match:
            raise commands.BadArgument("Invalid command format. [dice count]d<side count>[+<modifier>]")

        count = match.group(1)
        self.sides = max(int(match.group(2)), 1)
        modifier = match.group(3)

        if self.sides < 1:
            raise commands.BadArgument("Cannot roll a 0-sided die.")

        if not count or int(count) < 1:
            self.rolls = 1
        else:
            self.rolls = int(count)

        if not modifier:
            self.modifier = 0
        else:
            self.modifier = int(modifier)

    def cast_roll(self) -> List[int]:
        """
        Roll a dice based on the params stored in the object
        :return: List of all rolled values.
        """
        roll_output = []

        for roll in range(min(self.rolls, self.MAX_ROLLS)):  # Cap our roll count
            roll_output.append(random.randint(1, self.sides))
        return roll_output


class DHMSTimestamp:

    def __init__(self, argument: str) -> None:

        self.timestamp = str(argument)
        self.seconds = self.timestamp_to_seconds(argument)

        if not self.seconds:
            raise commands.BadArgument

    @staticmethod
    def timestamp_to_seconds(timestamp: str) -> Optional[int]:
        """Take in a time in _h_m_s format"""
        units = {
            "d": 86400,
            "h": 3600,
            "m": 60,
            "s": 1
        }
        seconds = 0
        match = re.findall("([0-9]+[smhd])", timestamp)  # Thanks to 3dshax server's former bot
        if match is None:
            return None
        for item in match:
            # The slicing here is to remove the unit letter.
            seconds += int(item[:-1]) * units[item[-1]]
        return seconds

    @staticmethod
    def seconds_to_timestamp(seconds: int) -> str:
        """Get a number of seconds and return a timestamp formatted in
        dhms format, excluding leading zero values."""
        days = seconds // 86400
        hours = (seconds // 3600) % 24
        mins = (seconds // 60) % 60
        secs = seconds % 60

        output = ""
        for num, period in enumerate([days, hours, mins, secs]):
            # Format the text so that it doesn't display zero values at the left
            if period > 0 or (output != "" and period == 0):
                # If the num is greater than zero or there are no values to the left
                output += str(period) + "dhms"[num]

        return output


class Countdown:
    """General use commands"""

    @staticmethod
    def date_diff_in_seconds(date1: datetime, date2: datetime) -> int:
        timedelta = date2 - date1
        return timedelta.days * 24 * 3600 + timedelta.seconds

    @staticmethod
    def _format_from_seconds(seconds: int) -> Tuple[int, int, int, int]:
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        return days, hours, minutes, seconds

    @staticmethod
    def seconds_remaining(timestamp: str) -> Union[float, None]:
        """
        Get timedelta string from a formatted timestamp.
        :return Amount of seconds remaining until the countdown, or None if the countdown has finished.
        """
        ending = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
        now = datetime.now()
        if ending < now:
            return None
        else:
            timedelta = ending - now
            return timedelta.total_seconds()

    @staticmethod
    def format_time_remaining(seconds: int) -> str:
        timedelta = Countdown._format_from_seconds(seconds)
        return "%d days, %d hours, %d minutes, %d seconds".format(timedelta)

    @staticmethod
    async def create_countdown(
            name: str, message: str, timestamp: str, ctx: Context
    ) -> Dict[str, Union[str, datetime, int, bool]]:
        """
        Save a countdown to the datafile
        :param name: Name of the countdown
        :param message: Message to be included in the countdown.
        :param timestamp: Time (since epoch) when the countdown ends
        :param ctx: Context object
        """
        # Check to make sure that the format matches
        try:
            datetime.datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            raise RuntimeError("Incorrect date format. Expected %Y-%m-%d %H:%M:%S.")

        return {
            "name": name,
            "message": message,
            "created": datetime.datetime.now(),
            "end": timestamp,  # End in unix time
            "channel_id": ctx.message.channel.id,
            "author_id": ctx.message.author.id,
            "completed": False
        }


class General(commands.Cog):
    """General commands"""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.countdowns = config.Config("countdowns.json")
        self.happenings = []
        self.boo_counter = 1
        self.config = self.bot.config

    @property
    def r_pkmn(self) -> Guild:
        return self.bot.get_guild(111504456838819840)

    @property
    def verified_role(self) -> Role:
        return discord.utils.get(self.r_pkmn.roles, id=349077573977899011)

    def _is_verified(self, ctx: Context) -> bool:
        if isinstance(ctx.message.channel, DMChannel):  # actually a user, meaning it's in DMs
            return True
        elif ctx.message.author.guild == self.r_pkmn:
            return self.verified_role in ctx.message.author.roles
        else:
            return self.config.get("user:{}:logs:enabled".format(ctx.message.author.id)) is True

    def _generate_among_us_msg(self, name: str):
        n_lines = 6
        max_width = 40 + len(name)
        space = "　"
        space_width = 4
        star_chance = 0.25
        stars = ["•", "。", ".", "ﾟ", "'", ","]
        spaceman = "ඞ"
        placed_spaceman = False
        output_lines = []

        # Pad with a random amount of characters
        #   but ensure that spaces are significantly more common

        # Randomly place the spaceman on lines 2 or three
        # It has to go somewhere, so we'll just pre-position it
        spaceman_col = random.randint(5, 35)
        spaceman_row = random.randint(1, 2)

        # Remind me why I told myself I'd make a text formatting command again?

        r = 0
        while r < n_lines:
            c = 0
            cur_line = []
            while c < max_width:
                if c >= spaceman_col and r == spaceman_row and not placed_spaceman:
                    cur_line.append(" ")
                    cur_line.append(spaceman)
                    c += 2
                    placed_spaceman = True
                elif r == 3 or r == 4:
                    if r == 3:
                        text_fmt = "{}{} was{} The Imposter. ".format(
                            " " * space_width,
                            name,
                            random.choice([" not", ""])
                        )
                        text_fmt = text_fmt.replace("%", "\\%")
                    else:
                        n_imposters = random.randint(1, 3)
                        text_fmt = "{}**{} Imposter{} remain{}. **".format(
                            " " * space_width,
                            n_imposters,
                            "s" if n_imposters != 1 else "",
                            "" if n_imposters != 1 else "s"

                        )

                    text_center = text_fmt.center(max_width, "%")
                    i = 0
                    while i < len(text_center):
                        ch = text_center[i]

                        # Check for escapes
                        if i < len(text_center) - 1 and ch == "\\" and text_center[i + 1] == "%":
                            cur_line.append("%")
                            i += 2
                        # make replacements
                        elif ch == "%":
                            if random.random() < star_chance:
                                cur_line.append(random.choice(stars))
                                i += 1
                            else:
                                cur_line.append(space)
                                i += space_width  # Spaces are much longer
                        else:
                            cur_line.append(ch)
                            i += 1

                    # Force the creation of a new line
                    break

                else:
                    if random.random() < star_chance:
                        cur_line.append(random.choice(stars))
                        c += 1
                    else:
                        cur_line.append(space)
                        c += 3  # Spaces are much longer

            output_lines.append("".join(cur_line))
            r += 1

        return "\n\n".join(output_lines)

    async def check_verification(self, ctx: Context) -> bool:
        verification = self._is_verified(ctx)
        if verification:
            return True
        elif not verification and ctx.message.guild == self.r_pkmn:
            await ctx.send('This command requires that you have the `Verified` role.')
            return False
        else:
            await ctx.message.author.send("This command requires that you allow Porygon2 to log your history by DMing "
                                          "Porygon2 `!allow_logging`.")
            return False

    @commands.command()
    async def among(self, ctx: Context, *, target: str = None) -> None:
        rate_limits.MemeCommand.check_rate_limit(ctx)
        if not target:
            target = getattr(ctx.author, "nick", ctx.author.name)
        response = self._generate_among_us_msg(target)

        await ctx.send(response)

    @commands.command()
    async def ping(self, ctx: Context) -> None:
        response = await ctx.send("Pong!")

        # Get a timedelta, then convert it to seconds
        dif = (datetime.utcnow() - response.created_at).total_seconds() * 1000

        await ctx.send("Response time: `{}ms`".format(dif))

    @commands.command()
    async def PING(self, ctx: Context):
        response = await ctx.send("**PONG**")
        # Get a timedelta, then convert it to seconds
        dif = (datetime.utcnow() - response.created_at).total_seconds() * 1000

        await ctx.send("Response time: `{}ms`".format(dif))

    @checks.not_rmd()
    @checks.not_pmdnd()
    @commands.command(aliases=["rolld", "r"])
    async def roll(self, ctx: Context, roll: Rollable) -> None:
        """Roll a die, or a few.

        Can be formatted as '!roll <num rolls>d<num sides>[+modifier]"""

        output = ""

        if roll.rolls > roll.MAX_ROLLS:
            output += "Too many dice rolled, rolling a maxcap of {} instead.\n".format(roll.MAX_ROLLS)

        roll_result = roll.cast_roll()

        output += "**[** `{}` **]**".format("` + `".join([str(i) for i in roll_result]))

        if roll.modifier == 0:
            output += "\n**{}**".format(sum(roll_result))
        else:
            sum_roll = sum(roll_result)
            output += "\n{} + {} = **{}**".format(sum_roll, roll.modifier, roll.modifier + sum_roll)

        await ctx.send(output)

    @commands.command(aliases=["thinking"])
    async def think(self, ctx: Context, *, text: str) -> None:
        """:thinking:"""
        await ctx.send(messages.think_message.format(text))

    @checks.sudo()
    @commands.command()
    async def status(self, ctx: Context) -> None:

        embed = discord.Embed(title="Current bot status",
                              description="Uptime: {}".format(DHMSTimestamp.seconds_to_timestamp(self.bot.secs)))

        embed.add_field(name="Uptime", value=DHMSTimestamp.seconds_to_timestamp(self.bot.secs))

        embed.add_field(name="Active cooldown objects", value=str(len(rate_limits.MemeCommand.get_instances())))

        await ctx.send(embed=embed)

    @checks.sudo()
    @commands.command()
    async def counters(self, ctx: Context) -> None:
        counters = self.bot.config.zrevrange("misc:rate_limits:counters", 0, -1, withscores=True,
                                             score_cast_func=int)
        embed = discord.Embed(description="Meme command counters", color=discord.Color.blue())

        [embed.add_field(name=name, value=score) for (name, score) in counters]

        embed.add_field(name="Active cooldown objects", value=str(len(rate_limits.MemeCommand.get_instances())))

        await ctx.send(embed=embed, content=None)

    @commands.command()
    async def why(self, ctx: Context) -> None:
        await ctx.send("https://www.youtube.com/watch?v=flL5b1NaSPE")

    @commands.command()
    async def userinfo(self, ctx: Context, member: Member = None) -> None:
        """Get a user's information"""

        if member is None:
            member = ctx.message.author

        embed = discord.Embed(title="**{}**".format(str(member)),
                              description='*AKA "{}"*'.format(member.nick) if member.nick else None,
                              color=discord.Color.blue())

        embed.set_thumbnail(url=member.avatar_url)

        embed.add_field(name="User ID", value=member.id)
        embed.add_field(name="Nickname", value=member.nick)

        joined_ts = member.joined_at.strftime("%Y-%m-%d %H:%M UTC")
        created_ts = member.created_at.strftime("%Y-%m-%d %H:%M UTC")

        embed.add_field(name="Joined server at", value=joined_ts)
        embed.add_field(name="Account created at", value=created_ts)
        roles = ", ".join([r.name for r in member.roles if r.name != "@everyone"])
        embed.add_field(name="Roles", value=roles if roles else "None")

        await ctx.send(embed=embed)

    @commands.command(hidden=True)
    async def userinfo_simple(self, ctx: Context, *, member: Member = None) -> None:
        """Simple userinfo to aid mobile users"""

        if not member:
            member = ctx.message.author

        roles = ', '.join([r.name for r in sorted(member.roles, reverse=True) if r.name != '@everyone'])

        params = [
            'Username: {}'.format(member.name),
            'Discriminator: {}'.format(member.discriminator),
            'User ID: {}'.format(member.id),
            'Nickname: {}'.format(member.nick if member.nick else '**None Set**'),
            'Joined At: {}'.format(member.joined_at.strftime("%Y-%m-%d %H:%M UTC")),
            'Created At: {}'.format(member.created_at.strftime("%Y-%m-%d %H:%M UTC")),
            'Roles: {}'.format(roles if roles else "None"),
            'Avatar URL: <{}>'.format(member.avatar_url),
        ]

        await ctx.send('\n'.join(params))

    @commands.command()
    async def lmgtfy(self, ctx: Context, *, link: str) -> None:
        """Gives a lmgtfy link to an input."""
        params = {"q": link}
        await ctx.send("http://lmgtfy.com/?{0}".format(urlencode(params)))

    @staticmethod
    def timestamp_to_seconds(timestamp: str) -> Optional[int]:
        """Take in a time in _h_m_s format"""
        units = {
            "d": 86400,
            "h": 3600,
            "m": 60,
            "s": 1
        }
        seconds = 0
        match = re.findall("([0-9]+[smhd])", timestamp)  # Thanks to 3dshax server's former bot
        if match is None:
            return None
        for item in match:
            # The slicing here is to remove the unit letter.
            seconds += int(item[:-1]) * units[item[-1]]
        return seconds

    @checks.is_regular()
    @commands.command()
    async def timer(self, ctx: Context, timestamp: DHMSTimestamp, *, name: str = None) -> None:
        """Format: !timer time(HH:MM:SS) [name]"""
        seconds = timestamp.seconds
        if seconds is None or seconds == 0:
            await ctx.send("Incorrect time format. `HH:MM:SS`, `MM:SS`, or  `SS`.")
            return
        elif seconds > 36000:
            await ctx.send("Timers cannot be longer than 10 hours.")
            return
        await ctx.send("Timer set for {0.timestamp} ({0.seconds} seconds).".format(timestamp))
        await sleep(seconds)
        if name is None:
            output = "{0}, timer for {1.seconds} completed!".format(ctx.message.author.mention, timestamp)
        else:
            output = "{0}, timer {1} for {2.seconds} completed.".format(ctx.message.author.mention, name, timestamp)
        await ctx.send(output)

    @staticmethod
    def role_check(ctx: Context) -> bool:
        """Check for certain roles, based on servers. Hardcoded."""
        if ctx.message.channel.id == 278043765082423296:
            return discord.utils.find(lambda r: r.id in [198275910342934528, 117242433091141636],
                                      ctx.message.author.roles) is not None
        else:
            return True

    # This command causes crashes due to trying to load too much at once, so it's disabled for now.
    @commands.command(enabled=False)
    async def quote_roulette(self, ctx: Context) -> None:

        size_thresh_kb = 200  # Minimum size for logfiles to be chosen.
        rate_limits.MemeCommand.check_rate_limit(ctx, 200)

        logfiles = glob.glob("message_cache/users/*", recursive=True)
        logfiles = [i for i in logfiles if os.stat(i).st_size >= size_thresh_kb]

        random.shuffle(logfiles)
        chosen = []

        async with ctx.typing():
            for file_path in logfiles:
                user_id = re.findall(r'(\d{17,18})', file_path)[0]
                member = discord.utils.get(ctx.message.guild.members, id=user_id)
                if path.getsize(file_path) > size_thresh_kb * 1000 and member is not None and self.role_check(ctx):
                    with open(file_path, "r", encoding="utf-8") as f:
                        line = random.choice(f.readlines()).rstrip("\n")
                        line = utils.extract_mentions(line, ctx.message)
                        chosen.append((member.display_name, line))

                    if len(chosen) == 3:
                        break

        num_chosen = random.randint(0, len(chosen) - 1)

        embed = discord.Embed(title="Whose quote is it? 60 seconds to vote.",
                              description='***"{}"***'.format(chosen[num_chosen][1]))

        n = 1  # Needed because tuple issues exist with enumerate()
        for name, line in chosen:
            embed.add_field(name=num_emoji(n), value='**"{}"**'.format(name), inline=False)
            n += 1

        msg = await ctx.send(embed=embed)

        for i in range(len(chosen)):
            await msg.add_reaction(num_emoji(i + 1))

        await sleep(60)

        output = 'The true author was **{}, number {}**, quoted as saying "{}".\n'.format(chosen[num_chosen][0],
                                                                                          num_chosen + 1,
                                                                                          chosen[num_chosen][1])

        # msg = await self.bot.get_message(ctx.message.channel, msg.id)  # Update the message object
        msg = await ctx.message.channel.fetch_message(msg.id)

        # Get the users that guessed correctly

        incorrect_guesses = []
        correct_reaction_users = None

        for reaction in msg.reactions:
            guesses = await reaction.users().flatten()
            if reaction.emoji == num_emoji(num_chosen + 1):
                correct_reaction_users = guesses
            else:
                incorrect_guesses += guesses

        correct_names = [i.display_name for i in correct_reaction_users if (i.id != self.bot.user.id and
                                                                            i not in incorrect_guesses)]

        if len(correct_names) > 0:
            output += "**{}** guessed correctly!".format(utils.format_list(correct_names))
        else:
            output += "Nobody guessed correctly."

        await ctx.send(output)

    @checks.sudo()
    @commands.command()
    async def happening(self, ctx: Context, timestamp: str) -> None:
        """It's habbening"""
        seconds = self.timestamp_to_seconds(timestamp)
        if seconds is None or seconds == 0:
            await ctx.send("Incorrect time format. `0h0m0s`")
            return
        elif seconds > 36000:
            await ctx.send("Timers cannot be longer than 10 hours.")
            return
        await ctx.send("The happening has begun.")

        imgs = ["https://i.imgur.com/r1mfZwj.gif", "https://i.imgur.com/V9K6CCl.gif", "https://i.imgur.com/4oyQobw.gif",
                "https://i.imgur.com/yscEsOL.gif", "https://i.imgur.com/DgfMc40.gif"]

        delay = 0.2 * seconds

        for img in imgs:
            await sleep(delay)
            await ctx.send(img)

    @commands.command()
    async def lenny(self, ctx: Context) -> None:
        await ctx.send("( ͡° ͜ʖ ͡°)")

    @commands.command()
    async def loony(self, ctx: Context) -> None:
        await ctx.send("`( ͡° ͜ʖ ͡°)`")

    @commands.command(hidden=True)
    async def eroge(self, ctx: Context) -> None:
        await ctx.send("I'm not going to ruin your day but I am an eroge artist and a professional on the field of "
                       "sex and I can tell you that 4 hours is not normal and you should check it out with a "
                       "doctor")

    @commands.command()
    async def get_wc(self, ctx: Context, *, user: str = None) -> None:
        """Get a wordcloud comprised of a user's history"""
        message = ctx.message
        if await self.check_verification(ctx) and rate_limits.MemeCommand.check_rate_limit(ctx, 15):
            if len(message.mentions) > 0:
                member = message.mentions[0]
            elif user is None:
                member = message.author
            else:
                member = discord.utils.find(lambda m: m.name.startswith(user), message.guild.members)

            if member is not None:
                try:
                    await ctx.send(file=discord.File("wc_pictures/{0}.png".format(member.id)),
                                   content="Word cloud for {}".format(member.name))
                except FileNotFoundError:
                    await ctx.send("Wordcloud not found.")

    # noinspection PyTypeChecker
    @commands.command()
    async def pickup(self, ctx: Context, *, target: str) -> None:
        """Pick up an item from someone."""
        if rate_limits.MemeCommand.check_rate_limit(ctx, 30):
            item = random.random()
            # noinspection PyTypeChecker
            if item <= 0.75:
                with open('carve_reg.txt') as f:
                    line_chosen = random.choice(f.readlines())
                    await ctx.send("You got {0}'s {1}!".format(target, line_chosen[:-1]))

            elif 0.75 < item < 0.95:  # Read from the orbs file
                with open('pickup_orbs.txt') as f:
                    line_chosen = random.choice(f.readlines())  # 61 total
                    use = random.randint(1, 3)
                    if use == 1:  # Normal pickup
                        await ctx.send("You got {0}'s {1}!".format(target, line_chosen[:-1]))
                    elif use == 2:  # Using it
                        await ctx.send("You used {0}'s {1}!".format(target, line_chosen[:-1]))
                    else:
                        await ctx.send("You tried to use {0}'s {1}, but it activated on yourself!".format(
                            target, line_chosen[:-1]))

            else:  # Itemizer time
                with open('carve_reg.txt') as f:
                    line_chosen = random.choice(f.readlines())  # Currently 291 items
                    await ctx.send("You activated {0}'s Itemizer Orb, turning you into a {1}!".format(
                        target, line_chosen[:-1]))

    @commands.Cog.listener()
    async def on_timer_update(self, seconds: int) -> None:
        if seconds % 10 == 0:
            # Check for countdowns expiring
            for name in self.countdowns:
                countdown = self.countdowns.get(name)
                if countdown is not None and countdown.seconds_remaining(countdown["time"] is None):
                    chan = self.bot.get_channel(int(countdown["channel_id"]))
                    await chan.send("<@{}> Countdown {} completed.".format(countdown["author_id"],
                                                                           countdown["name"]))

                    countdown["completed"] = True
                    await self.countdowns.put(name, countdown)

    @commands.Cog.listener()
    async def on_message(self, message: Message) -> None:
        if len(message.mentions) > 0 \
                and message.mentions[0].id == self.bot.user.id \
                and "boo" in message.content.lower():
            await sleep(1)
            await message.channel.send("No boo {} {}".format("u" * self.bot.boo_counter,
                                                             message.author.mention))
            if self.boo_counter == 1950:
                self.boo_counter = 0
            self.boo_counter += 1


def setup(bot: Bot) -> None:
    bot.add_cog(General(bot))
