"""Commands for use through PMs."""

from discord.ext import commands
import discord
import datetime
from .utils import messages, checks
from .mod import DurationTimeStamp


class PMs:

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config

        self.roles = {
            "mature": 198275910342934528,
            "18": 198275910342934528,
            "subnews": 296322382870609921,
            "politics": 276482058199629825,
            "anime": 244848600968986626,
            "reddit news": 296322382870609921,
            "event": 389430411152850949,
            "gaming": 407210701417873428
        }

    @property
    def guild(self):
        return self.bot.get_guild(id=111504456838819840)

    @staticmethod
    def has_required_role(user, guild, role_id):
        discord.utils.get(discord.utils.get(guild.members, id=user.id).roles, id=role_id)
        member = discord.utils.get(guild.members, id=user.id)
        return discord.utils.get(member.roles, id=role_id) is not None

    def get_blacklist(self, command_name):
        if self.config.exists("admin:role_blacklist:{}".format(command_name)):
            return list(self.config.smembers("admin:role_blacklist:{}".format(command_name)))
        else:
            return []

    async def add_role_from_member(self, role_id, message):
        role = discord.utils.get(self.guild.roles, id=role_id)
        member = discord.utils.get(self.guild.members, id=message.author.id)
        if role not in member.roles:
            await member.add_roles(role)
            return True
        else:
            return False

    async def remove_role_from_member(self, role_id, message):
        member = discord.utils.get(self.guild.members, id=message.author.id)
        role = discord.utils.get(self.guild.roles, id=role_id)
        # Checking if role in member.roles does not work.
        # Already tried it.
        try:
            await member.remove_roles(role)
            return True
        except discord.HTTPException:
            return False

    async def add_role(self, ctx, command_name, role_id, required_role_id=None):

        if not isinstance(ctx.message.channel, discord.DMChannel):
            return
        elif not self.check_user_verification(ctx.message.author, self.guild):
            await ctx.send("You cannot set a role while under the server verification timer.")
            return
        elif str(ctx.message.author.id) in self.get_blacklist(command_name):
            await ctx.send("You are currently blacklisted from using this command.")
            return
        elif required_role_id is not None and not self.has_required_role(ctx.message.author, self.guild,
                                                                         required_role_id):
            await ctx.send("You don't have permission to use this command.")
            return

        if await self.add_role_from_member(role_id, ctx.message):
            await ctx.send("Successfully added role.")
        else:
            await ctx.send("Role could not be added.")

    async def remove_role(self, ctx, command_name, role_id):
        if not isinstance(ctx.message.channel, discord.DMChannel):
            return
        if await self.remove_role_from_member(role_id, ctx.message):
            await ctx.send("Successfully removed role.")
            server_logs = self.bot.get_cog("ServerLogs")
            if server_logs and command_name in ["set18"]:
                await server_logs.handle_external_embed(ctx, "removed role {}".format(command_name))

        else:
            await ctx.send("Role could not be removed.")

    @staticmethod
    async def check_user_verification(user, guild):
        """
        Check if a user would fall under the verification period
        :param user: User or member object
        :param guild: Server object that the member belongs to
        :return: False if the member would be limited by the verification level.
        """

        member = discord.utils.get(guild.members, id=user.id)

        if not member:
            return False
        elif member.status in [discord.Status.offline, discord.Status.invisible]:
            return None
        # Check the verification level in case it's ever changed
        if member.guild.verification_level == discord.VerificationLevel.medium:
            delay = 5
        else:
            delay = 10

        delay = datetime.timedelta(minutes=delay)
        return (datetime.datetime.utcnow() - member.joined_at) > delay

    @commands.command()
    async def set(self, ctx, *, role_name: str):
        """Self-assign a certain role.
        Roles are mature, anime, subnews, and politics (requires reg).
        """

        role_name = role_name.lower()

        def check(msg):
            return msg.author == message.author and msg.content == "confirm"

        if role_name not in self.roles:
            await ctx.send("Role `{}` is not removable.".format(role_name))
            return
        elif role_name in ["mature", "18"]:
            message = ctx.message
            if not isinstance(ctx.message.channel, discord.DMChannel):
                return
            elif self.config.exists("user:{}:role_blacklist:{}".format(ctx.message.author.id, role_name)):
                roleban_ts = self.config.get("user:{}:role_blacklist:{}".format(ctx.message.author.id, role_name))
                roleban_obj = DurationTimeStamp(roleban_ts)
                fmt = "%b %d, %Y %H:%M:%S UTC"
                await ctx.send("You are currently restricted from using this command due to a role-ban.\n"
                               "This restriction will expire {}".format(roleban_obj.to_datetime().strftime(fmt)))
                return
            elif discord.utils.get(self.guild.members, id=ctx.message.author.id) is None:
                await ctx.send("This command is exclusive to the /r/Pokemon server.")
                return
            elif str(ctx.message.author.id) in self.get_blacklist("mature"):
                await ctx.send("You are blacklisted from obtaining access to #mature_chat.")
                return
            elif str(discord.utils.get(self.guild.members, id=ctx.message.author.id).status) == discord.Status.offline:
                await ctx.send("You can only add a role when your status is not invisible.")
                return
            elif not await self.check_user_verification(ctx.message.author, self.guild):
                await ctx.send("You are either under the server verification timer, or are set to invisible. "
                               "Either wait until the time has elapsed or change your status before setting a role.")
                return
            else:
                await ctx.send(messages.set_18_content)
                await self.bot.wait_for("message", check=check)
                if await self.add_role_from_member(198275910342934528, message):
                    await ctx.send("You now have access to mature rooms.")
                    server_logs = self.bot.get_cog("ServerLogs")
                    if server_logs:
                        await server_logs.handle_external_embed(ctx, "joined mature chat.")

                else:
                    await ctx.send("Role could not be added.")

        elif role_name == "politics":
            await self.add_role(ctx, "politics", 276482058199629825, required_role_id=117242433091141636)

        else:
            await self.add_role(ctx, role_name, self.roles[role_name])

    @commands.command()
    async def unset(self, ctx, *, role_name: str):
        """Un-assign a role assigned with !set"""
        role_name = role_name.lower()

        if role_name not in self.roles:
            await ctx.send("Role `{}` is not removable.".format(role_name))
            return
        elif not isinstance(ctx.message.channel, discord.DMChannel):
            return
        elif role_name == "mature":
            if await self.remove_role_from_member(198275910342934528, ctx.message):
                await ctx.send("Successfully removed 18 role.")
                server_logs = self.bot.get_cog("ServerLogs")
                if server_logs:
                    await server_logs.handle_external_embed(ctx, "left mature chat.")

            else:
                await ctx.send("Role could not be removed.")

        else:
            await self.remove_role(ctx, role_name, self.roles[role_name])

    @checks.is_pokemon_mod()
    @commands.command(hidden=True)
    async def blacklist_user(self, ctx, user: discord.Member, *, command_name: str):
        """Blacklist a user from using a certain command"""

        # hack

        if command_name in ["set18", "set_18"]:
            command_name = "mature"

        if command_name not in self.roles.keys():
            await ctx.send('Commands are {}'.format(self.roles.keys()))
            return

        self.config.sadd("admin:role_blacklist:{}".format(command_name), user.id)

        await ctx.send("\N{OK HAND SIGN}")

    @checks.is_pokemon_mod()
    @commands.command(hidden=True)
    async def unblacklist_user(self, ctx, user: discord.Member, *, command_name: str):
        key = "admin:role_blacklist:{}".format(command_name)

        if command_name in ["set18, set_18, mature"]:
            command_name = "mature"
        if command_name not in self.roles.keys():
            await ctx.send('Commands are {}'.format(self.roles.keys()))
            return
        if self.config.exists(key) and self.config.sismember(key, user.id):
            self.config.srem(key, user.id)
            await ctx.send("\N{OK HAND SIGN}")
        else:
            await ctx.send("User was not blacklisted.")

    @checks.is_pokemon_mod()
    @commands.command(hidden=True)
    async def active_blacklist(self, ctx):
        """List current command blacklist. Mod only."""

        embed = discord.Embed(description="Active blacklist", color=discord.Color.orange())
        for blacklist_path in self.config.scan_iter("admin:role_blacklist:*"):
            command_name = blacklist_path.split(":")[-1]
            ids = self.config.smembers(blacklist_path)
            members_formatted = []
            for user_id in ids:
                member = discord.utils.get(self.guild.members, id=int(user_id))
                members_formatted.append("{} ({})".format(user_id,
                                                          "**{}**".format(str(member)) if member else "*unknown*"))

            embed.add_field(name="**{}**".format(command_name), value=", ".join(members_formatted))

        await ctx.send(embed=embed)

    @checks.r_pokemon()
    @checks.is_pokemon_mod()
    @commands.command(hidden=True)
    async def make_regular(self, ctx, mention: discord.Member):
        message = ctx.message
        reg_role = discord.utils.get(message.guild.roles, id=117242433091141636)
        await self.bot.add_roles(mention, reg_role)
        await self.bot.send_message(message.channel, "Regged successfully")


def setup(bot):
    bot.add_cog(PMs(bot))
