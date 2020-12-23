"""A pokemon tourney for the mods, woo hoo"""
import logging
from typing import Dict

import discord
from discord.ext import commands
from discord.ext.commands import Context
from redis import RedisError

from .utils import checks, utils

log = logging.getLogger()

# TODO Add support for a hard mode that allows for a second challenge
# TODO Add w/l support

victory_message = """
**Congratulations, {}!**
You've been awarded {}'s badge! {}
{}
You can view your current badge collection by using `!league badge_case`."""

ribbon_get_message = """
**Congratulations, {0.mention}!**
%s
You've been granted the {1}! {2}

You can view your current badge collection by using `!league badge_case`
"""

default_ribbon_desc = """
You've been granted the {1}!
"""

new_medallion_piece_message = """
**Congratulations, {}!**
You've been awarded a piece of the {}! {}
You now have {}/{} pieces of the medallion, putting you one step closer towards completing it. 
Collect the rest by challenging moderators!
"""

medallion_complete_message = """
**Congratulations, {}!**
You've just collected **all** of the pieces of the {}! Putting them together, you now have a full medallion! {}
Thank you for participating in the event, and enjoy your permanent medallion in your badge case!

You can view your badge case by using `!league badge_case`."""


class PokemonTourney(commands.Cog):

    # Emoji name for each badge.
    _badges = {
        111682132115509248: "raffleiBadge",         # Tech
        136742503993966592: "explorerBadge",        # Lemonberry
        228201428177387523: "dragonicBadge",        # Semper
        225813236589527041: "elysianBadge",         # Fable
        # 125040405212430336: "prismBadge",         # Fluffy
        114994340320903175: "steamBadge",           # flare
        148978986045669378: "sierraBadge",          # dom
        190551860996734976: "varianceBadge",        # hiccup
        105175807994945536: "chronoBadge",          # quote
        209270029290569740: "fancyBadge",           # josh
        163368710915096576: "enlightenmentBadge",   # sol
        265965616551297024: "clockoutBadge",        # RunTime256
        195404515711778817: "depthsBadge",          # AceFyre
        # 78716152653553664: "baneBadge",           # Luc (debugging)
        227979061656289282: "flakeBadge",           # Monk
        292126215895252993: "fluxBadge",            # Bounty
        145954290718998529: "pinnacleBadge"         # Surv
    }

    _ribbons = {
        "League Champion": "championribbon",
        "Elite League Champion": "championribbon2",
        "Flawless Ribbon": "flawlessRibbon",
    }

    _champion_message = {
        "League Champion": "You've completed 8 Mod League Challenges and earned a role for your account along side a "
                           "nifty **Champion's Ribbon**!!\n",
        "Elite League Champion": "You've completed all current Mod League Challenges and have earned an "
                                 "**Elite Champion's Ribbon**!!\n",
    }

    # Little "titles" for people's progress
    _titles = {

    }

    _retired_members = [
        114994340320903175,  # flare
        136742503993966592,  # lemonberry
        190551860996734976,  # hiccup
    ]

    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config
        self.emb_pag = utils.Paginator(page_limit=1020, trunc_limit=1850)

    @property
    def emoji_pool(self):
        return self.bot.get_guild(320254070453567489).emojis + self.bot.get_guild(458474187988664333).emojis

    @property
    def emoji_guild(self):
        return self.bot.get_guild(320254070453567489)

    @property
    def _leader_ids(self):
        """More efficient way to find out all of the active leaders than searching"""
        ids = set()
        for key in self.config.scan_iter("config:pkmn_tourney:leaders:*"):
            *_, idx = key.split(":")
            try:
                ids.add(int(idx))
            except ValueError:
                continue
        return ids

    @property
    def _leader_keys(self):
        return ["config:pkmn_tourney:leaders:{}".format(i) for i in self._leader_ids]

    @property
    def badges(self) -> Dict[int, str]:
        """

        :return: {user_id: badge_name} for each badge
        """
        return {int(idx): self.config.hget("config:pkmn_tourney:leaders:{}".format(idx), "badge_emoji")
                for idx in self._leader_ids}

    @property
    def ribbons(self):
        """
        Get a dictionary of all ribbons.
        Ribbons are stored in redis under
            config:pkmn_tourney:ribbons:<emoji>
        where emoji is in the format `xRibbon`
        :return: Hashmap consisting of {title: emoji} pairs
        """
        ribbons = {}
        for key in self.config.scan_iter("config:pkmn_tourney:ribbons:*"):
            *_, emoji = key.split(":")
            ribbon_info = self.config.hgetall(key)
            try:
                ribbons[ribbon_info["title"]] = ribbon_info  # For backwards compatibility
            except KeyError:
                log.warning("Invalid ribbon in db: {}: {}".format(key, ribbon_info))
        return ribbons

    @property
    def inactive_leaders(self):
        """Returns IDs of inactive leaders"""
        inactives = []
        for idx in self._leader_ids:
            if self.config.hget("config:pkmn_tourney:leaders:{}".format(idx), "inactive"):
                inactives.append(idx)
        return inactives

    @property
    def green_dot_emoji(self):
        return self.bot.get_emoji(329131173441961995)

    @property
    def pokemon_guild(self):
        return self.bot.get_guild(111504456838819840)
        # return self.bot.get_guild(78716585996455936)

    @property
    def champion_role(self):
        return discord.utils.get(self.pokemon_guild.roles, id=334492243928809472)

    @property
    def leader_for_a_year_role(self):
        return discord.utils.get(self.pokemon_guild.roles, id=417055258716405761)

    @property
    def medallions(self):
        medallions = {}
        for key in self.config.scan_iter("config:pkmn_tourney:medallions:*"):
            *_, emoji = key.split(":")
            medallions[emoji] = self.config.hgetall(key)
        return medallions

    @property
    def active_medallion(self):
        active_medallion_emoji = self.config.get('config:pkmn_tourney:active_medallion')
        if str(active_medallion_emoji) == "None" or not active_medallion_emoji:
            return None
        else:
            return self.config.hgetall("config:pkmn_tourney:medallions:{}".format(active_medallion_emoji))

    def _get_medallion_progress_emoji(self, user_pieces_count, base_name):
        """
        Return the emoji name for a medallion given the number of pieces collected.
        :param user_pieces_count: Total number of pieces a user has
        :param base_name: Base medallion name
        :return: Medallion emoji name formatted correctly to reflect pieces.
        """
        if user_pieces_count == 0:
            return base_name + "Unattained"
        # If this fails it's probably because the medallion doesn't exist
        total_pieces = int(self.config.hget("config:pkmn_tourney:medallions:{}".format(base_name), "pieces"))
        if user_pieces_count < total_pieces:
            return base_name + str(user_pieces_count)
        else:
            return base_name + "Complete"

    def _update_db(self):
        # self.config.hmset("config:pkmn_tourney:ribbons", self._ribbons)

        # Transfer badges
        print("Updating things")
        # rip fluffy
        self.config.delete("config:pkmn_tourney:leaders:125040405212430336:easy")
        self.config.delete("config:pkmn_tourney:leaders:125040405212430336:normal")
        self.config.delete("config:pkmn_tourney:leaders:125040405212430336")
        for key in self.config.scan_iter("user:pkmn_tourney:*"):
            *_, container, user_id = key.split(":")
            if container == "fall_medal":
                self.config.hset("user:{}:pkmn_tourney:medallions:pumpkinRibbon".format(user_id),
                                 "pieces",
                                 int(self.config.scard("user:pkmn_tourney:fall_medal:{}".format(user_id))))

            elif container != "medallions":
                self.config.sadd("user:{}:pkmn_tourney:{}".format(user_id, container), *self.config.smembers(key))

            self.config.delete(key)

        self.config.set("config:pkmn_tourney:active_medallion", None)

        flawless_ribbon = {
            "title": "Flawless Ribbon",
            "emoji": "flawlessRibbon",
            "desc": "You've fought hard and obtained a Flawless Victory! "
                    "We can't we all be as awesome as you, {0.name}? "
        }

        self.config.hmset("config:pkmn_tourney:ribbons:flawlessRibbon", flawless_ribbon)

        for ribbon_name, msg in self._champion_message.items():
            ribbon = {
                "title": ribbon_name,
                "emoji": self._ribbons[ribbon_name],
                "desc": msg
            }

            self.config.hmset("config:pkmn_tourney:ribbons:{}".format(self._ribbons[ribbon_name]), ribbon)

        for leader_id, badge_name in self._badges.items():
            battle_format = self.config.hget("config:pkmn_tourney:leaders:{}:normal".format(leader_id), "format")
            if battle_format is None:
                battle_format = self.config.hget("config:pkmn_tourney:leaders:{}".format(leader_id), "format_normal")

            self.config.delete("config:pkmn_tourney:leaders:{}:easy".format(leader_id))
            self.config.delete("config:pkmn_tourney:leaders:{}:normal".format(leader_id))
            leader_info = {
                "format_normal": battle_format,
                "badge_emoji": badge_name,
                "inactive": "False" if leader_id not in self._retired_members else "True",
            }
            self.config.hmset("config:pkmn_tourney:leaders:{}".format(leader_id), leader_info)

        fall_medal = {
            "pieces": 3,
            "title": "Harvest Medallion",
            "emoji": "pumpkinRibbon"

        }

        self.config.hmset("config:pkmn_tourney:medallions:pumpkinRibbon", fall_medal)

    def _is_inactive(self, member_id):
        return self.config.hget("config:pkmn_tourney:leaders:{}".format(member_id), "inactive")

    def _get_emoji_from_name(self, name):
        if name is None:
            return "\N{QUESTION MARK}"
        else:
            return discord.utils.get(self.emoji_pool, name=name)

    def _get_mod_emoji(self, member_id):
        """Get emoji directly from mod id"""
        return discord.utils.get(self.emoji_pool, name=self.badges[member_id])

    def _get_badge_short_name(self, member_id):
        return self.badges[member_id][:-5]  # Chop off "badge"

    def get_in_the_gym_message(self, include_timestamp=False, include_online_members=False):
        output = {
            "offline": [],
            "online": [],
            "in_the_gym": []
        }

        for user_id in self.badges:
            mem = self.pokemon_guild.get_member(user_id)
            if mem is not None and not self._is_inactive(mem.id):
                if discord.utils.get(mem.roles, name="In The Gym"):
                    output["in_the_gym"].append("{} {}".format(str(self.green_dot_emoji), mem.display_name))
                elif mem.status not in [discord.Status.offline, discord.Status.invisible] and include_online_members:
                    output["online"].append("🔵 {}".format(mem.display_name))
                else:
                    output["offline"].append("⚫ {}".format(mem.display_name))
        sorted_output = sorted(output["in_the_gym"]) + sorted(output["online"]) + (sorted(output["offline"]))
        embed = discord.Embed(color=discord.Color.blue(), description="\n".join(sorted_output))
        embed.set_author(name="Current active gym leaders", icon_url=self.bot.user.avatar_url)
        if include_timestamp:
            embed.set_footer(text="Last updated {}".format(utils.get_timestamp()))

        return embed

    async def grant_badge_to_target(self, ctx: Context, target: discord.Member, badge_holder: discord.Member):
        """
        Grant a badge to a user. Takes care of all of the ceremony and stuff as well.
        :param ctx: Message context.
        :param target: User to add the badge to.
        :param badge_holder: Member who holds the badge.
        """
        badges = self.badges
        ribbons = self.ribbons
        badges_key = "user:{}:pkmn_tourney:badges".format(target.id)
        self.config.sadd(badges_key, badges[badge_holder.id])

        total_badges = self.config.scard(badges_key)
        if total_badges == 8:
            self.config.sadd("user:{}:pkmn_tourney:ribbons".format(target.id), ribbons["League Champion"])
            await target.add_roles(self.champion_role)
            champion_msg = self._champion_message["League Champion"].format(
                self._get_emoji_from_name(ribbons["League Champion"]))
        elif total_badges == len(self.badges.keys()) - len(self.inactive_leaders):
            self.config.sadd("user:{}:pkmn_tourney:ribbons".format(target.id), ribbons["Elite League Champion"])
            if not self.config.sismember("user:{}:pkmn_tourney:ribbons".format(target.id), "Elite League Champion"):
                champion_msg = self._champion_message["Elite League Champion"].format(
                    self._get_emoji_from_name(ribbons["Elite League Champion"]))
            else:
                champion_msg = ""
            self.config.sadd("user:{}:pkmn_tourney:ribbons".format(target.id), ribbons["Elite League Champion"])

        else:
            champion_msg = ""
        await ctx.send(victory_message.format(target.mention, badge_holder.name,
                                              str(self._get_mod_emoji(badge_holder.id)), champion_msg))

    @commands.group()
    async def league(self, ctx):
        """Type !help league for tourney commands"""
        pass

    @league.command()
    async def badge_info(self, ctx, badge_name: str):
        """Retreives info about a particular badge"""
        for mem_id, badge in self.badges.items():
            not_in_server = False
            short_name = badge[:-5]
            if badge_name == short_name or badge_name == badge:
                mem = self.pokemon_guild.get_member(mem_id)
                if not mem:
                    # user has left the server
                    mem = self.bot.get_user(mem_id)
                    not_in_server = True

                desc = "{} Badge{}".format(short_name,
                                           "\n*(Inactive)*" if self._is_inactive(mem_id) or not_in_server else "")

                embed = discord.Embed(description=desc)

                embed.set_author(name="{}'s badge.".format(mem.name, short_name),
                                 icon_url=mem.avatar_url)
                embed.set_thumbnail(url=self._get_emoji_from_name(badge).url)
                await ctx.send(embed=embed)
                return
        else:
            await ctx.send("Badge not found.")
            return

    @checks.is_pokemon_mod()
    @league.command()
    async def set_format(self, ctx, *, format_info: str):
        # Future implementation of difficulty levels

        # if level in ["normal", "hard"]:
        #     self.config.hset("config:pkmn_tourney:leaders:{}".format(ctx.message.author.id),
        #                      "format_{}".format(level), format_info)
        #     await ctx.send("\N{OK HAND SIGN}")
        # else:
        #     raise commands.UserInputError("Levels are `normal` and `hard`.")

        self.config.hset("config:pkmn_tourney:leaders:{}".format(ctx.message.author.id),
                         "format_normal", format_info)
        await ctx.send("\N{OK HAND SIGN}")

    @league.command(aliases=["profile"])
    async def badge_case(self, ctx, *, member: discord.Member=None):
        """Show a user's profile with corresponding badges based on the mods they've defeated."""

        # Caching values so we only read them once
        inactive_leaders = self.inactive_leaders
        ribbons = self.ribbons
        badges = self.badges
        active_medallion = self.active_medallion

        def get_collection(key):
            return list(self.config.smembers(key)) if self.config.exists(key) else []

        def get_medallions(user_id):
            active_emoji_in_case = False
            medallions = {}

            active_medallion_emoji = self.active_medallion["emoji"] if active_medallion is not None else None
            for hm_key in self.config.scan_iter("user:{}:pkmn_tourney:medallions:*".format(user_id)):
                *_, emoji_name = hm_key.split(":")
                piece_count = int(self.config.hget(hm_key, "pieces"))
                medallion_progress_emoji = self._get_medallion_progress_emoji(piece_count, emoji_name)
                medallion_title = self.config.hget("config:pkmn_tourney:medallions:{}".format(emoji_name), "title")
                # only show partial medallions if they're completed
                if "complete" not in medallion_progress_emoji.lower() and emoji_name != active_medallion_emoji:
                    continue
                else:
                    medallions[medallion_title] = medallion_progress_emoji
                    # This is gross but I'll have to take it for now
                    if active_medallion is not None and active_medallion_emoji in medallion_progress_emoji:
                        active_emoji_in_case = True

            if not active_emoji_in_case and active_medallion_emoji is not None:
                medallions[active_medallion["title"]] = active_medallion_emoji + "Unattained"

            return medallions

        if member is None:
            member = ctx.message.author

        embed = discord.Embed(color=discord.Color.blurple())

        embed.set_author(name="Badge collection for {}".format(member.display_name),
                         icon_url=member.avatar_url)

        badge_collection = get_collection("user:{}:pkmn_tourney:badges".format(member.id))
        ribbon_collection = get_collection("user:{}:pkmn_tourney:ribbons".format(member.id))
        medallion_collection = get_medallions(member.id)  # Returns a tuple (title, progress_emoji)

        # If a badge hasn't been collected, its icon is replaced with a grayed out version.
        # These grayed out badges are shown as `badgenameUnattained`

        for mod_id, badge in badges.items():
            if mod_id in inactive_leaders and badge not in badge_collection:
                continue
            elif badge not in badge_collection:
                badge += "Unattained"

            # we only care about the username here: grab it from the general bot context if we can
            # if that doesn't work, then we'll just display something generic
            mod_user = self.bot.get_user(mod_id)
            if mod_user is None:
                mod_name = "<Someone long gone>"
            else:
                mod_name = mod_user.name

            embed.add_field(name=mod_name,
                            value=str(self._get_emoji_from_name(badge)))

        # Clean up in case they have a badge that isn't reflected in the active mod badges
        for badge_name in self.config.smembers("user:{}:pkmn_tourney:badges".format(member.id)):
            if badge_name not in badges.values():
                embed.add_field(name=badge_name[:-5] + "Badge",
                                value=str(self._get_emoji_from_name(badge_name)))

        for title in sorted(ribbons.keys(), reverse=True):
            if ribbons[title]["emoji"] in ribbon_collection:
                embed.add_field(name=title, value=str(self._get_emoji_from_name(ribbons[title]["emoji"])))

        # Sort over this one in a special way because we only care about the collected ones
        # and possibly the active yet uncollected one
        for title, emoji in medallion_collection.items():
            embed.add_field(name=title, value=str(self._get_emoji_from_name(emoji)))

        await ctx.send(embed=embed)

    @checks.r_pokemon()
    @league.command()
    async def leader_info(self, ctx, *, member: discord.Member):
        """Get information on a certain gym leader, including their team and format."""
        if member is None or member.id not in self.badges:
            await ctx.send("User is not currently a leader.")
            return
        embed = discord.Embed(color=discord.Color.blue(),
                              description="{} Badge".format(self._get_badge_short_name(member.id).capitalize()))
        embed.set_author(name="Leader information for {}{}".format(
            member.name, " (retired)" if self._is_inactive(member.id) else ""), icon_url=member.avatar_url)
        embed.set_thumbnail(url=self._get_mod_emoji(member.id).url)
        user_info = self.config.hgetall("config:pkmn_tourney:leaders:{}".format(member.id))
        for difficulty, league_name in [("format_normal", "Mod League"), ("format_hard", "Mod League Plus")]:
            # user_info = self.config.hgetall("config:pkmn_tourney:leaders:{}:{}".format(member.id, difficulty))
            try:
                # If we don't have the format, just omit the field. We can still work if we don't have a team.
                self.emb_pag.set_headers([league_name])
                for h, p in self.emb_pag.paginate("{}\n{}".format(user_info[difficulty],
                                                                  user_info.get("{}_team".format(difficulty), ""))):
                    embed.add_field(name=h, value=p)
            except KeyError:
                pass

        await ctx.send(embed=embed)

    @checks.r_pokemon()
    @commands.command()
    async def in_the_gym(self, ctx):
        """View a list of mod league leaders."""
        await ctx.send("This command has been removed, please check the channel pins in <#325764029538762763> to "
                       "view an up-to-date list of leaders.")

    @checks.is_pokemon_mod()
    @league.command()
    async def grant_badge(self, ctx, *, member: discord.Member):
        """Grant the mod's own badge to the member."""
        await self.grant_badge_to_target(ctx, member, ctx.message.author)

    @checks.is_pokemon_mod()
    @league.command()
    async def grant_other_badge(self, ctx, badge_holder: discord.Member, target: discord.Member):
        """Grant some other mod's badge to a member."""
        await self.grant_badge_to_target(ctx, target, badge_holder)

    @checks.is_pokemon_mod()
    @league.command()
    async def grant_ribbon(self, ctx, member: discord.Member, *, ribbon_name: str):
        """Grant a user a ribbon."""

        active_ribbons = self.ribbons  # Just pull this once

        if ribbon_name not in active_ribbons or not ribbon_name:
            await ctx.message.author.send("Ribbon doesn't exist. Active ribbons are {}".format(active_ribbons.keys()))
            return

        cur_ribbon = active_ribbons[ribbon_name]
        emoji = cur_ribbon["emoji"]

        if self.config.sismember("user:{}:pkmn_tourney:ribbons".format(member.id), emoji):
            await ctx.send("User {} already has the {}!".format(member.name, ribbon_name))
        else:
            self.config.sadd("user:{}:pkmn_tourney:ribbons".format(member.id), emoji)
            # This double formatting stuff is needed so that we can possibly inject format strings into descs.
            await ctx.send((ribbon_get_message % (cur_ribbon.get("desc", "") + "\n"))
                           .format(member, ribbon_name, self._get_emoji_from_name(emoji)))

    """
    Medallion representation:
    config:pkmn_tourney:medallions:<emoji>
        title: Full name to be displayed to the user as a title. e.g. "Harvest Medallion"
        emoji: Shortened name w/o type, except for pumpkin which is a special case.
        pieces: number of total pieces required to have a completed medal.
    
    user:<id>:pkmn_tourney:medallions:<emoji> (hm)
        pieces: number of pieces the user has
        (extra space to be expanded at some future point)
    
    """

    @checks.is_pokemon_mod()
    @league.command()
    async def grant_medal_piece(self, ctx, *, member: discord.Member):
        """Grants a piece of the current active medallion"""

        active_medal_info = self.active_medallion
        if active_medal_info is None:
            await ctx.send("This medallion is no longer addable.")
            return

        active_medal_name = active_medal_info["emoji"]

        if self.config.exists("user:{}:pkmn_tourney:medallions:{}".format(member.id, active_medal_info['emoji'])):
            user_medal_pieces_held = int(self.config.hget("user:{}:pkmn_tourney:medallions:{}".format(
                member.id, active_medal_name), "pieces"))
        else:
            user_medal_pieces_held = 0

        if user_medal_pieces_held == int(active_medal_info["pieces"]):
            await ctx.send("{} has already completed their {}!".format(member.mention,
                                                                       active_medal_info["title"]))
            return

        self.config.hincrby("user:{}:pkmn_tourney:medallions:{}".format(member.id, active_medal_name), "pieces", 1)
        user_medal_pieces_held += 1

        # Get the name combined with the number of pieces the user has -- or complete.
        full_emoji_name = self._get_medallion_progress_emoji(user_medal_pieces_held, active_medal_name)
        if "complete" in full_emoji_name.lower():
            await ctx.send(medallion_complete_message.format(member.mention, active_medal_info["title"],
                                                             self._get_emoji_from_name(full_emoji_name)))
        else:
            await ctx.send(new_medallion_piece_message.format(
                member.mention,
                active_medal_info["title"],
                self._get_emoji_from_name(full_emoji_name),
                user_medal_pieces_held,
                active_medal_info["pieces"]
            ))

    @checks.is_pokemon_mod()
    @league.command()
    async def create_ribbon(self, ctx, emoji_base_name: str, *, title: str):
        """Create a new ribbon"""
        new_ribbon = {
            "title": title,
            "emoji": emoji_base_name,
        }

        self.config.hmset("config:pkmn_tourney:ribbons:{}".format(emoji_base_name), new_ribbon)
        await ctx.send(
            "New ribbon created. You can update its description with `!set_ribbon_message <emoji> <message>`",
            embed=utils.embed_from_dict(new_ribbon, description="Current ribbon config")
        )

    @checks.is_pokemon_mod()
    @league.command()
    async def set_ribbon_message(self, ctx, emoji_name: str, *, description: str):
        """
        Set a special message for users when they are granted their ribbon.
        """
        ribbon_emoji = self.ribbons.values()

        if emoji_name not in ribbon_emoji:
            await ctx.message.author.send("Invalid ribbon emoji. Those that exist are {}".format(ribbon_emoji))
            return
        try:
            self.config.hset("config:pkmn_tourney:ribbons:{}".format(emoji_name), "desc", description)
        except RedisError:
            raise commands.BadArgument("Could not find that ribbon. Did you mean to input an emoji?")
        else:
            await ctx.send("Description for ribbon set.",
                           embed=utils.embed_from_dict(
                               self.config.hgetall("config:pkmn_tourney:ribbons:{}".format(emoji_name)),
                               description="Current ribbon config"))

    @checks.is_pokemon_mod()
    @league.command()
    async def create_new_medal(self, ctx, emoji_name: str, pieces: int, *, full_name: str):
        """Create a new medallion."""
        self.config.hmset("config:pkmn_tourney:medallions:{}".format(emoji_name), {
            "emoji": emoji_name,
            "title": full_name,
            "pieces": pieces
        })

        await ctx.send("\N{OK HAND SIGN}")

    @checks.is_pokemon_mod()
    @league.command()
    async def set_active_medal(self, ctx, emoji_name: str=None):
        """Set the medallion which will show in user's badge cases if incomplete."""
        medallions = self.medallions
        if emoji_name not in medallions and emoji_name is not None:
            await ctx.message.author.send("Medal doesn't exist. Addable medals are {}".format(medallions.keys()))
            return
        self.config.set("config:pkmn_tourney:active_medallion", emoji_name)
        await ctx.send("Active medallion set.",
                       embed=utils.embed_from_dict(self.active_medallion, description="Medallion info"))

    @checks.is_pokemon_mod()
    @league.command()
    async def add_leader(self, ctx, member: discord.Member, *, badge_emoji: str):
        """Add a new leader to the league."""
        base_leader_info = {
            "inactive": False,
            "badge_emoji": badge_emoji
        }

        self.config.hmset("config:pkmn_tourney:leaders:{}".format(member.id), base_leader_info)
        await ctx.send("\N{OK HAND SIGN}")

    @checks.is_pokemon_mod()
    @league.command()
    async def update_tournament_champion(self, ctx):
        """Update the database based on whoever holds the role of tournament champion"""
        try:
            cur_champion_id = int(self.config.hget("config:pkmn_tourney:champion", "user_id"))
        except RedisError:
            cur_champion_id = None
        cur_champion_member = discord.utils.find(self.pokemon_guild.members,
                                                 lambda m: any([r for r in m.roles if m.id == 417055258716405761]))

        # TODO clean up this repetition

        if cur_champion_id is None:
            if cur_champion_member is None:
                await ctx.send("There is currently no champion in the database, nor any member with the champion role.")
                return
            else:
                self.config.hset("config:pkmn_tourney:champion", "user_id", cur_champion_member.id)
                self.config.hmset("config:pkmn_tourney:leaders:{}".format(cur_champion_member.id), {
                    "inactive": True,  # Marked as inactive, they can still grant badges but won't show up otherwise
                    "temporary": True,
                    "badge_emoji": self.config.hget("config:pkmn_tourney:champion:badge_emoji"),
                    "format_normal": self.config.hget("config:pkmn_tourney:champion:format")
                })
                await ctx.send("Member {} was registered as a new leader.".format(cur_champion_member))
        else:
            if cur_champion_member is None:
                # Clear the current active member
                self.config.hdel("config:pkmn_tourney:champion", "user_id")
                await ctx.send("Current leader has been reset in database.")
            elif cur_champion_member.id == cur_champion_id:
                await ctx.send("Cur champion in database matches user with role, no changes were made.")
                return
            else:
                # cur champion in db is not None but a different user has the role
                self.config.hset("config:pkmn_tourney:champion", "user_id", cur_champion_member.id)
                self.config.hmset("config:pkmn_tourney:leaders:{}".format(cur_champion_member.id), {
                    "inactive": True,
                    "temporary": True,
                    "badge_emoji": self.config.hget("config:pkmn_tourney:champion:badge_emoji"),
                    "format_normal": self.config.hget("config:pkmn_tourney:champion:format")
                })

                await ctx.send("Member {} was registered as the new leader.".format(cur_champion_member))

    @checks.is_pokemon_mod()
    @league.command()
    async def set_champion_badge(self, ctx, badge_emoji: str):
        self.config.hset("config:pkmn_tourney:champion", "badge_emoji", badge_emoji)

        try:
            cur_champion_id = self.config.hget("config:pkmn_tourney:champion", "user_id")
            self.config.hset("config:pkmn_tourney:leaders:{}".format(cur_champion_id), "badge_emoji", badge_emoji)
        except RedisError:
            pass

        await ctx.send("Badge emoji set to `{}`".format(badge_emoji))

    @checks.is_pokemon_mod()
    @league.command()
    async def set_champion_format(self, ctx, *, format_msg: str):
        self.config.hset("config:pkmn_tourney:champion", "format", format_msg)
        try:
            cur_champion_id = self.config.hget("config:pkmn_tourney:champion", "format")
            self.config.hset("config:pkmn_tourney:leaders:{}".format(cur_champion_id), "format_normal", format_msg)
        except RedisError:
            pass

        await ctx.send("Description set.")

    @checks.is_pokemon_mod()
    @league.command()
    async def mark_leader_inactive(self, ctx, member: discord.Member):
        """Mark a leader as inactive, hiding their unattained badge from badge cases."""
        key = "config:pkmn_tourney:leaders:{}".format(member.id)
        if self.config.exists(key):
            self.config.hset(key, "inactive", True)
            await ctx.send("Member marked inactive.",
                           embed=utils.embed_from_dict(self.config.hgetall(key)))
        else:
            await ctx.send("Invalid member.")
            return

    @checks.sudo()
    @commands.command(enabled=False)
    async def update_db(self, ctx):
        self._update_db()

    @commands.Cog.listener()
    async def on_timer_update(self, secs):
        if secs % 60 == 0:
            chan = self.bot.get_channel(325764029538762763)
            gym_msg_id = self.config.get("config:pkmn_tourney:gym_message_id")
            if gym_msg_id is None:
                new_msg = await chan.send(embed=self.get_in_the_gym_message(include_timestamp=True))
                await new_msg.pin()
                self.config.set("config:pkmn_tourney:gym_message_id", new_msg.id)
            else:
                try:
                    msg = await chan.fetch_message(int(gym_msg_id))
                except AttributeError:  # Usually pops up during debugging as chan is None
                    return

                try:
                    await msg.edit(embed=self.get_in_the_gym_message(include_timestamp=True))
                except (discord.HTTPException, discord.Forbidden):
                    try:
                        await chan.delete_message(msg)
                    except (discord.HTTPException, discord.Forbidden):
                        await msg.unpin()
                    msg = await chan.send(embed=self.get_in_the_gym_message(include_timestamp=True))
                    await msg.pin()
                    self.config.set("config:pkmn_tourney:gym_message_id", msg.id)


def setup(bot):
    bot.add_cog(PokemonTourney(bot))
