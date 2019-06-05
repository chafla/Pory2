"""
Administrative commands for pory. A lot of them used from my HockeyBot,
including the cog importing commands and eval, which came from RoboDanny.
Copyright (c) 2015 Rapptz
"""

import inspect
import logging
import re
import subprocess
import traceback

from asyncio import sleep
from os import getcwd
from time import time
from time import monotonic
from typing import Union

import discord
from discord import DMChannel, Game, Message, TextChannel
from discord.ext import commands
from discord.ext.commands import Bot, Context

from .utils import checks, rate_limits, utils

log = logging.getLogger()


class Admin:

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.config = bot.config

        self.bot.loop.create_task(self.send_message_on_restart())

    async def send_message_on_restart(self) -> None:
        await self.bot.wait_until_ready()
        hash_name = "config:admin:last_force_kill"
        if self.config.exists(hash_name):
            force_kill_info = self.config.hgetall(hash_name)
            if force_kill_info:
                channel = self.bot.get_channel(int(force_kill_info["channel_id"]))
                await channel.send("Restarted in {}s.".format(int(time() - int(float(force_kill_info["timestamp"])))))
                self.config.delete(hash_name)

    async def git_pull(
            self, channel: Union[DMChannel, TextChannel]
    ) -> None:
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

    @checks.sudo()
    @commands.command()
    async def load(
            self, ctx: Context, *, module: str, verbose: bool=False
    ) -> None:
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

    @checks.sudo()
    @commands.command()
    async def unload(self, ctx: Context, *, module: str) -> None:
        """Unloads a module."""
        try:
            self.bot.unload_extension(module)
        except Exception as e:
            await ctx.send('{}: {}'.format(type(e).__name__, e))
        else:
            await ctx.send('Module unloaded successfully.')

    @checks.sudo()
    @commands.command(name='reload')
    async def _reload(self, ctx: Context, *, module: str) -> None:
        """Reloads a module."""
        t = monotonic()
        try:
            self.bot.unload_extension(module)
            self.bot.load_extension(module)
        except Exception as e:
            await ctx.send('Failed.')
            await ctx.send('{}: {}'.format(type(e).__name__, e))
            log.exception("Exception occurred when reloading cog")
            monotonic()  # Resetting it
        else:
            await ctx.send("Module loaded successfully.\nTotal time: `{:.0f}ms`.".format((monotonic() - t) * 1000))

    # Thanks to rapptz
    @checks.sudo()
    @commands.command()
    async def eval(self, ctx: Context, *, code: str) -> None:
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

    @checks.sudo()
    @commands.command()
    async def exec(self, ctx: Context, *, code: str) -> None:
        """Evaluates python code on multiple lines"""

        env = {
            'bot': ctx.bot,
            'ctx': ctx,
            'message': ctx.message,
            'author': ctx.message.author,
            'channel': ctx.message.channel,
        }
        env.update(globals())

        exec_test = re.compile(
            r"(?:^(?:(?:for)|(?:def)|(?:while)|(?:if)))|"
            r"(?:^([a-z_][A-z0-9_\-.]*)\s?[+\-\\*]?=)"
        )
        cmds = []  # `commands` shadows import from discord.ext

        print(code.split(';'))

        for command in code.split(';'):
            try:
                command = command.strip()
                is_exec = exec_test.match(command)

                if is_exec:
                    exec(command, env)
                    result = env.get(is_exec.group(1), None)
                    if inspect.isawaitable(result):
                        result = await result
                        env.update({is_exec.group(1): result})
                else:
                    result = eval(command, env)
                    if inspect.isawaitable(result):
                        result = await result

            except Exception as e:
                result = "{}: {}".format(type(e).__name__, e)

            cmds.append([
                command,
                result
            ])

        response_str = "```py\n" + '\n'.join(
            [">>> {}\n{}".format(command, result) for command, result in cmds]) + "\n```"

        if not self.bot.user.bot:
            await ctx.message.edit(response_str)
        else:
            await ctx.send(response_str)

    @checks.sudo()
    @commands.command()
    async def get_invite(self, ctx: Context):
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
    @commands.command(aliases=["rip", "F", "f"])
    async def kill(self, ctx: Context, *, args: str=None) -> None:
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
    async def set_auto_git_update(
            self, ctx: Context, webhook_author_id: str=None
    ) -> None:
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
    async def git_update(self, ctx: Context) -> None:
        await self.git_pull(ctx.message.channel)

    @checks.sudo()
    @commands.command(aliases=["echo"])
    async def say(self, ctx: Context, dest_id: int, *, content: str) -> None:
        """Send a message to a channel or user"""
        channel = self.bot.get_channel(dest_id)
        await channel.send(content)

    @checks.sudo()
    @commands.command(name="blacklist_memes")
    async def blacklist_memes_from_channel(
            self, ctx: Context, channel_id: str=None
    ) -> None:
        """Add an entry to the rate_limit channel blacklist.
        If an ID is not passed in, use the current channel."""
        if channel_id is None:
            channel_id = ctx.message.channel.id

        self.config.sadd("config:rate_limits:chan_blacklist", channel_id)
        await ctx.send("\N{OK HAND SIGN}")

    @checks.sudo()
    @commands.command(name="unblacklist_memes")
    async def unblacklist_memes_from_channel(
            self, ctx: Context, channel_id: str=None
    ) -> None:
        if channel_id is None:
            channel_id = ctx.message.channel.id

        self.config.srem("config:rate_limits:chan_blacklist", channel_id)
        await ctx.send("\N{OK HAND SIGN}")

    @checks.sudo()
    @commands.command()
    async def channel_blacklist(self, ctx: Context) -> None:
        """Show the active server blacklist"""
        output = "Currently blacklisted channels:```\n"
        for channel_id in await rate_limits.MemeCommand.get_blacklist():
            channel = discord.utils.get(ctx.message.guild.channels, id=channel_id)
            if channel:
                output += channel.name + "\n"
        output += "```"
        await ctx.send(output)

    @checks.sudo()
    @commands.command(alises=["cd_coeff"])
    async def set_cooldown_coeff(
            self, ctx: Context, ratio: float=1.0
    ) -> None:
        """Adjust cooldown settings for current channel"""
        self.config.set("chan:{}:rate_limits:cooldown_ratio".format(ctx.channel.id), ratio)
        await ctx.send("Cooldown multiplier for #{} is now set to {}.".format(ctx.message.channel.name, ratio))

    @checks.sudo()
    @commands.command()
    async def rate_limit_status(self, ctx: Context) -> None:
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
    @commands.command()
    async def set_game(self, ctx: Context, *, game: str=None) -> None:
        if game:
            await self.bot.change_presence(game=Game(name=game))
        else:
            await self.bot.change_presence(game=None)
        await ctx.send("```\nGame set to {}.```".format(game))

    @checks.sudo()
    @commands.command()
    async def get_config(self, ctx: Context, target: str="channel") -> None:
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

    async def on_message(self, message: Message) -> None:
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


def setup(bot: Bot) -> None:
    bot.add_cog(Admin(bot))
