"""
Utility command to store a user's timezone and allow for easier conversions with time.

Includes utilities to get the user's current time, or list off all the timezones present in the server.


Planned database configuration:

user:
    user_id:
        tz:
            timezone: <timezone_tag>
            privacy_enabled: <boolean flag>
            whitelisted_guilds: <set of guilds user has whitelisted

"""
from typing import Set, Optional

from discord.ext import commands
from discord.ext.commands import Context, Bot
import discord
import pytz
import datetime

TZ_SET_PROMPT_MSG_INIT = """
What's the 2-character code for your country? (for example, US for United States).
Type `exit` at any point to quit this prompt.
"""

TZ_CHOOSE_TIMEZONE_MSG = """
Which of the following timezones do you live in?
{}
"""

TZ_NONE_FOUND_MSG = """
I can't seem to find a timezone in the country you specified, sorry!
Try calling this command again with an argument from this site: https://tinyurl.com/rgu2hcm
For example, !tz set America/Santiago
"""

DT_FORMAT = "%a %I:%M:%S %p %Z"


class TimeZones(commands.Cog):

    def __init__(self, bot: Bot):
        self.bot = bot
        self.config = bot.config

    def set_timezone(self, user_id: int, timezone_str: str):
        """
        Consolidated way to set a user's timezone
        """

        # Add some initializing keys at first
        if not self.config.exists("user:{}:tz:timezone".format(user_id)):
            self.config.set("user:{}:tz:privacy_enabled".format(user_id), 0)

        self.config.set("user:{}:tz:timezone".format(user_id), timezone_str)

    def get_timezone(self, user_id: int) -> str:
        return self.config.get("user:{}:tz:timezone".format(user_id))

    def get_timezone_respecting_privacy(self, user_id: int, guild_id: int) -> Optional[str]:
        """
        Get a user's timezone, but returns None if the user has no timezone or has privacy blocking
        the current guild
        :param user_id: User to pull from
        :param guild_id: Guild to reference for privacy settings
        """
        if self.has_privacy_enabled(user_id) and not self.is_whitelisted(user_id, guild_id):
            return None
        else:
            return self.get_timezone(user_id)

    def has_privacy_enabled(self, user_id: int) -> bool:
        return self._privacy_setting(user_id) == "1"

    def _privacy_setting(self, user_id: int) -> bool:
        return self.config.get("user:{}:tz:privacy_enabled".format(user_id))

    def set_privacy_setting(self, user_id: int, enabled: bool):
        self.config.set("user:{}:tz:privacy_enabled".format(user_id), int(enabled))

    def get_whitelisted_guilds(self, user_id: int) -> Set:
        return self.config.smembers("user:{}:tz:whitelist_guilds".format(user_id))

    def is_whitelisted(self, user_id: int, guild_id: int) -> bool:
        return self.config.sismember("user:{}:tz:whitelist_guilds".format(user_id), guild_id)

    def add_guild_to_whitelist(self, user_id: int, guild_id: int):
        self.config.sadd("user:{}:tz:whitelist_guilds".format(user_id), guild_id)

    def remove_guild_from_whitelist(self, user_id: int, guild_id: int):
        self.config.srem("user:{}:tz:whitelist_guilds".format(user_id), guild_id)

    def purge_user(self, user_id: int):
        self.config.delete("user:{}:tz:whitelist_guilds".format(user_id))
        self.config.delete("user:{}:tz:timezone".format(user_id))
        self.config.delete("user:{}:tz:privacy_enabled".format(user_id))

    @commands.group()
    async def tz(self, ctx: Context):
        pass

    @tz.command()
    async def set(self, ctx: Context, *, timezone_tag: str = None):
        """
        Set a user's timezone. Should be in pytz.common_timezones format. Otherwise, it'll start an
        interactive prompt.

        We have to do it this way if we want to actually respect things like DST and not have everything
        break.

        > asks for two-letter country code, and show valid country tags from there.
        > If more than one timezone in the country exists, ask the user to select it with a number.
        """

        base_retries = 5

        def message_check(msg):
            return msg.author.id == ctx.message.author.id and msg.channel.id == ctx.channel.id

        async def del_msg(msg):
            try:
                await msg.delete()
            except discord.Forbidden:
                pass

        if timezone_tag is None or timezone_tag not in pytz.common_timezones_set:

            tries_remaining = base_retries

            # Loop a number of times to try to narrow down the user's timezone.
            bot_msg = await ctx.send(TZ_SET_PROMPT_MSG_INIT)

            while tries_remaining > 0:

                response_msg = await self.bot.wait_for("message", check=message_check, timeout=600)

                if response_msg.content.lower() == "exit":
                    return

                # country_timezones is a dictionary holding all ISO country codes, so it makes an easy lookup
                # It has values for upper and lowercase
                if response_msg.content not in pytz.country_timezones:
                    await del_msg(response_msg)

                    await bot_msg.edit(content="Sorry, that doesn't seem to be a valid country code. "
                                               "Please send a message just consisting of the 2-character country "
                                               "code (like US or NZ).")
                    tries_remaining -= 1

                else:
                    valid_timezones = pytz.country_timezones[response_msg.content]

                    # I haven't really verified it, but there's a non-zero chance that some country just
                    # doesn't have a valid timezone in it.
                    # It's probably worth providing this option just to be safe.

                    if len(valid_timezones) == 0:
                        await bot_msg.edit(content=TZ_NONE_FOUND_MSG)
                        await del_msg(response_msg)
                        return

                    output_tz = []

                    for i, tz in enumerate(valid_timezones):
                        # note: incremented by 1 so it starts at 1
                        output_tz.append("{}: {}".format(i + 1, tz))

                    tz_resp = "Which timezone do you reside in? " \
                              "Reply with its number.\n{}".format("\n".join(output_tz))

                    await bot_msg.edit(content=tz_resp)

                    tries_remaining = base_retries

                    # Now, try to get the actual timezone
                    # This is kind of obnoxious lol

                    while tries_remaining > 0:
                        response_msg = await self.bot.wait_for("message", check=message_check, timeout=600)

                        if response_msg.content.lower() == "exit":
                            return

                        # Catch some sanity checks

                        try:
                            choice = int(response_msg.content)
                        except (ValueError, TypeError):
                            await bot_msg.edit(content="Sorry, please respond with a number.\n"
                                                       "{}".format("\n".join(output_tz)))
                            await del_msg(response_msg)
                            tries_remaining -= 1
                            continue
                        if not 0 < choice <= len(valid_timezones):
                            await bot_msg.edit(content="Please choose a number in range.\n"
                                                       "{}".format("\n".join(output_tz)))
                            await del_msg(response_msg)
                            tries_remaining -= 1
                            continue

                        # We should finally have our timezone string
                        # Here, we'll actually set it

                        self.set_timezone(ctx.author.id, valid_timezones[choice - 1])  # Note we added 1 earlier
                        await bot_msg.edit(content="Your timezone has been registered as "
                                                   "{}".format(valid_timezones[choice - 1]))
                        return

            # If we reach this point, we've fallen out of either of the while loops

            await bot_msg.edit(content="Sorry, you've reached the max number of retries for this command. "
                                       "Please call it again if you still want to set your timezone.")
            return

        else:
            self.set_timezone(ctx.author.id, timezone_tag)
            await ctx.send("Your timezone has been updated to {}.".format(timezone_tag))

    @tz.command()
    async def get(self, ctx: Context, *mentions: discord.Member):
        """
        Fetch a timezone.
        If one user is specified, it'll show both of your timezones and local times.

        If multiple users are specified, it'll pull their local times and compare them.

        The first two users can be specified by name, but any beyond that must be tagged.
        """

        user_tz_name = self.get_timezone(ctx.author.id)

        desc = []

        if user_tz_name and not (self.has_privacy_enabled(ctx.author.id) and
                                 not self.is_whitelisted(ctx.author.id, ctx.guild.id)):
            user_tz = pytz.timezone(user_tz_name)
            user_dt = datetime.datetime.now(tz=user_tz)
            desc.append("**{}**:\n {}".format("{}'s local time".format(ctx.author.name),
                                              user_dt.strftime(DT_FORMAT)))

        for member in mentions:
            if member.id == ctx.author.id:
                continue
            mem_tz = self.get_timezone(member.id)

            if mem_tz is None:
                continue
            elif self.has_privacy_enabled(member.id) and not self.is_whitelisted(member.id, ctx.guild.id):
                # Skip the user if they don't want their TZ exposed in here
                continue
            else:
                new_tz = pytz.timezone(mem_tz)
                new_dt = datetime.datetime.now(tz=new_tz)
                # Storing them as a tuple of (display name, tz_info)
                desc.append("**{}**:\n {}".format(member.display_name, new_dt.strftime(DT_FORMAT)))

        embed = discord.Embed(description="Timezone information:\n\n{}".format("\n".join(desc)))

        await ctx.send(embed=embed)

    @tz.command()
    async def reltime(self, ctx: Context, src: discord.Member, target: discord.Member, *, time: str):
        """
        Get a relative time offset for another user.
        Time should be formatted as HH:MM, in 24hr time.
        :param target: User's timezone to use for timezone calcs.
        :param time: Time to calculate
        """

        not_found_user = None
        format_str = "%H:%M"

        src_tz_str = self.get_timezone_respecting_privacy(src.id, ctx.guild.id)
        target_tz_str = self.get_timezone_respecting_privacy(target.id, ctx.guild.id)

        if not src_tz_str:
            not_found_user = src
        elif not target_tz_str:
            not_found_user = target

        if not_found_user:
            await ctx.send("Cannot compare, {} has no timezone info.".format(not_found_user.display_name))
            return

        src_tz = pytz.timezone(src_tz_str)
        target_tz = pytz.timezone(target_tz_str)

        src_time = datetime.datetime.strptime(time, format_str)

        now = datetime.datetime.now()

        src_time = src_time.replace(year=now.year, month=now.month, day=now.day,
                                    tzinfo=src_tz)
        # src_time = src_tz.normalize(src_time)

        # src_dt = src_tz.fromutc(src_time)
        # target_dt = target_tz.fromutc(target_tz)
        target_dt = src_time.astimezone(target_tz)

        desc = ["**{}**:\n {}".format(src, src_time.strftime(DT_FORMAT)),
                "**{}**:\n {}".format(target, target_dt.strftime(DT_FORMAT))]

        embed = discord.Embed(description="Relative times given {} in {}'s timezone:\n\n{}".format(
            time,
            src.display_name,
            "\n".join(desc)))

        await ctx.send(embed=embed)

    @tz.command()
    async def toggle_privacy(self, ctx: Context):
        """
        Toggle a privacy filter. If enabled, only guilds you trust (using !tz trust_server) will have access to your
        timezone information.
        """

        cur_privacy = self._privacy_setting(ctx.message.author.id)
        if cur_privacy is None:
            cur_privacy = False
        else:
            cur_privacy = bool(int(cur_privacy))
        self.set_privacy_setting(ctx.author.id, not cur_privacy)

        if cur_privacy:
            await ctx.send("Your privacy settings have been disabled. Your timezone will be public "
                           "in every guild we share.")
        else:
            await ctx.send("Your privacy settings have been enabled. Your timezone will only be "
                           "shared in guilds you specify with !tz trust_server.")

    @tz.command()
    async def trust_server(self, ctx: Context, guild_id: int = None):
        """
        Allow your timezone to be accessed in the server
        """
        if not guild_id:
            guild_id = ctx.guild.id

        guild = self.bot.get_guild(guild_id)

        if not guild:
            await ctx.send("I don't seem to share that guild with you.")
            return
        self.add_guild_to_whitelist(ctx.author.id, guild_id)

        await ctx.send("I'll now share your timezone in guild {}.".format(guild.name))

    @tz.command()
    async def untrust_server(self, ctx: Context, guild_id: int = None):
        """
        Remove the current server from your trusted server list.
        """
        if not guild_id:
            guild_id = ctx.guild.id
        guild = self.bot.get_guild(guild_id)

        if not guild:
            await ctx.send("I don't seem to share that guild with you.")
            return
        self.remove_guild_from_whitelist(ctx.author.id, guild_id)

        await ctx.send("I'll now hide your timezone in guild {}.".format(guild.name))

    @tz.command()
    async def delete(self, ctx: Context):
        """
        Remove a user's timezone configuration from the bot. Purges their preferences and removes their data from the
        db.
        """
        self.purge_user(ctx.author.id)
        await ctx.send("Your timezone information has been removed from the bot.")


def setup(bot: Bot) -> None:
    bot.add_cog(TimeZones(bot))
