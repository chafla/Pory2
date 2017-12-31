"""User profile things, such as animelist"""

from discord.ext import commands
import discord


permitted_entries = {
    "anime_list": "username",
}


class UserProfile:

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config

    def update_profile(self, ctx, key, value):
        if value is None:
            self.config.hdel("user:{}:profile:{}".format(ctx.message.author.id, ctx.command.name),
                             key)
            return False
        else:
            self.config.hset("user:{}:profile:{}".format(ctx.message.author.id, ctx.command.name),
                             key, value)
            return True

    @commands.group(invoke_without_command=True)
    async def profile(self):
        pass

    # @profile.command()
    # async def update(self, ctx, category: str, value: str=None):
    #     if category in permitted_entries:
    #         if self.update_profile(ctx, category)

    @profile.command(pass_context=True)
    async def my_anime_list(self, ctx, account_name: str=None):
        if self.update_profile(ctx, "username", account_name):
            await ctx.send("Entry added successfully.")
        else:
            await ctx.send("Entry removed.")

    @profile.command()
    async def view(self, ctx, member: discord.Member=None):
        """View a user's profile"""
        if member is None:
            member = ctx.message.author
        embed = discord.Embed(color=discord.Color.blue())
        embed.set_author(name="UserProfile for {}".format(ctx.message.author.name),
                         icon_url=member.avatar_url)
        has_fields = False
        for category in permitted_entries:
            if self.config.exists("user:{}:profile:{}".format(member.id, category)):
                field_parts = []
                for name, entry in self.config.hgetall("user:{}:profile:{}".format(member.id, category)):
                    field_parts.append("*{}*: `{}`".format(name.capitalize(), entry))
                    has_fields = True
                embed.add_field(name=category, value="\n".join(field_parts))

        if not has_fields:
            embed.add_field(name="User's profile is empty!", value="")

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(UserProfile)
