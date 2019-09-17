""" Fancy help formatter.
Written by SirThane (@sirthane on github)

Overrides the built-in help formatter.
All help messages will be embed and pretty.
Most of the code stolen from
discord.ext.commands.formatter.py and
converted into embeds instead of codeblocks.
Docstr on cog class becomes category.
Docstr on command definition becomes command
summary and usage.
Use [p] in command docstr for bot prefix.
See [p]help here for example.
await bot.formatter.format_help_for(ctx, command)
to send help page for command. Optionally pass a
string as third arg to add a more descriptive
message to help page.
e.g. format_help_for(ctx, ctx.command, "Missing required arguments")
discord.py 1.0.0a
Copyrights to logic of code belong to Rapptz (Danny)"""

import discord
from discord.ext import commands
from discord.ext.commands import formatter
from cogs.utils import utils
import re
import inspect
import itertools


empty = u'\u200b'


_mentions_transforms = {
    '@everyone': '@\u200beveryone',
    '@here': '@\u200bhere'
}


_mention_pattern = re.compile('|'.join(_mentions_transforms.keys()))


class Help(formatter.HelpFormatter):
    """Formats help for commands."""

    def __init__(self, bot, *args, **kwargs):
        self.bot = bot
        self.bot.remove_command('help')
        self.bot.formatter = self
        self.bot.help_formatter = self
        super().__init__(*args, **kwargs)

    @property
    def author(self):
        # Get author dict with username if PM and display name in guild
        if isinstance(self.context.channel, discord.DMChannel):
            name = self.bot.user.name
        else:
            name = self.context.guild.me.display_name if not '' else self.bot.user.name
        author = {
                'name': '{0} Help Manual'.format(name),
                'icon_url': self.bot.user.avatar_url_as(format='png')
            }
        return author

    @property
    def destination(self):
        return self.context.message.author if self.bot.pm_help else self.context.message.channel

    @property
    def color(self):
        if isinstance(self.context.channel, discord.DMChannel):
            return 0
        else:
            return self.context.me.color

    def _add_subcommands(self, cmds):
        entries = ''
        for name, command in cmds:
            if name in command.aliases:
                # skip aliases
                continue

            if self.is_cog() or self.is_bot():
                name = '{}{}'.format(self.clean_prefix, name)

            new_entry = '**{}{}**   {}\n'.format(name, ":" if command.short_doc else "", command.short_doc)
            if len(new_entry + entries) > 1020:
                entries += "..."  # TODO This should be paginated
                return entries
            else:
                entries += new_entry
        return entries

    def get_command_signature(self):
        """Retrieves the signature portion of the help page."""
        prefix = self.clean_prefix
        cmd = self.command
        try:
            signature = cmd.signature
        except KeyError:
            # This tends to happen with getting help for command groups
            signature = " <subcommand>"
        return prefix + signature

    async def format(self, ctx, command):
        """Formats command for output.
        Returns a dict used to build embed"""

        # All default values for embed dict
        self.command = command
        self.context = ctx
        embs = []
        base_emb = {
            'embed': {
                'title': '',
                'description': '',
            },
            'footer': {
                'text': self.get_ending_note()
            },
            'fields': []
        }

        emb = base_emb.copy()
        emb["fields"] = []  # Ensure we don't hang onto a pointer

        if not embs:  # Only run it for the first embed

            description = command.description if not self.is_cog() else inspect.getdoc(command)
            if not description == '' and description is not None:
                description = '*{0}*'.format(description)

            if description:
                # <description> portion
                emb['embed']['description'] = description

        if isinstance(command, discord.ext.commands.core.Command):
            # <signature portion>
            emb['embed']['title'] = emb['embed']['description']
            # If it's a command group, the command has an attribute `commands`

            emb['embed']['description'] = '`Syntax: {0}`'.format(self.get_command_signature())

            # <long doc> section
            if command.help:
                name = '__{0}__'.format(command.help.split('\n\n')[0])
                name_length = len(name) - 4
                value = command.help[name_length:].replace('[p]', self.clean_prefix)
                if value == '':
                    value = empty
                field = {
                    'name': name,
                    'value': value,
                    'inline': False
                }
                emb['fields'].append(field)

            # end it here if it's just a regular command
            if not self.has_subcommands():
                return emb

        def category(tup):
            # Turn get cog (Category) name from cog/list tuples
            cog = tup[1].cog_name
            if cog is None:
                cog = getattr(tup[1], "help_category", None)
            return '**__{}:__**'.format(cog) if cog is not None else '**__\u200bNo Category:__**'

        # Get subcommands for bot or category
        filtered = await self.filter_command_list()

        if self.is_bot():
            # Get list of non-hidden commands for bot.
            data = sorted(filtered, key=category)
            for category, commands in itertools.groupby(data, key=category):
                # there simply is no prettier way of doing this.
                field = {
                    'inline': False
                }
                commands = sorted(commands)
                if len(commands) > 0:
                    field['name'] = category
                    field['value'] = self._add_subcommands(commands)  # May need paginated
                    if len(field['value']) > 1024:
                        field['value'] = field['value'][:1019] + "..."
                    emb['fields'].append(field)

        else:
            # Get list of commands for category
            filtered = sorted(filtered)
            if filtered:
                field = {
                    'name': '**__Commands:__**' if not self.is_bot() and self.is_cog() else '**__Subcommands:__**',
                    'value': self._add_subcommands(filtered),  # May need paginated
                    'inline': False
                }

                emb['fields'].append(field)

        return emb

    async def format_help_for(self, ctx, command_or_bot, reason: str=None):
        """Formats the help page and handles the actual heavy lifting of how  ### WTF HAPPENED?
        the help command looks like. To change the behaviour, override the
        :meth:`~.HelpFormatter.format` method.
        Parameters
        -----------
        context: :class:`.Context`
            The context of the invoked help command.
        command_or_bot: :class:`.Command` or :class:`.Bot`
            The bot or command that we are getting the help of.
        Returns
        --------
        list
            A paginated output of the help command.
        """
        self.context = ctx
        self.command = command_or_bot
        emb = await self.format(ctx, command_or_bot)

        if reason:
            emb['embed']['title'] = reason

        embed = discord.Embed(color=self.color, **emb['embed'])
        embed.set_author(**self.author)
        for field in emb['fields']:
            embed.add_field(**field)
        embed.set_footer(**emb['footer'])
        await self.destination.send(embed=embed)

    def simple_embed(self, title=None, description=None, color=None, author=None):
        # Shortcut
        embed = discord.Embed(title=title, description=description, color=color)
        embed.set_footer(text=self.bot.formatter.get_ending_note())
        if author:
            embed.set_author(**author)
        return embed

    def cmd_not_found(self, cmd, color=0):
        # Shortcut for a shortcut. Sue me
        embed = self.simple_embed(title=self.bot.command_not_found.format(cmd),
                                  description='Commands are case sensitive. Please check your spelling and try again',
                                  color=color, author=self.author)
        return embed

    @commands.command(name='help')
    async def help(self, ctx, *cmds: str):
        """Shows help documentation.
        [p]**help**: Shows the help manual.
        [p]**help** command: Show help for a command
        [p]**help** Category: Show commands and description for a category"""
        self.context = ctx

        def repl(obj):
            return _mentions_transforms.get(obj.group(0), '')

        # help by itself just lists our own commands.
        if len(cmds) == 0:
            await self.bot.formatter.format_help_for(ctx, self.bot)
            return

        elif len(cmds) == 1:
            # try to see if it is a cog name
            name = _mention_pattern.sub(repl, cmds[0])
            command = None
            if name in self.bot.cogs:
                command = self.bot.cogs[name]
            else:
                command = self.bot.all_commands.get(name)
                if command is None:
                    await self.destination.send(embed=self.cmd_not_found(name, self.color))
                    return

            await self.bot.formatter.format_help_for(ctx, command)
        else:
            name = _mention_pattern.sub(repl, cmds[0])
            command = self.bot.all_commands.get(name)
            if command is None:
                await self.destination.send(embed=self.cmd_not_found(name, self.color))
                return

            for key in cmds[1:]:
                try:
                    key = _mention_pattern.sub(repl, key)
                    command = command.all_commands.get(key)
                    if command is None:
                        await self.destination.send(embed=self.cmd_not_found(key, self.color))
                        return
                except AttributeError:
                    await self.destination.send(embed=self.simple_embed(title=
                                           'Command "{0.name}" has no subcommands.'.format(command), color=self.color,
                                                                   author=self.author))
                    return

            await self.bot.formatter.format_help_for(ctx, command)


def setup(bot):
    bot.add_cog(Help(bot))
