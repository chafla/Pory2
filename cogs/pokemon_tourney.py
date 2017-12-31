"""A pokemon tourney for the mods, woo hoo"""
import discord
from discord.ext import commands
from .utils import checks, utils

# TODO Add support for a hard mode that allows for a second challenge
# TODO Add w/l support

victory_message = """
**Congratulations, {}!**
You've been awarded {}'s badge! {}
{}
You can view your current badge collection by using `!league badge_case`."""

flawless_victory_message = """
**Congratulations, {0.mention}**
You've fought hard and obtained a Flawless Victory! We can't we all be as awesome as you, {0.name}? 
Enjoy the new ribbon commemorating this rare achievement! {1} 

You can view your current badge collection by using `!league badge_case`.
"""


class PokemonTourney:

    # TODO
    # Add badge info, retired leaders, medallions, etc. to config and add commands for them so that they can be
    # updated without needing to hardcode everything

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
        227979061656289282: "flakeBadge"            # Monk
    }

    _ribbons = {
        "League Champion": "championribbon",
        "Elite League Champion": "championribbon2",
        "Flawless Ribbon": "flawlessRibbon",
    }

    _champion_message = {
        "League Champion": "\nYou've completed 8 Mod League Challenges and earned a role for your account along side a "
                           "nifty **Champion's Ribbon**!! {}\n",
        "Elite League Champion": "\nYou've completed all current Mod League Challenges and have earned an "
                                 "**Elite Champion's Ribbon**!! {}\n",
    }

    _medallion_message = [
        "",
        """**Congratulations, {}!**
You've been awarded **1/3** of the Harvest Medallion! {}  
Challenge **2** more moderators to gain the last *two* piece(s)!

You can view your current badge collection by using `!league badge_case`.""",
        """**Congratulations, {}!**
You've been awarded **2/3** of the Harvest Medallion! {}  
Challenge **1** more moderators to gain the last *one* piece(s)!

You can view your current badge collection by using `!league badge_case`.""",
        """**Congratulations, {}!**
You've successfully completed the Harvest Medallion! {}  
Thank you for participating in our Fall '17 event and enjoy your permanent ribbon in your badge case!

You can view your current badge collection by using `!league badge_case`."""
    ]

    _current_medallion = ["pumpkinRibbonUnattained", "pumpkinRibbon1", "pumpkinRibbon2", "pumpkinRibbonComplete"]

    # _active_medallion = {  # Moved to redis so it will be easily modifiable.
    #     "name": "Harvest Medallion",
    #     "badge": "fall_medal",
    # }

    _completed_medallions = {
        "Harvest Medallion": "pumpkinRibbonComplete",
    }

    # Little "titles" for people's progress
    # TODO?
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
    def emoji_guild(self):
        return self.bot.get_guild(320254070453567489)

    @property
    def _leader_ids(self):
        return list(self.config.smembers("config:pkmn_tourney:leader_ids"))

    @property
    def _leader_keys(self):
        return ["config:pkmn_tourney:leaders:{}".format(i) for i in self._leader_ids]

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
    def current_medallion(self):
        return self.config.hgetall('config:pkmn_tourney:current_medallion')

    def _update_db(self):
        for leader_id, badge_name in self._badges:
            battle_format = self.config.hget("config:pkmn_tourney:leaders:{}:normal".format(leader_id), "format")

            self.config.remove("config:pkmn_tourney:leaders:{}:easy".format(leader_id))
            self.config.remove("config:pkmn_tourney:leaders:{}:normal")
            leader_info = {
                "format_normal": battle_format,
                "badge_name": badge_name,
                "inactive": "False" if leader_id not in self._retired_members else "True"
            }
            self.config.hmset("config:pkmn_tourney:leaders:{}".format(leader_id), leader_info)

    def _get_emoji_from_name(self, name):
        if name is None:
            return "\N{QUESTION MARK}"
        else:
            return discord.utils.get(self.emoji_guild.emojis, name=name)

    def _get_mod_emoji(self, member_id):
        """Get emoji directly from mod id"""
        return discord.utils.get(self.emoji_guild.emojis, name=self._badges[member_id])

    def _get_badge_short_name(self, member_id):
        return self._badges[member_id][:-5]

    def get_in_the_gym_message(self, include_timestamp=False):
        output = {
            "offline": [],
            "online": [],
            "in_the_gym": []
        }
        for user_id in self._badges:
            mem = self.pokemon_guild.get_member(user_id)
            if mem.id not in self._retired_members and mem is not None:
                if discord.utils.get(mem.roles, name="In The Gym"):
                    output["in_the_gym"].append("{} {}".format(str(self.green_dot_emoji), mem.display_name))
                elif mem.status not in [discord.Status.offline, discord.Status.invisible]:
                    output["online"].append("🔵 {}".format(mem.display_name))
                else:
                    output["offline"].append("⚫ {}".format(mem.display_name))
        sorted_output = sorted(output["in_the_gym"]) + sorted(output["online"]) + (sorted(output["offline"]))
        embed = discord.Embed(color=discord.Color.blue(), description="\n".join(sorted_output))
        embed.set_author(name="Current active gym leaders", icon_url=self.bot.user.avatar_url)
        if include_timestamp:
            embed.set_footer(text="Last updated {}".format(utils.get_timestamp()))

        return embed

    @commands.group()
    async def league(self, ctx):
        """Type !help league for tourney commands"""
        pass

    @league.command()
    async def badge_info(self, ctx, badge_name: str):
        """Retreives info about a particular badge"""
        for mem_id, badge in self._badges.items():
            short_name = badge[:-5]
            if badge_name == short_name or badge_name == badge:
                desc = "{} Badge{}".format(short_name, "\n*(Retired)*" if mem_id in self._retired_members else "")
                embed = discord.Embed(description=desc)
                mem = self.pokemon_guild.get_member(mem_id)
                embed.set_author(name="{}'s badge.".format(mem.name, short_name),
                                 icon_url=mem.avatar_url)
                embed.set_thumbnail(url=self._get_emoji_from_name(badge).url)
                await ctx.send(embed=embed)
                return
        else:
            await ctx.send("Badge not found.")
            return

    # TODO Create is_leader check
    @checks.is_pokemon_mod()
    @league.command()
    async def set_team(self, ctx, level: str, *, team_info: str):
        """Sets challenge info and difficulty level

        Level: `normal` or `hard`"""
        if level in ["normal", "hard"]:
            self.config.hset("config:pkmn_tourney:leaders:{}:{}".format(ctx.message.author.id, level),
                             "format", team_info)
        else:
            raise commands.UserInputError("Levels are `normal` and `hard`.")

    @checks.is_pokemon_mod()
    @league.command()
    async def set_format(self, ctx, level: str, *, format_info: str):
        if level in ["normal", "hard"]:
            self.config.hset("config:pkmn_tourney:leaders:{}:{}".format(ctx.message.author.id, level),
                             "format", format_info)
            await ctx.send("\N{OK HAND SIGN}")
        else:
            raise commands.UserInputError("Levels are `normal` and `hard`.")

    @league.command(aliases=["profile"])
    async def badge_case(self, ctx, *, member: discord.Member=None):
        """Show a user's profile with corresponding badges based on the mods they've defeated."""

        def get_collection(key):
            return list(self.config.smembers(key)) if self.config.exists(key) else []

        if member is None:
            member = ctx.message.author

        embed = discord.Embed(color=discord.Color.blurple())

        embed.set_author(name="Badge collection for {}".format(member.display_name),
                         icon_url=member.avatar_url)

        badge_collection = get_collection("user:pkmn_tourney:badges:{}".format(member.id))
        ribbon_collection = get_collection("user:pkmn_tourney:ribbons:{}".format(member.id))
        medallion_collection = get_collection("user:pkmn_tourney:medallions:{}".format(member.id))

        # If a badge hasn't been collected, its icon is replaced with a grayed out version.
        # These grayed out badges are shown as `badgenameUnattained`
        for mod_id, badge in self._badges.items():
            if mod_id in self._retired_members:
                continue
            elif badge not in badge_collection:
                badge += "Unattained"
            embed.add_field(name=self.pokemon_guild.get_member(mod_id).name,
                            value=str(self._get_emoji_from_name(badge)))

        for title in sorted(self._ribbons.keys(), reverse=True):
            if self._ribbons[title] in ribbon_collection:
                embed.add_field(name=title, value=str(self._get_emoji_from_name(self._ribbons[title])))

        for name, medal in self._completed_medallions.items():
            if medal not in self.current_medallion['emoji'] and medal in medallion_collection:
                embed.add_field(name=name, value=str(self._get_emoji_from_name(medal)))

        if self.current_medallion['name'] != '':
            if self.config.exists("user:pkmn_tourney:{}:{}".format(self.current_medallion['medal'], member.id)):
                medal_progress = self.config.scard("user:pkmn_tourney:{}:{}".format(
                    self.current_medallion['medal'], member.id))
            else:
                medal_progress = 0
            embed.add_field(name=self.current_medallion['name'],
                            value=str(self._get_emoji_from_name(self._current_medallion[medal_progress])))

        await ctx.send(embed=embed)

    @checks.r_pokemon()
    @league.command()
    async def leader_info(self, ctx, *, member: discord.Member):
        """Get information on a certain gym leader, including their team and format."""
        if member is None or member.id not in self._badges:
            await ctx.send("User is not currently a leader.")
            return
        embed = discord.Embed(color=discord.Color.blue(),
                              description="{} Badge".format(self._get_badge_short_name(member.id).capitalize()))
        embed.set_author(name="Leader information for {}{}".format(
            member.name, " (retired)" if member.id in self._retired_members else ""), icon_url=member.avatar_url)
        embed.set_thumbnail(url=self._get_mod_emoji(member.id).url)
        for difficulty, league_name in [("normal", "Mod League"), ("hard", "Mod League Plus")]:
            if self.config.exists("config:pkmn_tourney:leaders:{}:{}".format(member.id, difficulty)):
                user_info = self.config.hgetall("config:pkmn_tourney:leaders:{}:{}".format(member.id, difficulty))
                try:
                    # If we don't have the format, just omit the field. We can still work if we don't have a team.
                    self.emb_pag.set_headers([league_name])
                    for h, p in self.emb_pag.paginate("{}\n{}".format(user_info["format"], user_info.get("team", ""))):
                        embed.add_field(name=h, value=p)
                    # embed.add_field(name=league_name, value="{}\n{}".format(user_info["format"],
                    #                                                         user_info.get("team", "")))
                except KeyError:
                    pass

        await ctx.send(embed=embed)
        # TODO: implement w/l counter

    @checks.is_pokemon_mod()
    @league.command(hidden=True)
    async def grant_badge(self, ctx, *, member: discord.Member):
        """Grant the mod's own badge to the member."""
        self.config.sadd("user:pkmn_tourney:badges:{}".format(member.id),
                         self._badges[ctx.message.author.id])
        # TODO: Add a list of badge names
        total_badges = self.config.scard("user:pkmn_tourney:badges:{}".format(member.id))
        if total_badges == 8:
            self.config.sadd("user:pkmn_tourney:ribbons:{}".format(member.id), self._ribbons["League Champion"])
            await member.add_roles(self.champion_role)
            champion_msg = self._champion_message["League Champion"].format(
                self._get_emoji_from_name(self._ribbons["League Champion"]))
        elif total_badges == len([i for i in self._badges if i not in self._retired_members]):
            if not self.config.sismember("user:pkmn_tourney:ribbons:{}".format(member.id), "Elite League Champion"):
                champion_msg = self._champion_message["Elite League Champion"].format(
                    self._get_emoji_from_name(self._ribbons["Elite League Champion"]))
            else:
                champion_msg = ""
            self.config.sadd("user:pkmn_tourney:ribbons:{}".format(member.id), self._ribbons["Elite League Champion"])

        else:
            champion_msg = ""
        await ctx.send(victory_message.format(member.mention, ctx.message.author.name,
                                              str(self._get_mod_emoji(ctx.message.author.id)), champion_msg))

    @checks.is_pokemon_mod()
    @league.command(hidden=True)
    async def grant_flawlessvictory(self, ctx, *, member: discord.Member):
        """Grant the Flawless Victory ribbon"""
        if self.config.sismember("user:pkmn_tourney:ribbons:{}".format(member.id), "flawlessRibbon"):
            await ctx.author.send("User {} already has the Flawless Ribbon".format(member.name))
        else:
            self.config.sadd("user:pkmn_tourney:ribbons:{}".format(member.id), "flawlessRibbon")
            await ctx.send(flawless_victory_message.format(member, self._get_emoji_from_name("flawlessRibbon")))

    @checks.is_pokemon_mod()      # TODO: This will be changed for future medal events so that any mod can only grant
    @league.command(hidden=True)  # one piece to one user. Use a hash instead of set to track mod ID as well
    async def grant_fallmedal(self, ctx, *, member: discord.Member):
        """Grants a piece of Harvest Medallion"""
        if self.config.exists("user:pkmn_tourney:{}:{}".format(self.current_medallion['medal'], member.id)):
            medal_progress = self.config.scard("user:pkmn_tourney:{}:{}".format(self.current_medallion['medal'],
                                                                                member.id))
        else:
            medal_progress = 0
        if medal_progress < 3:
            medal_name = self._current_medallion[medal_progress + 1]
            self.config.sadd("user:pkmn_tourney:{}:{}".format(self.current_medallion['medal'], member.id), medal_name)
            if medal_name == self.current_medallion['emoji']:
                self.config.sadd("user:pkmn_tourney:medallions:{}".format(member.id), medal_name)
            await ctx.send(self._medallion_message[medal_progress + 1].format(member.mention,
                                                                              self._get_emoji_from_name(medal_name)))

    @checks.r_pokemon()
    @commands.command()
    async def in_the_gym(self, ctx):
        """View a list of mod league leaders."""
        if ctx.message.channel.id != 198187334968016906:
            await ctx.send("Please use this command in <#198187334968016906>.\nPlease note this command is deprecated.")
            return

        await ctx.send(embed=self.get_in_the_gym_message(),
                       content="**Note that this command is deprecated, please check the channel"
                               "pins in <#325764029538762763> to view an up-to-date list of leaders.**")

    @checks.sudo()
    @commands.command()
    async def update_db_format(self):
        pass

    async def on_timer_update(self, secs):
        if secs % 60 == 0:
            chan = self.bot.get_channel(325764029538762763)
            gym_msg_id = self.config.get("config:pkmn_tourney:gym_message_id")
            if gym_msg_id is None:
                new_msg = await chan.send(embed=self.get_in_the_gym_message(include_timestamp=True))
                await new_msg.pin()
                self.config.set("config:pkmn_tourney:gym_message_id", new_msg.id)
            else:
                msg = await chan.get_message(int(gym_msg_id))
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
