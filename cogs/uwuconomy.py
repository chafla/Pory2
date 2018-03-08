"""don't uwu, $350 penalty"""
import re
import discord
from discord.ext import commands
from .utils import checks
from cogs.utils import rate_limits


class Uwuconomy:

    # active_guilds = [274731851661443074, 155800402514673664]

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config

        # TODO Bring all the uwuconomy stuff in under each channel's key
        self.active_guilds = list(self.config.smembers("config:uwuconomy:active_guilds"))
        self.active_channels = list(self.config.smembers("config:uwuconomy:active_chans"))
        self.muted_contexts = list(self.config.smembers("config:uwuconomy:muted"))

    @property
    def emoji(self):
        return discord.utils.get(self.bot.get_guild(78716585996455936).emojis, name="350dollarpenalty")

    @commands.command(hidden=True, pass_context=True)
    async def uwuconomy(self, ctx, *, user: discord.Member=None):
        rate_limits.MemeCommand.check_rate_limit(ctx, 0, priority_blacklist=[319309336029560834])
        if not user:
            user = ctx.message.author

        fines = self.config.get("user:{}:uwuconomy".format(user.id))
        fines = 0 if not fines else int(fines)

        embed = discord.Embed(color=discord.Color.blue(), description=("${}".format(-fines * 350)))

        embed.set_author(name="{.display_name}'s current balance".format(user), icon_url=user.avatar_url)
        await ctx.send(embed=embed)

    @checks.sudo()
    @commands.command(hidden=True, pass_context=True)
    async def toggle_uwuconomy(self, ctx, bounds: str=None):
        """Toggle uwuconomy for a single channel"""
        if bounds in ["serverwide", "server"]:
            target = ctx.message.guild
            kind = "guilds"
        else:
            target = ctx.message.channel
            kind = "chans"

        if self.config.sismember("config:uwuconomy:active_{}".format(kind), target.id):
            self.config.srem("config:uwuconomy:active_{}".format(kind), target.id)
            self.config.set("{}:{}:uwuconomy".format(kind[:-1], target.id), "disabled")
            action = "disabled"
        else:
            self.config.sadd("config:uwuconomy:active_{}".format(kind), target.id)
            self.config.set("{}:{}:uwuconomy".format(kind[:-1], target.id), "enabled")
            action = "enabled"

        # Hack because something doesn't seem to be working right

        cache = list(self.config.smembers("config:uwuconomy:active_{}".format(kind)))

        if kind == "guilds":
            self.active_guilds = cache
        else:
            self.active_channels = cache

        await ctx.send("uwuconomy is now {} in {}.".format(action, target.name))

    @checks.sudo()
    @commands.command(hidden=True)
    async def toggle_uwuconomy_reactions(self, ctx, bounds: str=None):

        name = "config:uwuconomy:muted"

        target = ctx.message.channel if bounds != "serverwide" else ctx.message.server

        if self.config.sismember(name, target.id):
            self.config.srem(name, target.id)
            action = "unmuted"
            self.muted_contexts.remove(str(target.id))
        else:
            self.config.sadd(name, target.id)
            action = "muted"
            self.muted_contexts.append(str(target.id))

        await ctx.send("uwuconomy reactions {} in {}.".format(action, target.name))

    async def on_message(self, message):
        if not isinstance(message.channel, discord.DMChannel) and \
            (str(message.guild.id) in self.active_guilds or str(message.channel.id) in self.active_channels) \
                and re.search("uwu", message.content, re.IGNORECASE) and not message.content.startswith("!uwu"):
            if not (str(message.channel.id) in self.muted_contexts or str(message.guild.id) in self.muted_contexts):
                await message.add_reaction(self.emoji)

            self.config.incr("user:{}:uwuconomy".format(message.author.id))
            self.config.sadd("config:uwuconomy:tracked_users", message.author.id)


def setup(bot):
    bot.add_cog(Uwuconomy(bot))
