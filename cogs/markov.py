"""Markov generating and handling code"""

import json
import logging

from inspect import iscoroutinefunction
from io import StringIO
from typing import Any, Callable, Optional, Union  # , Coroutine

import discord
import markovify

from discord import Guild, Member, Role
from discord.ext import commands
from discord.ext.commands import Bot, Context

from .utils import markov2, utils, checks
from .utils.rate_limits import MemeCommand
from .utils import gizoogle


"""
class MarkovifyTextList(markovify.Text):
    # Small definition that's needed to make sure markovify works as intended
    def sentence_split(self, text):
        return text
"""


log = logging.getLogger()


class Markov:

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.config = bot.config
        self.currently_generating = []

        self._lewdmarkov_model = None

    @property
    def r_pkmn(self) -> Guild:
        return self.bot.get_guild(111504456838819840)

    @property
    def verified_role(self) -> Role:
        return discord.utils.get(self.r_pkmn.roles, id=349077573977899011)

    def _is_verified(self, ctx: Context) -> bool:
        if isinstance(ctx.message.channel, discord.DMChannel):  # actually a user, meaning it's in DMs
            return True
        elif ctx.message.author.guild == self.r_pkmn:
            return self.verified_role in ctx.message.author.roles
        else:
            return self.config.get("user:{}:logs:enabled".format(ctx.message.author.id)) is True

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

    async def _generate_lewdmarkov_model(self) -> None:
        # I tried working with this method, but it would just hang the bot. Probably put too much load on it.
        try:
            with open(r'cogs/utils/loodmarkov_model.json', 'r', encoding='utf-8') as g:
                outfile = json.load(g)
                markov = markovify.Text.from_json(outfile)
                self._lewdmarkov_model = markov
                log.info("Loaded lewdmarkov model.")
        except FileNotFoundError:
            log.warning("Count not find markov file.")
            return

    async def _get_member(self, ctx: Context, user: str=None) -> Optional[Member]:
        message = ctx.message

        if len(message.mentions) > 0:
            member = message.mentions[0]

        elif user is not None and user != "self":
            # Find user with the matching submitted name
            # Check if the username matches exactly, then if it's like the start of a display_name
            member = discord.utils.get(message.guild.members, name=user)
            if member is None:
                member = discord.utils.find(
                    lambda m: m.display_name.startswith(user),
                    self.bot.get_all_members()
                )
                if member is None:
                    await ctx.send("User not found.")
                    return
                elif ctx.guild != self.r_pkmn and self.verified_role not in member.roles:
                    await ctx.send("Member not verified.")
                    return

        else:
            member = message.author

        return member

    async def gen_markov(
            self, ctx: Context,
            markov_type: str=None,
            user: str=None,
            path: Union[str, StringIO]=None,
            modifier_func: Optional[
                Union[
                    Callable[[str], Union[str, Any]]
                ]
            ]=None,
            use_newlines: bool=True,
            state_size: int=2
    ) -> None:
        # `Any]]` above is `Coroutine[None, None, str]]]`
        assert path is not None or markov_type is not None
        old_lib = False
        if use_newlines:
            cls = markovify.NewlineText
        else:
            cls = markovify.Text
        # only allow TTS if in bot_spam
        message = ctx.message

        if ctx.message.author.id in self.currently_generating:
            await ctx.send("Please wait for your previous markov to finish generating.")
            return

        if markov_type == "usermarkov":  # If usermarkov is called
            if len(message.mentions) > 0:
                member = message.mentions[0]
            elif user is not None and user is not "self":
                # Find user with the matching submitted name
                # Check if the username matches exactly, then if it's like the start of a display_name
                member = discord.utils.get(message.guild.members, name=user)
                if member is None:
                    member = discord.utils.find(lambda m: m.display_name.startswith(user),
                                                self.bot.get_all_members())
                    if member is None:
                        await ctx.send("User not found.")
                        return

            else:
                member = message.author
            try:
                g = (open(r'message_cache/users/{0.id}.txt'.format(member), 'r', encoding='utf-8'))
            except FileNotFoundError:
                await ctx.send("I don't have any logs from you.")
                return

        elif markov_type == "otmarkov":
            g = (open('message_cache/messages_off_topic.txt', 'r', encoding='utf-8'))
        elif markov_type == "newmarkov":
            g = (open('message_cache/messages_general_chat.txt', 'r', encoding='utf-8'))
        elif markov_type == "oldmarkov":
            g = (open('message_cache/messages_general_chat.txt', 'r', encoding='utf-8'))
            old_lib = True
        elif path is not None:  # Let us pass in any markov file we want
            if not isinstance(path, StringIO):
                g = open(path, "r", encoding="utf-8")
            else:
                g = path
        else:
            return
        try:
            self.currently_generating.append(ctx.message.author.id)
            async with ctx.typing():
                if old_lib:
                    markov_line = markov2.Markov(g.read())
                    output = markov_line.generate_markov_text()
                else:
                    markov = cls(g.read(), state_size=state_size)
                    output = markov.make_sentence(tries=5000)  # Generate markov

                if not output:
                    await ctx.send("Could not generate markov.")
                    return
                if utils.check_input(output):
                    output = utils.extract_mentions(output, message)
                if modifier_func is not None:
                    if iscoroutinefunction(modifier_func):
                        output = await modifier_func(output)
                    else:
                        output = modifier_func(output)
            await ctx.send(output)

        finally:
            self.currently_generating.remove(ctx.message.author.id)
            g.close()

    @staticmethod
    def _create_multi_markov(*member_ids: int) -> Optional[str]:
        """
        Combine multiple models to create a markov based on different files.
        Might be slow.
        """
        models = []

        for user_id in member_ids:
            try:
                # You don't close the files. How naughty.
                g = (
                    open("message_cache/users/{0}.txt".format(user_id),
                         "r", encoding="utf-8")
                ).read()
                models.append(markovify.NewlineText(g, state_size=2))
            except FileNotFoundError:
                pass

        if len(models) > 1:
            combined_model = markovify.combine(models)
            return combined_model.make_sentence(tries=5000)

    @commands.command(enabled=False, hidden=True)
    async def otmarkov(self, ctx: Context) -> None:
        if MemeCommand.check_rate_limit(ctx, 60):
            await self.gen_markov(ctx, "otmarkov")

    @commands.command(enabled=False, hidden=True, aliases=["newmarkov"])
    async def genmarkov(self, ctx: Context) -> None:
        if MemeCommand.check_rate_limit(ctx, 60):
            await self.gen_markov(ctx, "genmarkov")

    @commands.command(enabled=False, hidden=True)
    async def oldmarkov(self, ctx: Context) -> None:
        if MemeCommand.check_rate_limit(ctx, 60):
            await self.gen_markov(ctx, "oldmarkov")

    @commands.command(hidden=True)
    async def gizmarkov(self, ctx: Context) -> None:
        if MemeCommand.check_rate_limit(ctx, 60, cooldown_group="usermarkov"):
            await self.gen_markov(ctx, "usermarkov", modifier_func=gizoogle.String.translate)

    @commands.command(hidden=True)
    async def fhyrmarkov(self, ctx: Context) -> None:
        MemeCommand.check_rate_limit(ctx, 60, cooldown_group="usermarkov")
        await self.gen_markov(ctx, "usermarkov", modifier_func=utils.generate_fhyr_text)

    @commands.command(hidden=True)
    async def beemarkov(self, ctx: Context) -> None:
        """not the bees"""
        if MemeCommand.check_rate_limit(ctx, 60):
            await self.gen_markov(ctx, path="text_sources/bee_movie.txt")

    @commands.command()
    async def markovoftheentireworld(self, ctx: Context) -> None:
        if MemeCommand.check_rate_limit(ctx, 60):
            await self.gen_markov(ctx, path="text_sources/history_of_entire_world.txt")

    @commands.command()
    async def markovofjapan(self, ctx: Context) -> None:
        if MemeCommand.check_rate_limit(ctx, 60):
            await self.gen_markov(ctx, path="text_sources/history_of_japan.txt")

    @checks.sudo()
    @commands.group()
    async def sourcemarkov(self, ctx: Context) -> None:
        pass

    @checks.sudo()
    @sourcemarkov.command()
    async def add_from_pastebin(
            self, ctx: Context, name: str, pastebin_url: str
    ) -> None:
        sio = await utils.get_text_from_pastebin(pastebin_url)
        self.config.hset("config:markov:custom_files", name, sio.getvalue())
        await ctx.send("Markov registered successfully")

    @checks.sudo()
    @sourcemarkov.command()
    async def add_from_upload(self, ctx: Context, name: str) -> None:
        try:
            sio = await utils.get_text_from_upload(ctx.message.attachments[0].url)
            self.config.hset("config:markov:custom_files", name, sio.getvalue())
            await ctx.send("Markov registered successfully")
        except IndexError as e:
            raise e

    @checks.sudo()
    @sourcemarkov.command()
    async def list(self, ctx: Context) -> None:
        names = self.config.hkeys("config:markov:custom_files")
        await ctx.send("Keys: \n{}".format("\n".join(names)))

    @checks.sudo()
    @sourcemarkov.command()
    async def remove(self, ctx: Context, name: str) -> None:
        self.config.hdel("config:markov:custom_files", name)

    @checks.sudo()
    @sourcemarkov.command()
    async def generate(self, ctx: Context, name: str) -> None:
        sio = StringIO()
        text = self.config.hget("config:markov:custom_files", name)
        sio.write(text)
        sio.seek(0)
        await self.gen_markov(ctx, path=sio, use_newlines=False)

    @commands.command()
    async def seedmarkov(self, ctx: Context, *, seed: str) -> None:
        """
        Generate a usermarkov based on a starting word or phrase.
        """
        MemeCommand.check_rate_limit(ctx, 60, cooldown_group="usermarkov")
        # TODO: implement separate thing and clean this up
        try:
            with open(r'message_cache/users/{0.id}.txt'.format(ctx.message.author), 'r', encoding='utf-8') as g:
                textfile = g.read()
        except FileNotFoundError:
            await ctx.send("I don't have any logs from you.")
            return

        async with ctx.typing():

            markov = markovify.NewlineText(textfile, state_size=2)
            try:
                output = markov.make_sentence_with_start(seed, tries=500)
                if output is None:
                    await ctx.send("Could not create markov with seed `{}`.".format(seed))
                    return
                elif utils.check_input(output):
                    output = utils.extract_mentions(output, ctx.message)

            except (markovify.text.ParamError, KeyError):
                await ctx.send("Could not make a markov with given seed.")
                return

        await ctx.send(output)

    @commands.command()
    async def dualmarkov(self, ctx: Context, *, member: str) -> None:
        """Get a markov comprised of your history combined with that of another."""

        MemeCommand.check_rate_limit(ctx, 60, cooldown_group="usermarkov")

        member = await self._get_member(ctx, member)  # TODO Get this working with multiple members
        if member is not None:
            async with ctx.typing():
                output = self._create_multi_markov(ctx.message.author.id, member.id)
                if output is None:
                    await ctx.send("Could not create markov.")
                    return
                else:
                    if utils.check_input(output):
                        output = utils.extract_mentions(output, ctx.message)

            await ctx.send(output)

    @commands.command()
    async def usermarkov(self, ctx: Context, *, user: str=None) -> None:
        """Get a markov chain generated from a user's history."""
        if await self.check_verification(ctx):
            MemeCommand.check_rate_limit(ctx, 60, cooldown_group="usermarkov")
            await self.gen_markov(ctx, "usermarkov", user)

    @commands.command(aliases=["loodmarkov"], hidden=True)
    async def lewdmarkov(self, ctx: Context) -> None:
        """:eyes:"""
        # Because it takes the model 20s to generate (enough to time pory out), it's more efficient to just use
        # pre-generated lines.
        lewdmarkov_whitelist = [198193394391056385, 274747175706165248, 198526174735892480]
        if MemeCommand.check_rate_limit(ctx, 60, cooldown_group="lewdmarkov") \
                and (self.bot.instance == "AprilPory" or ctx.message.channel.id in lewdmarkov_whitelist)\
                or isinstance(ctx.message.channel, discord.DMChannel)\
                or checks.sudo_check(ctx.message):

            cur_pos = self.config.get("config:markov:lewdmarkov_pos")

            if cur_pos is None or int(cur_pos) == 0:
                cur_pos = 1
                owner = self.bot.get_user(78716152653553664)
                await owner.send("regenerate lewdmarkovs!")
            else:
                cur_pos = int(cur_pos)
                cur_pos += 1

            self.config.set("config:markov:lewdmarkov_pos", str(cur_pos))

            with open("loodmarkov_output.txt", "r", encoding="utf-8") as lm:
                loodmarkov_text = lm.readlines()
            loodmarkov_output = loodmarkov_text[cur_pos]
            await ctx.send(loodmarkov_output)

    @checks.sudo()
    @commands.command()
    async def reset_lewdmarkov_pos(self) -> None:
        self.config.set("config:markov:lewdmarkov_pos", "1")


def setup(bot: Bot) -> None:
    bot.add_cog(Markov(bot))
