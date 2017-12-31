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

    @commands.command(pass_context=True)
    async def rescuer(self, ctx, *, team_name: str):
        """Set a pingable role for when people have rescue requests."""
        # I should really clean this up because it's honestly messy as hell code from bill's PC
        def rescuer_check(msg):
            return (msg.content == "NA") or (msg.content == "EU")

        message = ctx.message

        team_list = ["BRT/RRT Rescuer", "EoD/T/S Rescuer", "GtI Rescuer", "EU PSMD Rescuer", "NA PSMD Rescuer"]
        entered_team = team_name

        if entered_team not in team_list:
            await ctx.send("Teams are `BRT/RRT Rescuer`, `EoD/T/S Rescuer`, `GtI Rescuer`,"
                           " `EU PSMD Rescuer`, and `NA PSMD Rescuer`.")

        if team_aliases[entered_team] == "PSMD_null":
            # Simple check if the user omits the PSMD role
            await ctx.send("Which region, `NA` or `EU`?")
            msg = await self.bot.wait_for_message(author=message.author, check=rescuer_check)
            if msg.content == "NA":
                entered_team = "NA PSMD"
            elif msg.content == "EU":
                entered_team = "EU PSMD"
        role = discord.utils.get(message.guild.roles, name=team_aliases[entered_team])
        if role is None or role.name not in team_list:
            # If the role wasn't found, or isn't one that we want to add
            await ctx.send("Team doesn't exist. Teams that do are `BRT/RRT Rescuer`, `EoD/T/S Rescuer`, "
                           "`GtI Rescuer`, `EU PSMD Rescuer`, and `NA PSMD Rescuer`.")
            print("Role not added. Ensure team_list is updated with all roles.")
            return
        elif role in message.author.roles:
            # If they already have the role
            await ctx.send("You already have this role.")
        else:
            try:
                await message.author.add_roles(role)
                await ctx.send("Successfully added role {0}".format(role.name))
            except discord.Forbidden:
                await ctx.send("I don't have perms to add roles.")


def setup(bot):
    bot.add_cog(RMD(bot))
