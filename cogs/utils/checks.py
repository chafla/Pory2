
from typing import Callable, Union

import discord.utils

from discord.ext import commands
from discord import DMChannel, Guild, Message, Role
from discord.ext.commands import Context, Command


T_Check = Callable[[Callable[[Context], bool]], Command]


# More code from robodanny

sudoers = {
    78716152653553664,
    125435062127820800
}


def sudo_user_check(user: discord.User) -> bool:
    return user.id in sudoers

# The original function
def sudo_check(message: Message) -> bool:
    return sudo_user_check(message.author)


# And the function that works as a decorator
def sudo() -> T_Check:
    return commands.check(
        lambda ctx: sudo_check(ctx.message)
    )


def r_pokemon_check(server: Guild) -> bool:
    return server.id == 111504456838819840


def r_md_check(server: Guild) -> bool:
    return server.id == 117485575237402630


def pm_check(channel: Guild) -> bool:
    return isinstance(channel, discord.DMChannel)


def has_role(ctx: Union[Context, discord.Message], check: Callable[[Role], bool]) -> bool:
    """
    Check if someone has a role,
    :param ctx:
    :param check: Prepped find() argument
    :return: Whether or not the role was found
    """
    try:
        message = ctx.message
        ch = ctx.message.channel
        author = ctx.message.author
    except AttributeError:
        message = ctx
        ch = message.channel
        author = message.author

    if sudo_check(message):
        return True

    if isinstance(ch, discord.DMChannel):
        return False  # can't have roles in PMs

    # Take a prepped find() argument and pass it in
    role = discord.utils.find(check, author.roles)
    return role is not None


def is_pokemon_mod() -> T_Check:
    def predicate(ctx: Context) -> bool:
        return has_role(ctx,
                        lambda r: r.id == 278331223775117313
                        ) or (
                        not pm_check(ctx.message.channel)
                        and ctx.message.guild.id == 146626123990564864
                        )
    return commands.check(predicate)


def is_leader() -> T_Check:
    def predicate(ctx: Context) -> bool:
        return has_role(ctx, lambda r: r.id == 325763695533883392)
    return commands.check(predicate)


def in_pm() -> T_Check:
    def predicate(ctx: Context) -> bool:
        return isinstance(ctx.message.channel, DMChannel)
    return commands.check(predicate)


def not_in_oaks_lab() -> T_Check:
    def predicate(ctx: Context) -> bool:
        return isinstance(
            ctx.message.channel, discord.DMChannel
        ) or (
                ctx.message.guild is not None
                and ctx.message.guild.id != 204402667265589258
        )
    return commands.check(predicate)


def not_in_pokemon() -> T_Check:
    def predicate(ctx: Context) -> bool:
        return isinstance(
            ctx.message.channel, discord.DMChannel
        ) or (
                ctx.message.guild is not None
                and ctx.message.guild.id != 111504456838819840
        )
    return commands.check(predicate)


def mod_server_check(guild: Guild) -> bool:
    return guild.id == 146626123990564864


def mod_server() -> T_Check:
    def predicate(ctx: Context) -> bool:
        return mod_server_check(ctx.message.guild) or sudo_check(ctx.message)
    return commands.check(predicate)


def is_regular() -> T_Check:
    # Hope you've been eating your fiber
    def predicate(ctx: Context) -> bool:
        return isinstance(
            ctx.message.channel, discord.DMChannel
        ) or not r_pokemon_check(ctx.message.guild) or (
                r_pokemon_check(ctx.message.guild)
                and has_role(ctx, lambda r: r.id == 117242433091141636)
        )
    return commands.check(predicate)


def can_tag() -> T_Check:
    def predicate(ctx: Context) -> bool:
        message = ctx.message
        if sudo_check(message):
            return True
        elif message.author.id in []:
            return True
        else:
            return False
    return commands.check(predicate)


def has_manage_roles() -> T_Check:
    """Check that the user has the Manage Roles Permission"""
    def predicate(ctx: Context) -> bool:
        if isinstance(ctx.channel, discord.DMChannel):
            return False
        user_perms = ctx.author.guild_permissions
        return user_perms.manage_roles
    return commands.check(predicate)


def has_manage_guild() -> T_Check:
    """Check that the user has the Manage Roles Permission"""
    def predicate(ctx: Context) -> bool:
        if isinstance(ctx.channel, discord.DMChannel):
            return False
        user_perms = ctx.author.guild_permissions
        return user_perms.manage_guild or sudo_user_check(ctx.author)
    return commands.check(predicate)


def r_pokemon() -> T_Check:
    """Check if it's the /r/pokemon server"""
    def predicate(ctx: Context) -> bool:
        return ctx.message.guild is not None and ctx.message.guild.id == 111504456838819840
    return commands.check(predicate)


def r_md() -> T_Check:
    def predicate(ctx: Context) -> bool:
        return ctx.message.guild is not None and ctx.message.guild.id == 117485575237402630 or sudo_check(ctx.message)
    return commands.check(predicate)


def not_pmdnd() -> T_Check:
    def predicate(ctx: Context) -> bool:
        return (isinstance(ctx.message.channel, discord.DMChannel) or
                (ctx.message.guild is not None and ctx.message.guild.id != 239125949122215952))
    return commands.check(predicate)


def not_rmd() -> T_Check:
    def predicate(ctx: Context) -> bool:
        return (isinstance(ctx.message.channel, discord.DMChannel) or
                (ctx.message.guild is not None and ctx.message.guild.id != 117485575237402630))
    return commands.check(predicate)


def leader_for_a_year() -> T_Check:
    def predicate(ctx) -> bool:
        return has_role(ctx, lambda r: r.id == 417055258716405761)
    return commands.check(predicate)


def in_cj() -> T_Check:
    def predicate(ctx):
        return ctx.message.guild is not None and ctx.message.guild.id in [283101596806676481, 344285545742204940]
    return commands.check(predicate)


def in_mez_server() -> T_Check:
    def predicate(ctx):
        return ctx.message.guild is not None and ctx.message.guild.id == 344285545742204940
    return commands.check(predicate)