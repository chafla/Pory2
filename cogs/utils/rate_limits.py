import logging
import discord
from cogs.utils.errors import CommandBlacklisted, CommandRateLimited
from cogs.utils.redis_config import RedisConfig
import time

log = logging.getLogger()

config = RedisConfig()


class MemeCommand:
    """
    A meme command, or basically a tracked rate-limit.
    """

    instances = []
    server_blacklist = [146668917866102784]
    DEFAULT_COOLDOWN = 120

    def __new__(cls, *args, **kwargs):
        instance = object.__new__(cls)
        cls.instances.append(instance)
        return instance

    @classmethod
    def get_instances(cls):
        return cls.instances

    def __init__(self, name, ctx, cooldown=-1, action=None, kind=None, restricted=None):
        # Note: Default cooldown is -1 because of how nonetype objects work in python
        self._ts = 0
        self.has_alerted = False
        self._first_time = True
        self.name = name
        self.kind = kind
        self.action = action
        self.cooldown = cooldown if cooldown >= 0 else self.DEFAULT_COOLDOWN
        self.restricted = restricted
        self.server_id = ctx.message.guild.id if not isinstance(ctx.message.channel, discord.DMChannel) else None
        self.channel = ctx.message.channel
        self.channel_id = ctx.message.channel.id

    def __str__(self):
        return self.name

    @classmethod
    def get_meme(cls, command):
        return cls.instances[command]

    @property
    def channel_blacklist(self):
        return config.smembers("config:rate_limits:chan_blacklist")

    @staticmethod
    async def get_blacklist():
        return MemeCommand.channel_blacklist

    @staticmethod
    def increase_counter(ctx):
        """
        Increase the database counter for the command.
        """
        if not config.exists("misc:rate_limits:counters"):
            config.zadd("misc:rate_limits:counters", 1.0, ctx.command.name)
        else:
            config.zincrby("misc:rate_limits:counters", ctx.command.name)

    def _handle_rate_limit(self, ctx, ignore_blacklist, priority_blacklist):
        # TODO: Consider making a decorator
        """
        Wrapper and filter for certain commands. This function takes care of controlling meme commands by blacklisting
        them by server and channel, whitelisting some channels for rate-limit-free memefests, and most importantly
        rate-limiting commands.
        Formerly memes()

        :param ctx: Context object, to extract message from.
        :return: True if command would not be blocked by anything. Otherwise, returns False.
        """

        message = ctx.message

        # Exceptions

        if isinstance(ctx.message.channel, discord.DMChannel):
            return True

        elif ctx.message.author.id == 78716152653553664:
            return True

        elif not ignore_blacklist and \
                (self.channel_blacklist is not None and str(message.channel.id) in self.channel_blacklist):
            msg = "This command has been disabled for this channel."
            if message.guild.id == 111504456838819840:  # Only do this in the r/pokemon server
                msg = "Please use this command in <#198187334968016906>."  # #bot_spam's ID
            raise CommandBlacklisted(msg)

        elif priority_blacklist is not None and ctx.message.channel.id in priority_blacklist:
            raise CommandBlacklisted("This command has been disabled for this channel.")

        elif self.server_id in self.server_blacklist:
            raise CommandBlacklisted("This command has been blacklisted from this server.")

        # If no blocks happen, execute main rate limit stuff.

        # time.perf_counter() is important since time.clock isn't multiplat.
        # Leaving the dif as a float gives us absolute accuracy in difs.
        dif = time.perf_counter() - self._ts

        # We check here to see if there are any extra coefficients to multiply the current meme by
        coeff = config.get("chan:{}:rate_limits:cooldown_ratio".format(ctx.message.channel.id))
        cooldown = int(float(coeff) * self.cooldown) if coeff is not None else self.cooldown

        if self._first_time:  # Init, pretty much.
            self._ts = 0
            self._first_time = False
            self.increase_counter(ctx)
            return True

        elif dif < cooldown:  # if the time since the last command is less than the cooldown
            active_cd = cooldown - dif
            self.has_alerted = True
            raise CommandRateLimited(int(active_cd))

        elif dif > cooldown:  # if the time since the last meme is greater than the cooldown
            self._ts = time.perf_counter()
            self.has_alerted = False
            self.increase_counter(ctx)
            return True
        else:
            log.info("Bypassed rate-limit routines in {}".format(message.channel.id))
            return None

    @staticmethod
    def check_rate_limit(ctx, cooldown=-1, ignore_blacklist=False, cooldown_group=None, priority_blacklist=None):

        """
        Check if a command is rate-limited.
        :param ctx: Local context object.
        :param cooldown: Optional: Cooldown of command in seconds. Defaults to the default cooldown of 120s
        :param ignore_blacklist: Whether or not the command should bypass the blacklist by default
        :param cooldown_group: The name of the new rate limit object. To be used for command groups.
        :param priority_blacklist: List of channels that the command should be explicitly excluded from.
        :return: True if the command would not be rate-limited.
        """

        # TODO Make into a decorator
        cooldown_name = ctx.command.name if not cooldown_group else cooldown_group

        obj = discord.utils.get(MemeCommand.get_instances(), name=cooldown_name, channel_id=ctx.message.channel.id)
        if obj is None:
            obj = MemeCommand(cooldown_name, ctx, cooldown=cooldown)
        return obj._handle_rate_limit(ctx, ignore_blacklist, priority_blacklist)
