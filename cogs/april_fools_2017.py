"""
Base cog for april fools shenanigans

Users can use !ban <@mention>, which gives the target a role with no read permissions in most channels.
It does, though, give users read access to a certain few channels that we can make.
Every user can only ban one other user.

TODO:
Change the actual mod role names, but keep track of their IDs
Consider a better way of implementing this that lets people participate

'Hey, everyone. It's been a long month or two, and us mods are honestly pretty drained from the past few weeks.
We've decided that we're going to take a day off. We've heard all your wishes about being mods yourselves, and so,
effective immediately, everyone has mod powers. You can use !ban <mention> to ban troublemakers for us, though you can
only use it once every few hours to be safe.

Thanks for the help, and we'll see you soon!'

******************

Was planned for afd 2017 shenanigans, but was shelved for another day.


"""
import discord
from discord.ext import commands
from .utils import checks, config
from time import time
from asyncio import sleep

# TODO: Convert to rewrite form.


def is_fake_mod():
    def predicate(ctx):
        return checks.has_role(ctx, lambda r: r.name == "Mod")
    return commands.check(predicate)


class AprilFools:

    def __init__(self, bot):
        self.bot = bot
        self.banned_role = None
        self.mod_role = None
        self.cooldown = 30
        self.ban_data = {}
        self.ban_ability_cooldowns = {}

        self.ban_config = config.Config("april_fools_bans.json")  # Keep track of bans for the hell of it

    @property
    def guild(self):
        return self.bot.get_guild(id="111504456838819840")

    @checks.sudo()
    @commands.command(hidden=True)
    async def setup_guild(self, ctx):
        self.banned_role = discord.utils.get(self.guild.roles, name="Banned")
        self.mod_role = discord.utils.get(self.guild.roles, name="Mod")

        try:
            await ctx.delete()
        except discord.Forbidden:
            pass

        if not self.guild or not self.banned_role or not self.mod_role:
            await ctx.message.author.send("One or more objects was not set correctly.\nBanned: {}\nMod: {}".format(
                self.banned_role is not None, self.mod_role is not None))

    @is_fake_mod()
    @commands.command(hidden=True)
    async def ban(self, ctx, mention: discord.Member):
        # "Ban" a user. Remove mod role, and add role perm that blocks access in all channels.
        # TODO Add a call to time.time(), store that with the ban config, make all bans expire in 3 min
        # TODO Also add a user cooldown so that users aren't harassed
        author = ctx.message.author
        ban_cooldown = self.ban_ability_cooldowns.get(ctx.message.author.id, 0)

        if not self.ban_data.get(mention.id) and ctx.message.author.id != mention.id and ban_cooldown < time():
            try:
                await self.bot.remove_roles(mention, self.mod_role)
            except discord.HTTPException:
                await ctx.send("User is already banned.")
                return

            self.ban_data[mention.id] = {
                "user_id": mention.id,
                "banned_by": author.id,
                "timestamp_of_unban": time() + 10 * 60,
                "timestamp_of_cooldown": time() + 30 * 60,
            }

            # Keep track of the amount of times a given user was banned for the hell of it
            current_bans = self.ban_config.get(mention.id, [])
            current_bans.append(ctx.message.author.id)
            await self.ban_config.put(mention.id, current_bans)

            # Drop a cooldown on the member banning for three hours, so that they can't ban crazily.
            self.ban_ability_cooldowns[ctx.message.author.id] = time() + 3 * 60 * 60
            await self.bot.add_roles(mention, self.banned_role)
            await mention.send("You've just been sent to the Shadow Realm by {}".format(author.display_name))

    async def on_timer_update(self, secs):
        if secs % 5 == 0:
            for user_id, data in self.ban_data.items():
                if data["timestamp_of_cooldown"] <= time():  # Users cannot be banned again for this period
                    del self.ban_data[user_id]
                elif -1 < data["timestamp_of_unban"] <= time():
                    member = self.bot.get_member(self.guild, user_id)
                    await self.bot.remove_roles(member, self.banned_role)
                    await sleep(0.1)  # Failsafe
                    await self.bot.add_roles(member, self.mod_role)
                    data["timestamp_of_unban"] = -1


def setup(bot):
    bot.add_cog(AprilFools(bot))
