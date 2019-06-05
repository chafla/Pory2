
import asyncio
import datetime
import logging
import time

from typing import Union, List

import discord
from discord import (
    GroupChannel, Guild, Member, Message, TextChannel, VoiceChannel
)
from discord.ext import commands
from discord.ext.commands import Bot, Context

from .utils import checks


T_GuildChannel = Union[GroupChannel, TextChannel, VoiceChannel]


log = logging.getLogger()


class Logs:
    """Log channels"""
    # TODO: Refactor because it comes directly from the old code

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.log_old_markovs = False
        self.lock = asyncio.Lock()
        self.config = self.bot.config

        self.bot.loop.create_task(self.initialize_channels())

        self._markov_guild_cache = self.config.smembers("config:markov:active_guilds")

    @property
    def markov_guilds(self) -> List[int]:
        return [int(i) for i in self._markov_guild_cache]

    @property
    def guild(self) -> Guild:
        return self.bot.get_guild(111504456838819840)

    async def initialize_channels(self) -> None:
        await self.bot.wait_until_ready()
        guild = self.bot.get_guild(111504456838819840)
        for channel in guild.channels:
            self.config.sadd("chan:{}:names".format(channel.id), channel.name)

    @checks.sudo()
    @commands.command()
    async def register_markov_guild(self, ctx: Context, guild_id: int=None):
        if guild_id is None:
            guild_id = ctx.guild.id

        self.config.sadd("config:markov:active_guilds", guild_id)

        self._markov_guild_cache.add(guild_id)

        await ctx.send("Guild added.")

    @checks.in_pm()
    @commands.command()
    async def allow_logging(self, ctx: Context) -> None:
        """Allow pory to log your messages for usermarkov in accordance with TOS"""
        def check(m):
            return m.author == ctx.message.author and m.content.lower() == "i agree"\
                   and m.channel == ctx.message.channel
        await ctx.send("By replying `I agree` you consent to having Porygon2 log your messages **in all shared servers"
                       "** for use in commands such as usermarkov and get_wc. You can, at any time, revoke this "
                       "permission with '!disable_logging`, however this will not delete already saved logs.")
        msg = await self.bot.wait_for("message", check=check)

        if msg is not None:
            await ctx.send("Logging is now enabled.")
            self.config.set("user:{}:logs:enabled".format(ctx.message.author.id), "True")

    @checks.in_pm()
    @commands.command()
    async def disable_logging(self, ctx: Context) -> None:
        self.config.delete("user:{}:logs:enabled".format(ctx.message.author.id))
        await ctx.send("You've now disabled logging for usermarkov and get_wc.")

    async def on_message(self, message: Message) -> None:

        if message.author.id == self.bot.user.id:
            return

        elif isinstance(message.channel, discord.DMChannel):

            log.info("New pm from {0.author.name} ({0.author.id}): {0.content}".format(message))
            if message.content in ["confirm", "!set18"]:
                return
            embed = discord.Embed(title="New PM from {0.name}#{0.discriminator}".format(message.author),
                                  color=discord.Color.orange())
            server_logs = self.bot.get_cog("ServerLogs")
            embed = server_logs.format_embed(embed, message.author)
            embed.add_field(name="Content", value=message.content)

            try:
                dest = self.bot.get_channel(198526174735892480)
                await dest.send(embed=embed)
            except discord.HTTPException:
                pass

            return

        elif message.guild == self.guild:  # Pokemon server only
            # Full logs w/ timestamps for archival purposes.
            with open(r'message_cache/channels/{0}.txt'.format(message.channel.id), 'a',
                      encoding='utf-8') as tmp:  # Log general chat w/ usernames
                ts = time.time()
                ts = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                with await self.lock:
                    if not message.attachments:
                        tmp.write("[{0}] ({1}) {2}: {3}\n".format(ts, message.author.id, message.author.name,
                                                                  message.content))
                    else:
                        tmp.write("[{0}] ({1}) {2}: {3} [ATTACHMENTS] {4}\n".format(ts, message.author.id,
                                                                                    message.author.name,
                                                                                    message.content,
                                                                                    message.attachments))

        # General chat for newmarkov
        if self.log_old_markovs:
            if message.channel.id == 111504456838819840:  # Log general chat for markov
                with open('message_cache/messages_general_chat.txt', 'a', encoding='utf-8') as tmp:
                    tmp.write(message.content + '\n')

            # Off topic
            elif message.channel.id == 137986625039892480:
                with open('message_cache/messages_off_topic.txt', 'a', encoding='utf-8') as tmp:
                    tmp.write(message.content + '\n')

        # Logs for usermarkov
        # excluding serious chat
        markov_guild_whitelist = self.markov_guilds

        markov_channel_blacklist = [319309418204233740,
                                    274734349981712385,
                                    338455130531692545,
                                    246279583807045632]
        # lol this is pretty messy
        if message.guild.id in markov_guild_whitelist and message.channel.id not in markov_channel_blacklist \
                and message.channel.name != "earnest_chat":

            # If in r/pokemon, users have the verified role, otherwise they should have used !enable_logging
            if (message.guild.id == 111504456838819840 and discord.utils.get(message.author.roles,
                                                                             id=349077573977899011))\
                    or self.config.get("user:{}:logs:enabled".format(message.author.id)) is True:

                with open(r'message_cache/users/{0}.txt'.format(message.author.id), 'a', encoding='utf-8') as tmp:
                    tmp.write("{0}\n".format(message.content))

    async def on_message_edit(self, before: Message, after: Message) -> None:
        if not isinstance(before.channel, discord.DMChannel) and before.guild == self.guild \
                and before.content != after.content:  # Don't catch embed updates
            with open(r'message_cache/channels/{0}.txt'.format(before.channel.id), 'a',
                      encoding='utf-8') as tmp:  # Log general chat w/ usernames
                ts = time.time()
                ts = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                tmp.write("[{0}] [EDITED] ({1}) {2}: {3} \n".format(ts, before.author.id, before.author.name,
                                                                    after.content))

    async def on_message_delete(self, message: Message) -> None:
        if not isinstance(message.channel, discord.DMChannel) and message.guild == self.guild:
            with open(r'message_cache/channels/{0}.txt'.format(message.channel.id), 'a',
                      encoding='utf-8') as tmp:  # Log general chat w/ usernames
                ts = time.time()
                ts = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                tmp.write("[{0}] [DELETED] ({1}) {2}: {3} \n".format(ts, message.author.id,
                                                                     message.author.name, message.content))

    async def on_channel_update(
            self, before: T_GuildChannel, after: T_GuildChannel
    ) -> None:
        # For use with r/pokemon's regular report
        if after.guild == self.guild and before.name != after.name:
            self.config.sadd("chan:{}:names".format(before.id), after.name)

    async def on_channel_delete(self, channel: T_GuildChannel) -> None:
        if not isinstance(channel, discord.DMChannel) and channel.guild == self.guild:
            self.config.set("chan:{}:deleted".format(channel.id), datetime.datetime.now())

    async def on_channel_create(self, channel: T_GuildChannel) -> None:
        if not isinstance(channel, discord.DMChannel) and channel.guild == self.guild:
            self.config.sadd("chan:{}:names".format(channel.id), channel.name)

    async def on_member_update(self, before: Member, after: Member) -> None:
        if before.nick != after.nick and after.guild == self.guild:
            # Keep track of member nicknames
            self.config.sadd("user:{}:nicks".format(before.id), before.nick, after.nick)

        elif before.name != after.name and after.guild == self.guild:
            # Keep track of usernames
            self.config.sadd("user:{}:names".format(before.id), before.name, after.name)


def setup(bot: Bot) -> None:
    bot.add_cog(Logs(bot))
