from discord.ext import commands
import logging

log = logging.getLogger()


class AprilFools2018(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.substitutions = {}
        self.channel_blacklist = [115637695769870340]

        with open("afd_substitutions.txt", "r", encoding="utf-8") as f:
            for sub in f.readlines():
                # these variables tho
                try:
                    pokemon, digimon = sub.strip("\n").split(" | ")
                    self.substitutions[pokemon] = digimon.title()
                except ValueError:
                    log.exception("Couldn't split in AprilFools2018 for line {}.".format(sub))

    def find_matching_substitution(self, message: str):
        for pkmn_name in self.substitutions:
            if pkmn_name in message.lower():
                return self.substitutions[pkmn_name]
        else:
            return None

    @property
    def guild(self):
        return self.bot.get_guild(234567)  # Borked on purpose since it seems to activate on its own

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.guild == self.guild and message.channel.id not in self.channel_blacklist:
            digimon_name = self.find_matching_substitution(message.content)
            if digimon_name is not None:
                await message.channel.send("Did you mean {}? {}".format(digimon_name, message.author.mention))


# def setup(bot):
#     bot.add_cog(AprilFools2018(bot))
