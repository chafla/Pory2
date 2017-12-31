"""Basic tag support"""

from discord.ext import commands
from .utils import checks, utils
from discord import DMChannel, Embed, Color
from redis import RedisError


tag_ctx_keys = {
    "global": "config:tags:global",
    "chan": "{}:tags",
    "guild": "{}:tags"
}

list_desc = """
Global tags:
{}

Server tags:
{}

Channel tags:
{}
"""


class Tags:

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config

    def get_tag_context(self, ctx, tag_name):
        """
        Check the appropriate contexts if a tag exists.
        We want to respect a hierarchy of:
            - global
            - local (server)
            - local (channel)
        which is backwards from the way we'd normally be checking.
        
        Returns the context in which it exists, else none
        """
        # We want the error to fall through if the global tags don't work.
        if self.config.hexists("config:tags:global", tag_name):
            return "global"

        if not isinstance(ctx.message.channel, DMChannel):
            try:
                if self.config.hexists("guild:{}:tags".format(ctx.message.guild.id), tag_name):
                    return "guild"
            except RedisError:
                pass

        try:
            if self.config.hexists("chan:{}:tags".format(ctx.message.channel.id), tag_name):
                return "chan"
            else:
                return None
        except RedisError:
            return None

    def _key_from_bounds(self, ctx, bounds):
        """Get a key based on some bounds given ctx"""
        if bounds == "global":
            return "config:tags:global"
        elif bounds == "chan":
            return "chan:{}:tags".format(ctx.message.channel.id)
        elif bounds == "guild":
            return "guild:{}:tags".format(ctx.message.guild.id)
        else:
            return None

    def _key_from_context(self, ctx, tag_name):
        """Get a key based on what context it matches"""
        tag_context = self.get_tag_context(ctx, tag_name)
        if tag_context:
            if tag_context == "global":
                return "config:tags:global"
            elif tag_context == "chan":
                return "chan:{}:tags".format(ctx.message.channel.id)
            elif tag_context == "guild":
                return "guild:{}:tags".format(ctx.message.guild.id)
            else:
                return None

    @checks.is_regular()
    @commands.group(invoke_without_command=True)
    async def tag(self, ctx, name: str):
        tag_ctx = self.get_tag_context(ctx, name)
        if not tag_ctx:
            await ctx.send("Tag doesn't exist.")
            return
        else:
            tag = self.config.hget(self._key_from_context(ctx, name))

            await ctx.send(tag)

    @checks.is_pokemon_mod()
    @tag.command()
    async def add(self, ctx, bounds: str, name: str, *, content: str):
        # Allow mods to create tags, allow regs and above to call tags
        # TODO: Make generic errors for these commands like how robodanny does it
        if utils.check_mentions(content):
            await ctx.send("Tags cannot contain mentions")
        elif len(name) > 30:
            await ctx.send("Tag name must be less than 30 characters.")
        elif len(content) > 200:
            await ctx.send("Tag content must be less than 200 characters.")
        else:
            # Check for an existing tag
            existing_tag_ctx = self.get_tag_context(ctx, name)
            if existing_tag_ctx is not None:
                await ctx.send("Tag {} already exists as a {} tag.".format(name, existing_tag_ctx))
                return
            elif existing_tag_ctx == "global" and not checks.sudo_check(ctx.message):
                await ctx.send("Only {} can add a global tag.".format(self.bot.owner))
            else:
                try:
                    self.config.hset(self._key_from_bounds(ctx, bounds), name, content)
                except KeyError:
                    await ctx.send("Invalid bound.")
                    return
                else:
                    await ctx.send("Tag {} added successfully.".format(name))

    @checks.is_pokemon_mod()
    @tag.command()
    async def remove(self, ctx, name: str):
        """Remove a tag. Mods can remove channel or server tags, but only the owner can remove global tags."""
        if self.config.hexists("config:tags:global", name):
            if not checks.sudo_check(ctx.message):
                await ctx.send("Only {} can remove global tags.".format(self.bot.owner))
            else:
                self.config.hdel("config:tags:global", name)

        elif self.config.hexists("chan:{}:tags".format(ctx.message.channel.id), name):
            self.config.hdel("chan:{}:tags".format(ctx.message.channel.id), name)
            # Don't allow ability to remove global tags

        elif self.config.hexists("guild:{}:tags".format(ctx.message.guild.id), name):
            self.config.hdel("guild:{}:tags".format(ctx.message.guild.id, name))

        await ctx.send("Tag {} removed.".format(name))

    @checks.is_pokemon_mod()
    @tag.command()
    async def list(self, ctx):
        global_tags = self.config.hkeys("config:tags:global")
        chan_tags = self.config.hkeys("{}:tags".format(ctx.message.channel.id))
        guild_tags = self.config.hkeys("{}:tags".format(ctx.message.guild.id))

        global_txt = ", ".join(global_tags) if global_tags else None
        chan_txt = ", ".join(chan_tags) if chan_tags else None
        guild_txt = ", ".join(guild_tags) if guild_tags else None

        embed = Embed(color=Color.blue(), description=list_desc.format(global_txt, chan_txt, guild_txt))
        embed.set_author(name="All tags")

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Tags(bot))
