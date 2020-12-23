"""Moderating related commands"""

import datetime
import re

from typing import Dict, Optional

import discord
from discord import Color, Embed, Guild, Member, TextChannel

from discord.ext import commands
from discord.ext.commands import Context, Bot

from .utils import checks


class Timestamp:

    def __init__(self, argument: str) -> None:
        self.timestamp = str(argument)
        self.pieces = self.parse_timestamp(self.timestamp)
        if not self.pieces:
            raise commands.BadArgument("Incorrect timestamp format.")

    def __str__(self) -> str:
        return self.timestamp

    @staticmethod
    def parse_timestamp(timestamp: str) -> Optional[Dict[str, int]]:
        """
        Take in a time in _d_h_m_s format.

        Possible flags are:
            y: year
            M: month
            d: day of week (1 is monday, 7 is sunday)
            D: day (date)
            h: hour (24h time)
            m: minute
            s: second

        """
        parts = {}
        match = re.findall("([0-9]+[yMwDsmhd])", timestamp)  # Thanks to 3dshax server's former bot
        if match is None:
            return None
        else:
            for item in match:
                # The slicing here is to remove the unit letter.
                parts[item[-1]] = int(item[:-1])

            return parts


class RecurringTimeStamp(Timestamp):
    # TODO: improve this so it isn't just copy-pasted

    def __init__(self, argument: str) -> None:
        super().__init__(argument)

    def __eq__(self, other: datetime.datetime) -> bool:
        assert isinstance(other, datetime.datetime)
        return self.equals_datetime(self.timestamp, other)

    def __ne__(self, other: datetime.datetime) -> bool:
        return not self.__eq__(other)

    @staticmethod
    def parse_timestamp(timestamp: str) -> Optional[Dict[str, str]]:
        """
        Take in a time in _d_h_m_s format, similar to how cron operates.

        Possible flags are:
            y: year
            M: month
            d: day of week (1 is monday, 7 is sunday)
            D: day (date)
            h: hour (24h time)
            m: minute
            s: second

        Other flags/options
            Params can be wild-carded with *, or simply omitted.
            Multiple options can be specified with commas, e.g. 1,3,5d
            A range of days can also be specified with a dash, e.g. 1-5d

        Examples:
            3d6h: Every wednesday at 6
            3,5d20h: Every wednesday and friday at 8 pm

        """
        parts = {}
        match = re.findall("((?:[0-9],*-?|\*)+[yMwDsmhd])", timestamp)  # Thanks to 3dshax server's former bot
        if match is None:
            return None
        else:
            for item in match:
                # The slicing here is to remove the unit letter.
                parts[item[-1]] = item[:-1]

            return parts

    @staticmethod
    def timestamp_to_datetime(timestamp: str) -> Optional[datetime.datetime]:
        """
        Take in a time in _d_h_m_s format and convert it to datetime
        Useful for one-off notifications
        """
        parts = {}
        match = re.findall("([0-9]+[smhd])", timestamp)  # Thanks to 3dshax server's former bot
        if match is None:
            return None
        for item in match:
            # The slicing here is to remove the unit letter.
            parts[item[-1]] = int(item[:-1])
        return datetime.datetime.now().replace(day=parts.get("d"),
                                               hour=parts.get("h"),
                                               minute=parts.get("m"),
                                               second=parts.get("s"))

    @staticmethod
    def _get_dt_param(identifier: str, dt: datetime.datetime) -> int:
        if identifier == "y":
            return dt.year
        elif identifier == "M":
            return dt.month
        elif identifier == "d":
            return dt.isoweekday()
        elif identifier == "D":
            return dt.day
        elif identifier == "h":
            return dt.hour
        elif identifier == "m":
            return dt.minute
        elif identifier == "s":
            return dt.second

    @staticmethod
    def equals_datetime(timestamp: str, dt_obj: datetime.datetime) -> bool:
        """Check a split list of timestamp parts to
        see that they all match the current time."""
        timestamp_parts = RecurringTimeStamp.parse_timestamp(timestamp)

        for identifier, num in timestamp_parts.items():

            dt_param = RecurringTimeStamp._get_dt_param(identifier, dt_obj)

            if "," in identifier:
                for n in num.split(","):
                    if dt_param != int(n):
                        return False

            elif "-" in num:
                num_parts = num.split("-")
                if dt_param not in range(int(num_parts[0]), int(num_parts[1])):
                    return False

            elif num == "*":
                continue

            elif int(num) != dt_param:
                    return False

        else:
            return True


