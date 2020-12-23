from discord import Guild
from discord.ext import commands
import discord
from cogs.utils.utils import download_image
from cogs.utils import checks
from io import BytesIO
from aiohttp import ClientError


class WebHooks(commands.Cog):
    """
    Cog to create some webhooks which the bot will spawn and can use as desired.

    Redis keys used:
    <guild>:hooks:all - Set of all webhook IDs managed by the bot
    <guild>:hooks:<hook_id> - Map of flags on the webhook that we want to hold onto
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.hook_id_config_key = "guild:{}:hooks:all"

    @staticmethod
    def _check_permissions(ctx):
        bot_mem = ctx.guild.me
        perms = discord.permissions.Permissions()
        perms.manage_webhooks = True
        return perms <= bot_mem.guild_permissions

    @checks.sudo()
    @commands.group("hook")
    async def hook(self, ctx):
        pass

    async def _create_webhook(self, ctx, name: str, channel: discord.TextChannel, avatar_url: str):
        avatar_img = None

        if avatar_url is not None:

            # Try to download the avatar image to a bytes object if we can.

            avatar_img = BytesIO()

            try:
                await download_image(avatar_url, avatar_img)
                # The create_webhook() function expects a bytes-like object, not a file-like object (which BytesIO is).

                avatar_img = avatar_img.read()
            except ClientError:
                await ctx.send("Couldn't download the image.")
                return

        try:
            # Create, capture the hook.
            hook = await channel.create_webhook(name=name, avatar=avatar_img)
        except discord.HTTPException:
            await ctx.send("Could not create the webhook.")
            return

        # Now that the hook is created, we'll drop it into our database.

        guild_tag = "guild:{}:hooks".format(ctx.guild.id)

        self.config.sadd("{}:all".format(guild_tag), hook.id)

        # Don't store name: we'll fetch that as needed.
        # TODO this might be excessive if we have IDs
        hook_data = {
            "id": hook.id
        }

        self.config.hmset("{}:{}".format(guild_tag, hook.id), hook_data)
        await ctx.send("New webhook registered.")

    @hook.command()
    async def create_external(self, ctx, name: str, channel_id: str, avatar_url: str = None):
        """
        Create a new webhook belonging to some other channel in the current guild.
        :param ctx: context
        :param name: Username for the webhook
        :param channel_id: Channel ID for the webhook to be created in
        :param avatar_url: Avatar url to use
        """
        if ctx.guild is None or not self._check_permissions(ctx):
            await ctx.send("I don't have permissions to do that.")
            return

        chan = self.bot.get_channel(int(channel_id))

        await self._create_webhook(ctx, name, chan, avatar_url)

    @hook.command()
    async def create(self, ctx, name, avatar_url: str = None):
        """
        Create a new webhook in the current guild. Requires `manage webhook` permissions.
        :param ctx: context
        :param name: Username for the new webhook
        :param avatar_url: Avatar url for the new webhook
        """
        if ctx.guild is None or not self._check_permissions(ctx):
            await ctx.send("I don't have permissions to do that.")
            return

        await self._create_webhook(ctx, name, ctx.message.channel, avatar_url)

    @hook.command(aliases=["list"])
    async def list_guild_hooks(self, ctx):
        """
        List all of the webhooks created by pory in the guild.
        In here, we'll also run some cleanup operations.
        :param ctx: context
        """

        if ctx.guild is None or not self._check_permissions(ctx):

            return

        hooks = await ctx.guild.webhooks()

        bot_created_hook_ids = self.config.smembers(self.hook_id_config_key.format(ctx.guild.id))

        bot_created_hooks = []

        valid_hooks = set()

        for hook in hooks:
            if str(hook.id) in bot_created_hook_ids:
                bot_created_hooks.append(hook)
                valid_hooks.add(str(hook.id))

        # Clean up hooks that no longer exist.
        invalid_hooks = bot_created_hook_ids - valid_hooks
        if len(invalid_hooks) > 0:
            await ctx.send("Found {} hooks that no longer exist, removing.".format(len(invalid_hooks)))
            [self.config.srem(self.hook_id_config_key.format(ctx.guild.id), i) for i in invalid_hooks]

        if not bot_created_hooks:
            await ctx.send("No bot-created hooks exist in this server.")
            return

        # TODO Make this an embed at some point

        hook_list = "\n".join(["{} ({})".format(i.name, i.id) for i in bot_created_hooks])
        await ctx.send("Bot-created webhooks on the server: \n{}".format(hook_list))

    @staticmethod
    async def _get_hook(hook_id: str, guild: Guild):
        """
        Get a webhook from a guild
        :param hook_id: ID of the hook to retrieve
        :return: Webhook object, or None if it can't be found
        """
        hooks = await guild.webhooks()
        for hook in hooks:
            if hook.id == int(hook_id):
                return hook
        else:
            return None

    async def _send_hook(self, ctx, hook_id: str, target_guild: Guild, message: str):
        bot_created_hook_ids = self.config.smembers(self.hook_id_config_key.format(target_guild.id))
        if hook_id not in bot_created_hook_ids:
            await ctx.send("That webhook wasn't made by me.")
            return

        hook = await self._get_hook(hook_id, target_guild)

        try:
            await hook.send(message)
            await ctx.send("Hook sent successfully.")
        except discord.ClientException:
            await ctx.send("Couldn't send the hook.")

    @hook.command(aliases=["send"])
    async def send_in_guild(self, ctx, hook_id: str, *, message: str):
        """
        Send a message through a bot-managed webhook.
        :param ctx: Context
        :param hook_id: ID of the webhook to use.
        :param message: String message to make the body of the message.
        """

        if not ctx.guild or not self._check_permissions(ctx):
            return

        await self._send_hook(ctx, hook_id, ctx.guild, message)

    @hook.command(aliases=["send_external"])
    async def send_to_guild(self, ctx, hook_id: str, dest_guild_id: str, *, message: str):
        """
        Send a message through a bot-managed webhook in a different server.
        Ideally, this would be used when sending from DMs.
        :param ctx: context
        :param hook_id: ID of the hook to send through
        :param dest_guild_id: Target guild to send the hook to.
        :param message: String contents of the message.
        """

        guild = self.bot.get_guild(int(dest_guild_id))

        if guild:
            await self._send_hook(ctx, hook_id, guild, message)


def setup(bot):
    bot.add_cog(WebHooks(bot))
