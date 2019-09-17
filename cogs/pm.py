"""
Commands for use through PMs.

Rewritten around 9/25/18 to make it more widespread and similar to the functionality in goPC.

Current redis layout is as follows:

guild
    roles
        + config: hashmap of certain flags to store.
            # Flags include only_pm
        + all
            + names: hashmap associating role titles to IDs
        + roles
            + [role title]: A title referring to a certain role. What !add will reference.
                + role_id: string user ID
                + bans: hashmap of {user_id: unban_time_epoch}. Blacklisted users have a ban time of -1
                + TODO prereqs: Set of role IDS which must be satisfied for this role to be added.

Flow: Mod registers role for guild. User attempts to add the role by name. Guild is checked.

TODO should check every so often to make sure
"""
from typing import Optional

from discord import Guild, Member
from discord.ext import commands
import discord
import datetime

from discord.ext.commands import Context
from math import floor
from redis import RedisError
from time import time

from .utils import checks
from .mod import DurationTimeStamp


class PMs:

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config

    # TODO create a bot-wide raid mode, disabling role-adding commands

    @property
    def r_pkmn_guild(self):
        return self.bot.get_guild(id=111504456838819840)

    @staticmethod
    def has_required_role(user, guild, role_id):
        discord.utils.get(discord.utils.get(guild.members, id=user.id).roles, id=role_id)
        member = discord.utils.get(guild.members, id=user.id)
        return discord.utils.get(member.roles, id=role_id) is not None

    def get_rolebans(self, guild: Guild, role_title: str) -> dict:
        """Get a guild's role-bans."""
        try:
            return self.config.hgetall("guild:{}:roles:roles:{}:bans".format(guild.id, role_title))
        except RedisError:
            return {}

    def get_role_prereqs(self, guild: Guild, role_title: str):
        try:
            return self.config.hgetall("guild:{}:roles:roles:{}:prereqs".format(guild.id, role_title))
        except RedisError:
            return set()

    def role_exists(self, guild: Guild, role_title: str) -> bool:
        return self.config.hexists("guild:{}:roles:all:names".format(guild.id), role_title)

    def get_guild_config(self, guild: Guild) -> dict:
        try:
            return self.config.hgetall("guild:{}:roles:config".format(guild.id))
        except RedisError:
            return {}

    def get_guild_role_names(self, guild: Guild) -> dict:
        """
        Get all role titles for the guild.
        """
        # TODO Consider adding alias tags which simply have a reference to another role.
        try:
            return self.config.hgetall("guild:{}:roles:all:names".format(guild.id))
        except RedisError:
            return {}

    def _get_role_id_from_title(self, guild: Guild, role_title: str) -> Optional[int]:
        try:
            return self.config.hget("guild:{}:roles:all:names".format(int(guild.id)), role_title.lower())
        except RedisError:
            return None

    @staticmethod
    def _format_datetime(dt: datetime.datetime) -> str:
        fmt = "%b %d, %Y %H:%M:%S UTC"
        return dt.strftime(fmt)

    @staticmethod
    async def add_role_from_member(role_id, member_id, guild):
        role = discord.utils.get(guild.roles, id=role_id)
        member = discord.utils.get(guild.members, id=member_id)
        if role not in member.roles:
            await member.add_roles(role)
            return True
        else:
            return False

    @staticmethod
    async def remove_role_from_member(role_id: int, user_id: int, guild: Guild):
        member = discord.utils.get(guild.members, id=user_id)
        role = discord.utils.get(guild.roles, id=role_id)
        # Checking if role in member.roles does not work.
        # Already tried it.
        try:
            await member.remove_roles(role)
            return True
        except discord.HTTPException:
            return False

    async def add_role(self, ctx, role_title, guild):

        if self.get_guild_config(guild).get("only_pm") and not isinstance(ctx.message.channel, discord.DMChannel):
            # Don't even respond if the server disallows roles being added in channels.
            return
        elif not await self.check_user_verification(ctx.message.author, guild):
            await ctx.send("You are either under the server verification timer, or you are set to offline/invisible.")
            return

        prereq_roles = self.get_role_prereqs(guild, role_title)

        member = guild.get_member(ctx.message.author.id)

        # Check to see if the author has all of the prereq roles
        required_roles = [i for i in member.roles]
        member_roles = {str(i.id) for i in required_roles}
        if not set(prereq_roles.keys()).issubset(member_roles):
            required_roles = prereq_roles.difference(member_roles)
            required_roles_str = ", ".join([i.name for i in required_roles if i.id in required_roles])
            await ctx.send(
                "You are missing the following required roles to add that role: {}".format(required_roles_str)
            )
            return

        guild_role_bans = self.get_rolebans(guild, role_title)

        if str(ctx.message.author.id) in guild_role_bans.keys():

            roleban_ts = int(floor(float(guild_role_bans[str(ctx.message.author.id)])))
            if roleban_ts == -1:
                await ctx.send("You are currently blacklisted from attaining this role.")
                return
            else:
                # At this point, the roleban TS should just be seconds since epoch
                fmt = "%b %d, %Y %H:%M:%S UTC"
                # convert the unix timestamp
                unban_dt = datetime.datetime.utcfromtimestamp(roleban_ts)

                # Ban has expired.
                if unban_dt > datetime.datetime.utcnow():
                    await ctx.send("You are temporarily banned from obtaining this role.\n"
                                   "This ban will expire {}.".format(unban_dt.strftime(fmt)))
                    return
                else:
                    self.config.hdel("guild:{}:roles:roles:{}:bans".format(guild.id, role_title), ctx.message.author.id)

        role_id = int(self._get_role_id_from_title(guild, role_title))

        try:
            if await self.add_role_from_member(role_id, ctx.message.author.id, guild):
                await ctx.send("Successfully added role.")
            else:
                await ctx.send("You already have this role.")
        except discord.Forbidden:
            await ctx.send(
                "I'm either missing permissions, or the role you're trying to add is above mine in the list."
            )

    async def remove_role(self, ctx, role_title: str, guild: Guild):
        if self.get_guild_config(guild).get("only_pm") and not isinstance(ctx.message.channel, discord.DMChannel):
            # Don't even respond if the server disallows roles being added in channels.
            return

        # TODO Move this stuff up
        # elif isinstance(ctx.message.channel, discord.DMChannel):
        #     guild = self.get_server_from_pm(ctx)
        # else:
        #     guild = ctx.guild

        role_id = self._get_role_id_from_title(guild, role_title)

        if role_id is None:
            await ctx.send("Role could not be found.")
            return

        if await self.remove_role_from_member(int(role_id), ctx.message.author.id, guild):
            await ctx.send("Successfully removed role.")
        else:
            await ctx.send("Role could not be removed.")

    @checks.sudo()
    @commands.command(no_pm=True)
    async def register_role(self, ctx, role_name: str, role_title: str, guild_id: int = None):
        """
        Register a new role to be addable by !set.
        role_name: Full name of the role, surrounded by ""
        role_title: title by which the role should be added with !add. Not case-sensitive
        guild_id: Optional, the guild in which the role should be registered.
        """
        role_title = role_title.lower()

        # Raises expected AttributeError
        if guild_id is None:
            guild = ctx.guild
            guild_id = guild.id
        else:
            guild = self.bot.get_guild(guild_id)
            guild_id = guild.id
            if guild is None:
                await ctx.send("Couldn't find the guild provided.")
                return

        try:
            role_id = discord.utils.get(guild.roles, name=role_name).id
        except AttributeError:
            # role returned is None
            await ctx.send("Role with name {} in guild {} could not be found.".format(role_name, guild.name))
            return

        db_key = "guild:{}:roles:roles:{}".format(guild_id, role_title)

        self.config.set("{}:role_id".format(db_key), role_id)

        self.config.hset("guild:{}:roles:all:names".format(guild.id), role_title, role_id)

        await ctx.send("New role '{}' registered with keyword '{}'".format(role_name, role_title))

    @checks.sudo()
    @commands.command()
    async def deregister_role(self, ctx, role_title: str, guild_id: int = None):
        """
        Remove a role that's been registered by !register_role.
        role_title: title of the role to add, surrounded by "".
        guild_id: Optional, guild in which the role exists.
        """

        if guild_id is None:
            guild = ctx.guild
            guild_id = guild.id
        else:
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                await ctx.send("Couldn't find the guild provided.")
                return

        role_key = "guild:{}:roles:roles:{}".format(guild_id, role_title.lower())
        if self.config.exists(role_key):
            self.config.remove(role_key)
            self.config.hdel("guild:{}:roles:all:names".format(guild_id), role_title)
            await ctx.send("Role '{}' was deregistered.".format(role_title))
        else:
            await ctx.send("The given role doesn't exist in the specified guild.")

    @staticmethod
    async def check_user_verification(user, guild):
        """
        Check if a user would fall under the verification period
        :param user: User or member object
        :param guild: Server object that the member belongs to
        :return: False if the member would be limited by the verification level.
        """

        # Unfortunately, this can only go so far as to check the verification level and apply
        # a timer. It can't check if the user has a verified email address or phone number.

        member = guild.get_member(user.id)

        if not member:
            return False
        elif member.status in [discord.Status.offline, discord.Status.invisible]:
            # We can't really do anything if they're offline.
            return False

        if member.guild.verification_level == discord.VerificationLevel.low:
            return True
        elif member.guild.verification_level == discord.VerificationLevel.medium:
            delay = 5
        else:
            delay = 10

        delay = datetime.timedelta(minutes=delay)
        return (datetime.datetime.utcnow() - member.joined_at) > delay

    @commands.command()
    async def set(self, ctx, *, role_title: str):
        """Self-assign a certain role.
        Roles are mature, anime, subnews, and politics (requires reg).
        """

        role_name = role_title.lower()
        if isinstance(ctx.message.channel, discord.DMChannel):
            guild = await self.get_server_from_pm(ctx)

            if guild is None:
                return
        else:
            guild = ctx.guild

        if guild == self.r_pkmn_guild:
            await ctx.send("This command has been disabled on Porygon2 for the r/pokemon server. "
                           "Instead, DM Manaphy `+set {}`.".format(role_name))
            return

        await self.add_role(ctx, role_title, guild)

    @commands.command()
    async def unset(self, ctx, *, role_name: str):
        """Un-assign a role assigned with !set"""
        role_name = role_name.lower()

        if isinstance(ctx.message.channel, discord.DMChannel):
            guild = await self.get_server_from_pm(ctx)
        else:
            guild = ctx.guild

        if guild is None:
            return

        await self.remove_role(ctx, role_name, guild)

    async def get_server_from_pm(self, ctx) -> Optional[Guild]:
        # TODO: Work this out
        """
        Handle the logic for determining how many servers are shared between the bot and the message author, and
        from there allowing the user to select the one they desire.

        Re-implementation of goPC's code.
        """

        # Get the servers shared between the author and the bot

        def message_check(msg):
            try:
                int(msg.content)  # Just try to check if it's castable
                return msg.author.id == ctx.message.author.id
            except ValueError:
                # allow for an exit
                return msg.content.lower() == 'exit'

        guilds_shared = []
        for guild in self.bot.guilds:
            member = guild.get_member(ctx.message.author.id)
            # This should short circuit
            # If not, we'll surely see it at scale

            # Perform a membership check, and see if we've even created any roles.
            if member is not None and self.config.exists("guild:{}:roles:all:names".format(guild.id)):
                guilds_shared.append(guild)

        if len(guilds_shared) == 0:  # This shouldn't normally appear
            await ctx.send("We don't appear to share any servers that have addable roles.")
            return None

        elif len(guilds_shared) == 1:  # This makes it really easy, since there's only one server, just use that one
            return guilds_shared[0]

        else:  # Things get complicated. From here, it's mostly just message management.

            base_message = "Oops, looks like I share more than one server with you. Which server would you like " \
                           "to update your role in? Reply with the digit of the server, or 'exit' to cancel.\n"

            for i, svr in enumerate(guilds_shared, start=1):
                base_message += "{0}: {1.name}\n".format(i, svr)

            await ctx.send(base_message)

            # Wait for the message that the user sends back.
            # It should be an int.

            tries_remaining = 3

            while tries_remaining > 0:

                response_msg = await self.bot.wait_for("message", check=message_check, timeout=600)

                if response_msg is None:
                    return None

                elif response_msg.content == 'exit':
                    return None

                selection = int(response_msg.content)

                # + 1 because we already start from 1
                if not 0 < selection < len(guilds_shared) + 1:
                    await ctx.send("That number was out of range, try again.")
                    tries_remaining -= 1
                    continue
                else:
                    server = guilds_shared[(int(selection) - 1)]
                    return server

    @checks.sudo()
    @commands.command(no_pm=True)
    async def roleban(
            self, ctx: Context, target: Member, role_title: str,
            duration: DurationTimeStamp, *, reason: str = "None given."
    ) -> None:
        """
        Role-ban a user for a specified time.

        Should be called from within the guild the user will be rolebanned from.
        """

        role_title = role_title.lower()

        guild = ctx.guild
        target_role_id = self._get_role_id_from_title(guild, role_title)

        if target_role_id is None:
            role_names = ", ".join(self.get_guild_role_names(guild))
            await ctx.send("Invalid role name. Possible roles are {}.".format(role_names))
            return
        elif target is None:
            await ctx.send("Member not found.")
            return
        else:

            # Send a message, send a mod note and create a server log note
            if discord.utils.get(target.roles, name=role_title):
                # Note that we can still unban if the user doesn't have the given role
                await target.remove_roles(discord.utils.get(target.roles, name=role_title),
                                          reason="Removed due to blacklisting user.")

            # Make the ban-time the desired duration plus the current utc time
            # Just make it permanent if it's too huge

            # Otherwise, make it -1 if we want to permaban them
            expire_time = \
                (time() + duration.to_timedelta().total_seconds()) if duration.pieces.get("y", 0) < 50 else -1

            self.config.hset("guild:{}:roles:roles:{}:bans".format(guild.id, role_title), target.id, expire_time)

            # I actually think the way I handled the expiring tags was super clever, should remember that this is a
            # thing in redis

            # self.config.set("user:{}:role_blacklist:{}".format(target.id, role_title), str(duration), ex=expire_time)

            server_logs = self.bot.get_cog("ServerLogs")
            if server_logs:

                if expire_time != -1:
                    expire_time_ts = datetime.datetime.fromtimestamp(expire_time).strftime("%b %d, %Y %H:%M:%S UTC")
                else:
                    expire_time_ts = "Never."

                await server_logs.handle_external_embed(ctx, "was role-banned from {}.".format(role_title),
                                                        priority=True,
                                                        member=target,
                                                        **{"Moderator responsible": ctx.message.author.name,
                                                           "Reason": reason,
                                                           "Duration": str(duration),
                                                           "Expires": expire_time_ts},)

            await ctx.send("User {} has been role-banned successfully.".format(str(target)))

    @checks.sudo()
    @commands.command()
    async def role_blacklist(
            self, ctx: Context, target: Member, role_title: str, *, reason: str = "None given."
    ) -> None:
        """
        Permanently blacklist a user from a role.

        Should be called from within the guild the user will be rolebanned from.
        """

        role_title = role_title.lower()

        guild = ctx.guild
        target_role_id = self._get_role_id_from_title(guild, role_title)

        if target_role_id is None:
            role_names = ", ".join(self.get_guild_role_names(guild))
            await ctx.send("Invalid role name. Possible roles are {}.".format(role_names))
            return
        elif target is None:
            await ctx.send("Member not found.")
            return
        else:

            # Send a message, send a mod note and create a server log note
            if discord.utils.get(target.roles, name=role_title):
                # Note that we can still unban if the user doesn't have the given role
                await target.remove_roles(discord.utils.get(target.roles, name=role_title),
                                          reason="Removed due to blacklisting user.")

            self.config.hset("guild:{}:roles:roles:{}:bans".format(guild.id, role_title), target.id, -1)

            # I actually think the way I handled the expiring tags was super clever, should remember that this is a
            # thing in redis

            # self.config.set("user:{}:role_blacklist:{}".format(target.id, role_title), str(duration), ex=expire_time)

            server_logs = self.bot.get_cog("ServerLogs")
            if server_logs:

                await server_logs.handle_external_embed(ctx, "was blacklisted from {}.".format(role_title),
                                                        priority=True,
                                                        member=target,
                                                        **{"Moderator responsible": ctx.message.author.name,
                                                           "Reason": reason,
                                                           "Duration": "Permanent",
                                                           "Expires": "Never"})

            await ctx.send("User {} has been role-banned successfully.".format(str(target)))

    @checks.sudo()
    @commands.command(no_pm=True)
    async def unroleban(self, ctx: Context, target: Member, role_title: str, *, reason: str = "None given."):
        """
        Rescind a user's role-ban.
        """

        role_title = role_title.lower()

        guild = ctx.guild
        target_role_id = self._get_role_id_from_title(guild, role_title)

        if target_role_id is None:
            role_names = ", ".join(self.get_guild_role_names(guild))
            await ctx.send("Invalid role name. Possible roles are {}.".format(role_names))
            return
        elif target is None:
            await ctx.send("Member not found.")
            return
        else:

            self.config.hdel("guild:{}:roles:roles:{}:bans".format(guild.id, role_title), target.id)

            server_logs = self.bot.get_cog("ServerLogs")
            if server_logs:
                await server_logs.handle_external_embed(ctx, "was un-banned from having role {}.".format(role_title),
                                                        priority=True,
                                                        member=target,
                                                        **{"Moderator responsible": ctx.message.author.name,
                                                           "Reason": reason})

            await ctx.send("User {}'s role ban has been rescinded successfully.".format(str(target)))

    @checks.sudo()
    @commands.command(hidden=True)
    async def active_rolebans(self, ctx):
        """List current command blacklist. Mod only."""

        embed = discord.Embed(description="Active rolebans", color=discord.Color.orange())

        role_titles = self.get_guild_role_names(ctx.guild)

        fields_added = False

        for title in role_titles:
            try:
                bans = self.config.hgetall("guild:{}:roles:roles:{}:bans".format(ctx.guild.id, title))
                output_lines = []
                for user_id, ban_time in bans.items():
                    fields_added = True
                    member = discord.utils.get(ctx.guild.members, id=int(user_id))
                    if member is None:
                        user_name = "{} (not present in server)".format(user_id)
                    else:
                        user_name = "{} ({})".format(str(member), member.id)

                    ban_time = int(floor(float(ban_time)))

                    if ban_time == -1:
                        output_lines.append("{}: {}".format(user_name, "Permanent"))
                    else:
                        ts = self._format_datetime(datetime.datetime.fromtimestamp(ban_time))
                        output_lines.append("{}: {}".format(user_name, ts))

                embed.add_field(name="**{}**".format(title), value="\n".join(output_lines))

            except RedisError:
                pass

        await ctx.send(embed=embed) if fields_added else await ctx.send("No rolebans active on the server.")


def setup(bot):
    bot.add_cog(PMs(bot))
