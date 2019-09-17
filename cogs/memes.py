"""Code for simple rate limited commands, as well as basic commands that use the rate-limiting."""


import logging
import re

from glob import glob
from io import BytesIO
from random import choice

import aiohttp

from discord import File
from discord.ext import commands
from discord.ext.commands import Bot, Context

from .utils import utils, gizoogle, checks
from .utils.rate_limits import MemeCommand


log = logging.getLogger()


class RateLimitedMemes:
    """ Fun commands that make Porygon2 the amazing piece of cancer it is :^) """

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        MemeCommand.bot = bot
        # Init meme objects on load of cog

    # Simple commands

    @commands.command()
    async def hello(self, ctx: Context) -> None:
        if MemeCommand.check_rate_limit(ctx, 60, ignore_blacklist=True):
            await ctx.send("Hello was received!")

    # I swear
    @commands.command(hidden=True)
    async def hewwo(self, ctx: Context):
        await ctx.send("h-hewwo?")

    @commands.command()
    async def quill(self, ctx: Context) -> None:
        if MemeCommand.check_rate_limit(ctx):
            await ctx.send("Can we discuss bodies on the chubby side? http://i.imgur.com/iP6Fiwc.png")

    # @checks.not_in_oaks_lab()
    # @commands.command(hidden=True, enabled=False)
    # async def gluedcario(self, ctx: Context) -> None:
    #     # Currently broken
    #     if MemeCommand.check_rate_limit(ctx):
    #         await ctx.send("[IMAGE MISSING]")

    @checks.not_in_oaks_lab()
    @commands.command()
    async def okno(self, ctx: Context) -> None:
        if MemeCommand.check_rate_limit(ctx):
            await ctx.send("http://i.imgur.com/BnSmd7u.gif")

    @checks.not_in_oaks_lab()
    @commands.command()
    async def kix(self, ctx: Context) -> None:
        if MemeCommand.check_rate_limit(ctx):
            await ctx.send("http://www.teamten.com/lawrence/writings/kix.jpg")

    @checks.not_in_oaks_lab()
    @commands.command()
    async def brendan(self, ctx: Context) -> None:
        if MemeCommand.check_rate_limit(ctx):
            await ctx.send("http://i.imgur.com/Q4BRrWe.jpg")

    @commands.command(enabled=False, hidden=True)
    async def abrahamabra(self, ctx: Context) -> None:
        if MemeCommand.check_rate_limit(ctx):
            await ctx.send("[IMAGE MISSING]")

    @checks.not_in_oaks_lab()
    @commands.command()
    async def ifyouknow(self, ctx: Context) -> None:
        if MemeCommand.check_rate_limit(ctx):
            await ctx.send("http://i.imgur.com/PcXxLhw.gif")

    @checks.not_in_oaks_lab()
    @commands.command()
    async def tin(self, ctx: Context) -> None:
        if MemeCommand.check_rate_limit(ctx):
            await ctx.send("http://i.imgur.com/jAxt6v4.png")

    @checks.not_in_oaks_lab()
    @commands.command()
    async def dibs(self, ctx: Context) -> None:
        if MemeCommand.check_rate_limit(ctx):
            await ctx.send("http://i.imgur.com/srqlqI7.png")

    @checks.not_in_oaks_lab()
    @commands.command()
    async def reshipls(self, ctx: Context) -> None:
        if MemeCommand.check_rate_limit(ctx):
            await ctx.send("http://i.imgur.com/IXmQ949.jpg")

    @commands.command()
    async def thinksplosion(self, ctx: Context) -> None:
        if MemeCommand.check_rate_limit(ctx):
            await ctx.send("http://i.imgur.com/VrPekkR.gif")

    @commands.command(aliases=["hype"], hidden=True)
    async def eievui(self, ctx: Context) -> None:
        MemeCommand.check_rate_limit(ctx)
        await ctx.send("http://i.imgur.com/X7LCg0T.gif")

    @checks.r_md()
    @commands.command()
    async def okyes(self, ctx: Context) -> None:
        MemeCommand.check_rate_limit(ctx)
        await ctx.send("https://i.imgur.com/PujqYca.jpg")

    @checks.not_in_oaks_lab()
    @commands.command()
    async def midi(self, ctx: Context) -> None:
        if MemeCommand.check_rate_limit(ctx, 60):
            await ctx.send(
                "There were some interesting things Masuda did with the music for BW2, like setting some"
                " drum loops as midi instruments. Listen to the battle vs. World Champion track, and you"
                " can hear the amen break. Also, things like voice that you could hear in the poison gym"
                " and Colress' theme."
            )

    @checks.not_in_oaks_lab()
    @commands.command()
    async def lemons(self, ctx: Context, *, text: str) -> None:
        if MemeCommand.check_rate_limit(ctx, 600, priority_blacklist=[319309336029560834])\
                and not utils.check_input(text):
            await ctx.send(
                "I’m so glad that our {0} tree finally grew and sprouted fruitful {0}y {0}s. I mean, "
                "imagine, we can make {0}ade, key {0} pie, {0} merengue pie. I think it’s the most "
                "valuable of property that we have. I think we should go to the bank and get a loan, "
                "actually I think we should just get {0} tree insurance and then get a loan and use the "
                "{0} tree as collateral because it is now insured. I truly do love our {0} tree. Just "
                "imagine a life full of {0} trees, and all our beautiful {0}s, endless possibilities. "
                "They’re so beautiful, I wish I was a {0}. You wish you were a {0}? If you were a {0} I "
                "would put you on my shelf and cherish you like I cherish all our {0}s. That’s so "
                "beautiful, like I only hope that the whores aren’t stealing our {0}s you know those "
                "naughty whores always steal {0}s. we do have a couple {0} whores in this community, "
                "those damn {0}-stealing whores I hate them no one will take our prized {0}s from us. "
                "Hey, has it been about 10 seconds since we looked at our {0} tree? It has been about 10"
                " seconds till we looked at our {0} tree. Hey what the FUCK".format(text)
            )

    # Maybe move this one to image_list?
    @checks.not_in_oaks_lab()
    @commands.command()
    async def snek(self, ctx: Context) -> None:
        MemeCommand.check_rate_limit(ctx,
                                     cooldown_group="image_list",
                                     priority_blacklist=[319309336029560834])  # #mature_chat):
        temp_image = BytesIO()
        async with ctx.typing():
            async with aiohttp.ClientSession() as session:
                # For some reason, using the full URL doesn't work right
                # We need to omit the trailing slash
                async with session.get('http://dcfi.co/snek') as resp:
                    if resp.status == 200 and "image" in resp.content_type:
                        # print(await resp.json())
                        image_type = resp.content_type[6:]  # remove "image/
                        while True:
                            chunk = await resp.content.read(10)
                            if not chunk:
                                break
                            temp_image.write(chunk)
                    else:
                        await ctx.send("This command is temporarily unavailable.")
                        return

            temp_image.seek(0)

            filename = "snek." + image_type if image_type else "jpg"
        await ctx.send(file=File(temp_image, filename))

    @checks.not_in_oaks_lab()
    @commands.command()
    async def giz(self, ctx: Context, *, text: str) -> None:
        """Get a gizooglified version of some text."""
        if MemeCommand.check_rate_limit(ctx, 60):
            if re.match(r"^((http[s]?|ftp):/)?/?([^:/\s]+)((/\w+)*/)([\w\-.]+[^#?\s]+)(.*)?(#[\w\-]+)?$",
                        text):
                # if we get a url input
                giz_output = await gizoogle.Website.translate(text)
            else:
                giz_output = await gizoogle.String.translate(text)
            await ctx.send(giz_output)

    @commands.command()
    async def fhyr(self, ctx: Context, *, text: str) -> None:
        MemeCommand.check_rate_limit(ctx)
        await ctx.send(utils.generate_fhyr_text(text))

    @checks.not_in_oaks_lab()
    @commands.command()
    async def tingle(self, ctx: Context) -> None:
        if MemeCommand.check_rate_limit(ctx):
            file_list = glob('tingle/*.*')
            image_chosen = choice(file_list)
            await ctx.send(file=File(image_chosen))


def setup(bot: Bot) -> None:
    bot.add_cog(RateLimitedMemes(bot))
