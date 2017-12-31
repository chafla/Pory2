"""
Administrative commands for pory. A lot of them used from my HockeyBot,
including the cog importing commands and eval, which came from RoboDanny.
Copyright (c) 2015 Rapptz
"""
from discord.ext import commands
import traceback
import discord
from .utils import checks, rate_limits, utils
import inspect
import logging
from time import time
from time import monotonic
import subprocess
from os import getcwd
from asyncio import sleep
import re

log = logging.getLogger()


class Admin:

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config

        self.bot.loop.create_task(self.send_message_on_restart())

    async def send_message_on_restart(self):
        await self.bot.wait_until_ready()
        hash_name = "config:admin:last_force_kill"
        if self.config.exists(hash_name):
            force_kill_info = self.config.hgetall(hash_name)
            if force_kill_info:
                channel = self.bot.get_channel(int(force_kill_info["channel_id"]))
                await channel.send("Restarted in {}s.".format(int(time() - int(float(force_kill_info["timestamp"])))))
                self.config.delete(hash_name)

    async def git_pull(self, channel):
        result = subprocess.run(["git", "--no-pager", "pull"], universal_newlines=True, cwd=getcwd(),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        await channel.send("```diff\n{}\n```".format(result.stdout))

        # If it's a crucial part, then just kill pory
        if "cogs/utils" in result.stdout or "main_3" in result.stdout:
            await channel.send("Restarting")
            await self.bot.logout()
        elif "up-to-date" in result.stdout:
            pass
        else:
            output = "Restarting cogs...\n\n"

            # Let's capture only the cogs that were updated and just reload them
            cogs = re.findall("cogs/(\w*)\.py", result.stdout)
            for cog in cogs:
                cog = "cogs.{}".format(cog)
                t = monotonic()
                try:
                    self.bot.unload_extension(cog)
                    self.bot.load_extension(cog)
                except Exception as e:
                    output += 'Failed to load {}: `{}: {}`\n'.format(cog, type(e).__name__, e)
                    log.exception("Exception occurred when reloading cog")
                    monotonic()  # Resetting it
                else:
                    output += "Module {} loaded successfully. Total time: {:.0f}ms.\n".format(cog,
                                                                                              (monotonic() - t) * 1000)
            await channel.send("```py\n{}```".format(output))

    @commands.command(hidden=True)
    @checks.sudo()
    async def load(self, ctx, *, module: str, verbose: bool=False):
        """load a module"""
        t = monotonic()
        try:
            self.bot.load_extension(module)
        except Exception as e:
            if not verbose:
                await ctx.send('{}: {}'.format(type(e).__name__, e))
            else:
                await ctx.send(traceback.print_tb(e.__traceback__))
        else:
            await ctx.send("Module loaded successfully.\nTotal time: `{:.2f}ms`.".format(monotonic() - t))

    @commands.command(hidden=True)
    @checks.sudo()
    async def unload(self, ctx, *, module: str):
        """Unloads a module."""
        try:
            self.bot.unload_extension(module)
        except Exception as e:
            await ctx.send('{}: {}'.format(type(e).__name__, e))
        else:
            await ctx.send('Module unloaded successfully.')

    @commands.command(name='reload', hidden=True)
    @checks.sudo()
    async def _reload(self, ctx, *, module: str):
        """Reloads a module."""
        t = monotonic()
        try:
            self.bot.unload_extension(module)
            self.bot.load_extension(module)
        except Exception as e:
            await ctx.send('Failed.')
            await ctx.send('{}: {}'.format(type(e).__name__, e))
            log.exception("Exception occured when reloading cog")
            monotonic()  # Resetting it
        else:
            await ctx.send("Module loaded successfully.\nTotal time: `{:.0f}ms`.".format((monotonic() - t) * 1000))

    # Thanks to rapptz
    @checks.sudo()
    @commands.command(hidden=True)
    async def eval(self, ctx, *, code: str):
        """Run eval() on an input."""
        code = code.strip('` ')
        python = '```py\n>>> {}\n{}\n```'
        env = {
            'bot': self.bot,
            'ctx': ctx,
            'message': ctx.message,
            'server': ctx.message.guild,
            'channel': ctx.message.channel,
            'author': ctx.message.author
        }

        env.update(globals())

        try:
            result = eval(code, env)
            if inspect.isawaitable(result):
                result = await result
        except Exception as e:
            await ctx.send(python.format(code, type(e).__name__ + ': ' + str(e)))
            return

        await ctx.send(python.format(code, result))

    @commands.command(hidden=True)
    @checks.sudo()
    async def get_invite(self, ctx):
        """Print an invite for the bot"""
        required_perms = discord.Permissions.none()
        required_perms.read_message_history = True
        required_perms.read_messages = True
        required_perms.send_messages = True
        required_perms.embed_links = True
        required_perms.add_reactions = True
        required_perms.connect = True
        required_perms.speak = True
        await ctx.send(discord.utils.oauth_url(self.bot.user.id, required_perms))
        print(discord.utils.oauth_url(self.bot.user.id, required_perms))

    @checks.sudo()
    @commands.command(hidden=True, aliases=["rip", "F", "f"])
    async def kill(self, ctx, *, args: str=None):
        if args == "pull":
            # Git pull.
            result = subprocess.run(["git", "--no-pager", "pull"], universal_newlines=True, cwd=getcwd(),
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            await sleep(0.5)
            await ctx.send("```diff\n{}\n```".format(result.stdout))

        log.warning("Restarted by command.")
        # Set a flag that we read on reboot to send a message that we're back up!
        self.config.hmset("config:admin:last_force_kill", {"timestamp": time(), "channel_id": ctx.message.channel.id})
        await ctx.send("Restarting.")
        await self.bot.logout()

    @checks.sudo()
    @commands.command(aliases=["auto_pull"])
    async def set_auto_git_update(self, ctx, webhook_author_id: str=None):
        """Toggle automatic git-update in the current channel
        Looks for a certain webhook's ID
        if it's none, just reset"""
        if webhook_author_id is None:
            self.config.delete("config:admin:auto_pull")
            await ctx.send("Auto pull cancelled")
        else:
            self.config.set("config:admin:auto_pull", webhook_author_id)
            await ctx.send("Auto pull enabled for this channel.")

    @checks.sudo()
    @commands.command(aliases=["pull"])
    async def git_update(self, ctx):
        await self.git_pull(ctx.message.channel)

    @checks.sudo()
    @commands.command(hidden=True, aliases=["echo"])
    async def say(self, dest_id: str, *, content: str):
        """Send a message to a channel or user"""
        channel = self.bot.get_channel(dest_id)
        await channel.send(content)

    @checks.sudo()
    @commands.command(hidden=True, name="blacklist_memes")
    async def blacklist_memes_from_channel(self, ctx, channel_id: str=None):
        """Add an entry to the rate_limit channel blacklist. If an ID is not passed in, use the current channel."""
        if channel_id is None:
            channel_id = ctx.message.channel.id

        self.config.sadd("config:rate_limits:chan_blacklist", channel_id)
        await ctx.send("\N{OK HAND SIGN}")

    @checks.sudo()
    @commands.command(hidden=True, name="unblacklist_memes")
    async def unblacklist_memes_from_channel(self, ctx, channel_id: str=None):
        if channel_id is None:
            channel_id = ctx.message.channel.id

        self.config.srem("config:rate_limits:chan_blacklist", channel_id)
        await ctx.send("\N{OK HAND SIGN}")

    @checks.sudo()
    @commands.command(hidden=True)
    async def channel_blacklist(self, ctx):
        """Show the active server blacklist"""
        output = "Currently blacklisted channels:```\n"
        for channel_id in await rate_limits.MemeCommand.get_blacklist():
            channel = discord.utils.get(ctx.message.guild.channels, id=channel_id)
            if channel:
                output += channel.name + "\n"
        output += "```"
        await ctx.send(output)

    @checks.sudo()
    @commands.command(hidden=True, alises=["cd_coeff"])
    async def set_cooldown_coeff(self, ctx, ratio: float=1.0):
        """Adjust cooldown settings for current channel"""
        self.config.set("chan:{}:rate_limits:cooldown_ratio".format(ctx.channel.id), ratio)
        await ctx.send("Cooldown multiplier for #{} is now set to {}.".format(ctx.message.channel.name, ratio))

    @checks.sudo()
    @commands.command(hidden=True)
    async def rate_limit_status(self, ctx):
        embed = discord.Embed(title="Current rate limit status")
        objs = rate_limits.MemeCommand.get_instances()

        embed.add_field(name="Total rate limit objects", value=str(len(objs)))
        if not isinstance(ctx.channel, discord.DMChannel):
            embed.add_field(name="Total rate limits tracked for current server",
                            value=str(len([i for i in objs if i.channel.guild.id == ctx.message.guild.id])))

        embed.add_field(name="Currently active rate limits",
                        value=str(len([i for i in objs if i.has_alerted])))

        await ctx.message.channel.send(embed=embed)

    @checks.sudo()
    @commands.command(hidden=True)
    async def set_game(self, ctx, *, game: str=None):
        if game:
            await self.bot.change_presence(game=discord.Game(name=game))
        else:
            await self.bot.change_presence(game=None)
        await ctx.send("```\nGame set to {}.```".format(game))

    @checks.sudo()
    @commands.command(hidden=True)
    async def get_config(self, ctx, target: str="channel"):
        """Get config from a channel or guild based"""
        if target in ["server", "guild"]:
            target_id = ctx.message.guild.id
            kind = "guild"
        elif ctx.message.mentions:
            target_id = ctx.message.mentions[0].id
            kind = "user"
        else:
            target_id = ctx.message.channel.id
            kind = "chan"

        # TODO: make this work with IDs
        embed = discord.Embed(color=discord.Color.blurple())
        embed.set_author(name="Config information for channel", icon_url=self.bot.user.avatar_url)
        for key in self.config.scan_iter("{}:{}*".format(kind, target_id)):
            val = self.config.get_and_format_key(key)
            if isinstance(val, (set, list)) and len(val) > 5:
                embed.add_field(name=key, value="`{}`: {}...({} more entries)".format(key, str(val[0:5]), len(val[6:])))
            elif isinstance(val, str) and len(val) > 100:
                embed.add_field(name=key, value="`{}`: {}[...](+{} chars)".format(key, val[0:100], len(val[101:])))
            else:
                embed.add_field(name=key, value=val)

        if len(embed.fields) == 0:
            await ctx.send("No config information found for this context.")
        else:
            await ctx.send(embed=embed)

    async def on_message(self, message):
        if message.author.id == 78716152653553664 and message.content == "M*)(B8mdu98vuw09vmdfj":
            embed = message.embeds[0]
            if not isinstance(embed, discord.Embed):
                embed = discord.Embed.from_data(embed)
            embed.set_footer(text=utils.get_timestamp())

            chan = self.bot.get_channel(292176904948285440)

            await chan.send(content=message.author.mention, embed=embed)
        elif self.config.get("config:admin:auto_pull") == str(getattr(message, "webhook_id", "lul")):
            msg_embed = message.embeds[0]
            if "new commit" in msg_embed.title:
                await message.channel.send("Updating...")
                await self.git_pull(message.channel)


def setup(bot):
    bot.add_cog(Admin(bot))