class DurationTimeStamp(Timestamp):
    """
    Timestamp used to represent a duration.

    Should only really be used in command processing, and then converted into a datetime object.
    """

    def __init__(self, argument: str) -> None:
        if argument in ["permanent", "perma"]:
            argument = "99y99M99d99h99m99s"  # Just make it arbitrarily large
        super().__init__(argument)

    def to_timedelta(self) -> datetime.timedelta:
        """Get the datetime of the timestamp in relation to now."""
        # Timedeltas cannot handle more than weeks, so we need to convert
        # We just change things to days to make things more straightforward
        now = datetime.datetime.utcnow()
        td_pieces = self.pieces.copy()
        # Days, weeks and years are easy enough
        td_pieces["d"] = td_pieces.get("y", 0) * 365 + td_pieces.get("w", 0) * 7 + td_pieces.get("d", 0)
        # Months have variable lengths, so we need to use a different method
        months = td_pieces.get("M", 0)

        if months != 0:
            new_dt = now.replace(year=now.year + (now.month + months) // 12,
                                 month=(now.month + months) % 12)
            td_pieces["d"] += (new_dt - now).days

        # Make a delta from the durations specified in the ts
        td = datetime.timedelta(days=td_pieces.get("d", 0),
                                hours=td_pieces.get("h", 0),
                                minutes=td_pieces.get("m", 0),
                                seconds=td_pieces.get("s", 0))

        return td

    def to_datetime(self) -> datetime.datetime:
        """
        Get the datetime of the timedelta plus the current time.\
        """

        # Ignore this inspection, it returns the right thing (a datetime object)
        return datetime.datetime.utcnow() + self.to_timedelta()

    def total_seconds(self) -> int:
        return int((self.to_timedelta() - datetime.datetime.utcnow()).total_seconds())


