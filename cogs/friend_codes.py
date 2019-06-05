"""Support for friend codes"""


import re

from typing import Optional

from discord import Color, Embed, Member
from discord.ext import commands
from discord.ext.commands import Bot, Context


class FriendCodeValidator:

    def __init__(self, argument: str) -> None:
        fc_parts = re.findall("([0-9]{4})", argument)  # Find three 4-num long blocks
        if fc_parts is not None and len(fc_parts) == 3:
            self.code = "{0.[0]}-{0.[1]}-{0.[2]}".format(fc_parts)
        else:
            self.code = None


class FriendCodes:

    """Cog for 3DS/Switch friend code management."""

    formatted_names = {
        "3ds": "3DS",
        "switch": "Switch",
        "sw": "Switch",
        "go": "Pokemon GO"
    }

    game_name_substitutions = {
        "um": "Ultra Moon",
        "us": "Ultra Sun",
        "or": "Omega Ruby",
        "as": "Alpha Sapphire",
        "alpha": "Alpha Sapphire",
        "omega": "Omega Ruby"
    }

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.config = self.bot.config
        # self.bot.loop.create_task(self._retro_fix_friendcodes())

    @staticmethod
    def _parse_fc(text: str) -> Optional[str]:
        """Get an inputted fc-like string and format it in a constant form"""
        fc_parts = re.findall("([0-9]{4})", text)  # Find 4-num long blocks
        if len(fc_parts) != 3 or fc_parts is None:
            return
        else:
            return "{0}-{1}-{2}".format(fc_parts[0], fc_parts[1], fc_parts[2])

    @commands.group()
    async def fc(self) -> None:
        """Set your FCs or find another user's FC

        `[p]fc get @user` to look up an FC
        `[p]fc set (platform) 0123-4567-8910` to set your FC"""
        pass

    @fc.command()
    async def set(self, ctx: Context, system: str, fc: str) -> None:
        """Set your friend code.
        System can be '3ds', 'switch', or 'go'"""
        # Check to see if the fc is in proper form: should at least have four groups of 4 numbers
        friend_code = self._parse_fc(fc)

        if friend_code is None:
            await ctx.send("Invalid friend code.\nFormat: `0000-0000-0000`")
            return
        elif system.lower() not in self.formatted_names:
            await ctx.send("Invalid system specified.\nSystems are '3DS', 'Switch', and 'Go'")
            return

        self.config.set("user:{}:fc:{}:code".format(ctx.message.author.id,
                                                    self.formatted_names[system.lower()]), friend_code)

        await ctx.send("Friend code updated successfully.")

    @fc.command()
    async def get(self, ctx: Context, *, mention: Member=None) -> None:
        """Get a user's friend code. If a mention is omitted, then it gets the users' own friend code."""

        member = ctx.message.author if mention is None else mention
        systems = self.config.scan_iter(match="user:{}:fc:*:code".format(member.id))

        if systems is None:
            await ctx.send("No game info registered for {}.".format(member.display_name))
            return
        else:
            embed = Embed(
                title="Game info for {}:".format(member.display_name),
                color=Color.orange()
            )
            embed.set_author(name=member.name, icon_url=member.avatar_url)
            # First, want to add 3DS friend code, then follow it with in game igns
            for system in systems:
                sys_name = system.split(":")[-2]
                embed.add_field(
                    name=sys_name,
                    value=self.config.get("user:{}:fc:{}:code".format(member.id, sys_name))
                )
                igns = ""
                for game, name in self.config.hgetall("user:{}:fc:{}:ign".format(member.id,
                                                                                 sys_name)).items():
                    igns += "{}: {}\n".format(game.title(), name)

                if igns:
                    embed.add_field(name="IGNs", value=igns)

            await ctx.send(embed=embed)

    @get.error
    async def fc_error(self, error: Exception, ctx: Context) -> None:
        if isinstance(error, commands.BadArgument):
            await ctx.send(str(error))

    @fc.command()
    async def set_ign(self, ctx: Context, game: str, *, in_game_name: str) -> None:
        """Register an IGN for a game."""

        valid_games = ["Sun", "Moon", "Omega Ruby", "Alpha Sapphire", "X", "Y", "Ultra Sun", "Ultra Moon"]

        # Hack for user input
        if self.game_name_substitutions.get(game.lower()) is not None:
            game = self.game_name_substitutions[game.lower()]
        elif game.lower() == "ultra":
            await ctx.send('Ultra Sun and Ultra Moon need to be surrounded with parentheses.\n'
                           'Try `"Ultra Sun"` or `"Ultra Moon"` instead.')
            return

        elif game.lower() not in [i.lower() for i in valid_games]:
            await ctx.send("Invalid game. Valid games are: \n" + ", ".join(valid_games))
            return

        self.config.hset("user:{}:fc:3DS:ign".format(ctx.message.author.id), game.lower(), in_game_name)
        await ctx.send("IGN updated successfully.")


def setup(bot: Bot) -> None:
    bot.add_cog(FriendCodes(bot))
