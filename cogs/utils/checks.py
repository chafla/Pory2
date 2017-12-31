from discord.ext import commands
import discord.utils
from discord import DMChannel

# More code from robodanny


# The original function
def sudo_check(message):
    return message.author.id == 78716152653553664 or message.author.id == 125435062127820800


# And the function that works as a decorator
def sudo():
    return commands.check(lambda ctx: sudo_check(ctx.message))


def r_pokemon_check(server):
    return server.id == 111504456838819840


def r_md_check(server):
    return server.id == 117485575237402630


def pm_check(channel):
    return isinstance(channel, discord.DMChannel)


def has_role(ctx, check):
    """
    Check if someone has a role,
    :param ctx:
    :param check: Prepped find() argument
    :return: Whether or not the role was found
    """
    message = ctx.message
    if sudo_check(message):
        return True

    ch = ctx.message.channel
    author = ctx.message.author
    if isinstance(ch, discord.DMChannel):
        return False  # can't have roles in PMs

    # Take a prepped find() argument and pass it in
    role = discord.utils.find(check, author.roles)
    return role is not None


def is_pokemon_mod():
    def predicate(ctx):
        return has_role(ctx, lambda r: r.id == 278331223775117313) or (not pm_check(ctx.message.channel) and
                                                                       ctx.message.guild.id == 146626123990564864)
    return commands.check(predicate)


def is_leader():
    def predicate(ctx):
        return has_role(ctx, lambda r: r.id == 325763695533883392)
    return commands.check(predicate)


def in_pm():
    def predicate(ctx):
        return isinstance(ctx.message.channel, DMChannel)
    return commands.check(predicate)


def not_in_oaks_lab():
    def predicate(ctx):
        return isinstance(ctx.message.channel, discord.DMChannel) or (ctx.message.guild is not None
                                                                      and ctx.message.guild.id != 204402667265589258)
    return commands.check(predicate)


def not_in_pokemon():
    def predicate(ctx):
        return isinstance(ctx.message.channel, discord.DMChannel) or (ctx.message.guild is not None
                                                                      and ctx.message.guild.id != 111504456838819840)
    return commands.check(predicate)


def mod_server_check(guild):
    return guild.id == 146626123990564864


def mod_server():
    def predicate(ctx):
        return mod_server_check(ctx.message.guild) or sudo_check(ctx.message)
    return commands.check(predicate)


def is_regular():
    # Hope you've been eating your fiber
    def predicate(ctx):
        return isinstance(ctx.message.channel, discord.DMChannel) or not r_pokemon_check(ctx.message.guild) or \
               (r_pokemon_check(ctx.message.guild) and has_role(ctx, lambda r: r.id == 117242433091141636))
    return commands.check(predicate)


def can_tag():
    def predicate(ctx):
        message = ctx.message
        if sudo_check(message):
            return True
        elif message.author.id in []:
            return True
        else:
            return False
    return commands.check(predicate)


def r_pokemon():
    """Check if it's the /r/pokemon server"""
    def predicate(ctx):
        return ctx.message.guild is not None and ctx.message.guild.id == 111504456838819840
    return commands.check(predicate)


def r_md():
    def predicate(ctx):
        return ctx.message.guild is not None and ctx.message.guild.id == 117485575237402630
    return commands.check(predicate)


def not_pmdnd():
    def predicate(ctx):
        return ctx.message.guild is not None and ctx.message.guild.id != 239125949122215952
    return commands.check(predicate)


def not_rmd():
    def predicate(ctx):
        return ctx.message.guild is not None and ctx.message.guild.id != 117485575237402630
    return commands.check(predicate)


def explicit_whitelist():
    """Whitelist for explicit commands"""
    def predicate(ctx):
        return ctx.message.channel.id in [262993960035680256, 274063615307546625, 274734349981712385,
                                          157365909864972288, 290715803882487809]
    return commands.check(predicate)