class Mod(commands.Cog):

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.config = bot.config
        # Create cache on startup so we don't have to ping the DB every second
        self._reminder_cache = {}
        for key in self.config.scan_iter("config:mod:reminders*"):
            rem = self.config.hgetall(key)
            self._reminder_cache[rem["timestamp"]] = rem

    @property
    def mod_server(self) -> Guild:
        return self.bot.get_guild(146626123990564864)

    @property
    def d_important(self) -> TextChannel:
        return self.bot.get_channel(395304906912825344)
        # return self.bot.get_channel(220209831200423936)  # #cd-2017important
        # return self.bot.get_channel(262993960035680256)  # Debug

    @property
    def r_pkmn(self) -> Guild:
        return self.bot.get_guild(111504456838819840)

    @property
    def mod_tools_chan(self) -> TextChannel:
        return self.bot.get_channel(246279583807045632)

    async def add_mod_note(self, user_id: int, message: str) -> None:
        """Assign a modnote to `member` with message `message`"""
        await self.mod_tools_chan.send("%modnote add {} {}".format(user_id, message))

    @checks.sudo()
    @commands.command(hidden=True)
    async def set_reminder(
            self, ctx: Context, timestamp: RecurringTimeStamp, *, message: str
    ) -> None:
        """
        Take in a time in _d_h_m_s format, similar to how cron operates.

        Possible flags are:
            y: year
            M: month
            d: day of week (1 is monday, 7 is sunday)
            D: day (date)
            h: hour (24h time)
            m: minute
            s: second

        Other flags/options
            Params can be wild-carded with *, or simply omitted.
            Multiple options can be specified with commas, e.g. 1,3,5d
            A range of periods can be specified with a dash, e.g. 1-5d

        Examples:
            3d6h0m0s: Every wednesday at 6
            3,5d20h30m0s: Every wednesday and friday at 8:30 pm

        """

        reminder = {
            "timestamp": str(timestamp),
            "message": message,
            "channel": int(ctx.message.channel.id),  # TODO Implement this later
            "created_at": datetime.datetime.now().timestamp()
        }

        extra_pings = []

        if "@here" in ctx.message.content:
            extra_pings.append("@here")
        if "@everyone" in ctx.message.content:
            extra_pings.append("@everyone")
        [extra_pings.append(x) for x in re.findall(r'(<@[!&]?[0-9]+>)', ctx.message.content)]

        if extra_pings:
            reminder["extra_pings"] = " ".join(extra_pings)

        self.config.hmset("config:mod:reminders:{}".format(timestamp), reminder)

        await ctx.send("\N{OK HAND SIGN}")

    @checks.sudo()
    @commands.command()
    async def list_reminders(self, ctx: Context) -> None:
        output = []
        for key in self.config.scan_iter("config:mod:reminders*"):
            reminder_data = self.config.hgetall(key)
            output.append("**{}**: {}".format(reminder_data["timestamp"], reminder_data["message"]))
        embed = Embed(description="\n".join(output), color=Color.blue())
        embed.set_author(name="Current active reminders")
        await ctx.send(embed=embed)

    @checks.sudo()
    @commands.command()
    async def clear_all_reminders(self, ctx: Context) -> None:
        [self.config.delete(i) for i in self.config.scan_iter("config:mod:reminders*")]
        self._reminder_cache = {}
        await ctx.send("\N{OK HAND SIGN}")

    @checks.sudo()
    @commands.command()
    async def del_reminder(self, ctx: Context, timestamp: str) -> None:
        """Delete an existing reminder."""
        if self.config.exists("config:mod:reminders:{}".format(timestamp)):
            self.config.delete("config:mod:reminders:{}".format(timestamp))
            del self._reminder_cache[timestamp]
            await ctx.send("Reminder for {} deleted.".format(timestamp))
        else:
            await ctx.send("Reminder `{}` not found.".format(timestamp))

    @commands.Cog.listener()
    async def on_member_update(self, before: Member, after: Member) -> None:
        invalid_nicks = ["everyone", "here", "mods", "bot dev team", "admin", "general moderator",
                         "franchise moderator", "topic moderator", "voice moderator", "mod in training (mit)",
                         "regular manager"]
        if self.r_pkmn is None:
            return
        if after.guild.id == self.r_pkmn.id and before.nick != after.nick and after.nick is not None:
            stripped_nick = after.nick.lower().replace("\u200b", "")  # Yank out zero width space
            if stripped_nick in invalid_nicks:
                await after.edit(reason="Invalid name set: ({})".format(after.nick), nick=None)
                await after.send("In order to reduce abuse, your nickname has been reset.")
                await self.add_mod_note(after.id, "[BOT] Set nickname to {}, reset automatically.".format(after.nick))

    @commands.Cog.listener()
    async def on_timer_update(self, secs: int) -> None:
        # Every 10 seconds, check to see if the event matches the current time
        # If so, trigger.
        for ts in self._reminder_cache:
            rem_dt = RecurringTimeStamp(ts)
            now = datetime.datetime.now()
            if rem_dt == now:
                active_reminder = self._reminder_cache[ts]
                embed = Embed(description=active_reminder["message"],
                              color=Color.blue())
                embed.set_author(
                    name="Reminder",
                    icon_url="https://emojipedia-us.s3.amazonaws.com/thumbs/"
                             "160/twitter/31/alarm-clock_23f0.png"
                )
                embed.set_footer(text="Timestamp: {}".format(ts))
                await self.d_important.send(
                    embed=embed, content=active_reminder.get("extra_pings")
                )


def setup(bot: Bot) -> None:
    bot.add_cog(Mod(bot))
