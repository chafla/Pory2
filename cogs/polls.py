"""Little utility cog for people to perform short polls with reactions"""

from discord.ext import commands
from .utils.rate_limits import MemeCommand
from .utils import checks
import discord
import asyncio

# TODO: Clean up code, make it consistent and eliminate repeats

number_emoji = [
    "1⃣",
    "2⃣",
    "3⃣",
    "4⃣",
    "5⃣",
    "6⃣",
    "7⃣",
    "8⃣",
    "9⃣"
]


class ComplexPoll:

    def __init__(self, argument):
        """
        Expected input for a complex poll should look like
        ```\n
        <topic>\n
        <thing1>\n
        <thing2>\n
        ```
        """
        self.choices = []

        block = argument.strip("```").split("\n")
        try:
            block = block[1:-1]
        except IndexError:
            raise commands.BadArgument
        self.topic = block[0]
        for choice in block[1:]:
            self.choices.append(choice)

        if len(self.choices) < 2:
            raise commands.BadArgument


class Vote(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def num_emoji(num):
        return "{}⃣".format(num)

    @staticmethod
    async def add_thumbs(message):
        await message.add_reaction("👍")
        await asyncio.sleep(0.5)  # Rate limits
        await message.add_reaction("👎")

    @commands.command()
    async def vote(self, ctx):
        await self.add_thumbs(ctx.message)

    @commands.command(aliases=["spoll"])
    async def simple_poll(self, ctx, seconds: int, *, topic: str):
        """
        Start a simple thumbs up/thumbs down poll about a certain topic
        :param ctx: Context
        :param seconds: How long the poll should go on for. 0 is infinite.
        :param topic: The topic being polled.
        """

        MemeCommand.check_rate_limit(ctx, 200, True)

        if not checks.sudo_check(ctx.message) and (seconds > 3600 or seconds <= 0):
            await ctx.send("Invalid poll length. Polls must be less than 3600 seconds.")
            return

        time_msg = "\nYou have {} seconds to vote.".format(seconds) if seconds > 1 else ""
        output = "Vote on {.message.author.display_name}'s poll with reactions.\n**{}**{}".format(ctx, topic, time_msg)

        message = await ctx.send(output)

        await self.add_thumbs(message)

        await asyncio.sleep(seconds)
        embed = discord.Embed(title=topic, color=discord.Color.blue())
        embed.set_author(name=ctx.message.author.name, icon_url=ctx.message.author.avatar_url)
        # Pull the number of reactions from the message itself
        thumbs_up = 0
        thumbs_down = 0

        message = await message.channel.fetch_message(message.id)  # Update the message object

        for reaction in message.reactions:
            if reaction.emoji == "👍":
                thumbs_up = reaction.count - 1  # Account for the extra one
            elif reaction.emoji == "👎":
                thumbs_down = reaction.count - 1
        embed.add_field(name="👍", value=str(thumbs_up))
        embed.add_field(name="👎", value=str(thumbs_down))

        await ctx.send("**Results of <@{.message.author.id}>'s poll:**".format(ctx), embed=embed)

    @commands.command(brief="Create a poll with multiple listed choices.")
    async def complex_poll(self, ctx, seconds: int, *, options: ComplexPoll):
        """
        Format:

        !complex_poll <seconds> \`\`\`
        <topic>
        <option1>
        <option2>
        ...
        <option9>
        \`\`\`
        """

        MemeCommand.check_rate_limit(ctx, 200, True)

        topic = options.topic
        time_msg = "\nYou have {} seconds to vote.\n".format(seconds) if seconds > 1 else ""
        output = "Vote on {.message.author.display_name}'s poll with reactions.\n**{}**{}".format(ctx, topic, time_msg)

        for number, choice in enumerate(options.choices):
            output += "{}: {}\n".format(self.num_emoji(number + 1), choice)

        message = await ctx.send(output)

        for num, choice in enumerate(range(len(options.choices)), start=1):
            await message.add_reaction(self.num_emoji(num))
            await asyncio.sleep(0.25)  # rate limit stuff

        await asyncio.sleep(seconds)
        embed = discord.Embed(title=topic, color=discord.Color.blue())
        embed.set_author(name=ctx.message.author.name, icon_url=ctx.message.author.avatar_url)

        message = await message.channel.fetch_message(message.id)  # Update the message object

        for reaction in message.reactions:
            if reaction.emoji in number_emoji:
                emoji_index = number_emoji.index(reaction.emoji)  # Get the number of the emoji
                name = "{}: {}\n".format(self.num_emoji(emoji_index + 1), options.choices[emoji_index])
                embed.add_field(name=name, value=str(reaction.count - 1))

        await ctx.send("**Results of <@{.message.author.id}>'s poll:**".format(ctx), embed=embed)

    @complex_poll.error
    async def complex_poll_error(self, error, ctx):
        if type(error) == commands.BadArgument:
            await ctx.send(ctx.command.help)


def setup(bot):
    bot.add_cog(Vote(bot))
