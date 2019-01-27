import discord
from discord.ext import commands
from .utils import messages, checks
import datetime
import random
import time


terms_and_conditions_err = "That message should be posted in <#349198111345868801>. Sending it to me has no effect."


class RPokemon:
    """
    Utility commands specifically for use in /r/Pokemon
    Is this cog really only !egg now lmao
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.egg_data = self.config.hgetall("config:eggs")

    @property
    def guild(self):
        return self.bot.get_guild(111504456838819840)

    async def on_timer_update(self, seconds):
        if seconds % 3600 == 0:
            if random.random() > 0.98:  # 2% chance of activation
                mature_chan = self.bot.get_channel(278043765082423296)
                await mature_chan.send("The game.")

    @staticmethod
    async def on_member_join(member):
        if checks.r_pokemon_check(member.guild):
            await member.send(messages.intro_pm_content_pkmn)

    @staticmethod
    async def on_message(message):
        if isinstance(message.channel, discord.DMChannel):
            if message.content.lower() == "i agree to the terms and conditions":

                await message.channel.send(terms_and_conditions_err)

            elif message.content.lower() == "i agree to the terms and conditions in #rules":

                await message.channel.send("pls")


def setup(bot):
    bot.add_cog(RPokemon(bot))
