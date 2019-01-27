"""Basic commands for /r/MysteryDungeon"""
from discord.ext import commands
import discord
from .utils.rate_limits import MemeCommand

team_aliases = {
    "BRT/RRT Rescuer": "BRT/RRT Rescuer",
    "EoD/T/S Rescuer": "EoD/T/S Rescuer",
    "BRT/RRT": "BRT/RRT Rescuer",
    "BRT": "BRT/RRT Rescuer",
    "RRT": "BRT/RRT Rescuer",
    "EoD/T/S": "EoD/T/S Rescuer",
    "Sky": "EoD/T/S Rescuer",
    "GtI": "GtI Rescuer",
    "WAKE ME UP INSIDE": "GtI Rescuer",
    "GtI Rescuer": "GtI Rescuer",
    "fuck le gates to inshitity": "GtI Rescuer",
    "PSMD": "PSMD_null",
    "PSMD Rescuer": "PSMD_null",
    "EU PSMD": "EU PSMD Rescuer",
    "EU PSMD Rescuer": "EU PSMD Rescuer",
    "NA PSMD": "NA PSMD Rescuer",
    "NA PSMD Rescuer": "NA PSMD Rescuer",

}


class RMD:

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def faq(self, ctx):
        """Link to the /r/MysteryDungeon FAQ."""
        await ctx.send('Please check the FAQ! https://www.reddit.com/r/MysteryDungeon/wiki/psmdfaq')

    @commands.command()
    async def wm(self, ctx):
        """Link to wonder mail passwords in PSMD."""
        await ctx.send('http://www.cpokemon.com/2015/11/24/todas-las-contrasenas-wonder-mail-de-'
                       'pokemon-super-mystery-dungeon/')

    @commands.command()
    async def screenshot(self, ctx):
        """Guide on screenshotting rescue QR codes for PSMD."""
        await ctx.send("https://www.reddit.com/r/MysteryDungeon/comments/3ts6mm/how_to_take_a_screenshot_of"
                       "_rescue_mail_because/")

    @commands.command(hidden=True, pass_context=True, enabled=False)
    async def reshcycle(self, ctx):
        if MemeCommand.check_rate_limit(ctx):
            await ctx.send("http://i.imgur.com/1tgZCIs.png")

    @commands.command(hidden=True, pass_context=True)
    async def levels(self, ctx):
        if MemeCommand.check_rate_limit(ctx):
            await ctx.send("http://i.imgur.com/tD009K4.png")


def setup(bot):
    bot.add_cog(RMD(bot))
