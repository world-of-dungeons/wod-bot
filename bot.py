import locale
import re
import sys
import traceback
import urllib.parse
from datetime import datetime
from pprint import pprint

import discord
from discord.ext import commands, tasks
import requests
import json
from bs4 import BeautifulSoup
import html
from astropy.table import Table, join

from secrets import TOKEN

intents = discord.Intents.all()

help_command = commands.DefaultHelpCommand(no_category='Commands')

bot = commands.Bot(command_prefix='!', intents=intents, help_command=help_command)

re_all = re.compile(
    "\\[item: ?(?P<item>.+?)]|\\[post: ?(?P<post>[0-9]+)]|\\[pcom: ?(?P<pcom>[0-9a-z_]+)]|\\[group: ?(?P<group>.+?)]|\\[clan: ?(?P<clan>.+?)]")

locale.setlocale(locale.LC_TIME, "de_DE.UTF-8")
s = requests.Session()

with open("presences.json") as f:
    bot.presences = json.load(f)
with open("stats.json") as f:
    bot.stats = json.load(f)

bot.worlds = ["Algarion", "Barkladesh", "Cartegon", "Darakesh"]
bot.worlds_short = {
    "wa": "Algarion",
    "wb": "Barkladesh",
    "wc": "Cartegon",
    "wd": "Darakesh",
}

bot.role_message_id = 862294618875101184
bot.emoji_to_role = {
    discord.PartialEmoji(name="AL", id=862294499563929630): 862293144728502274,
    discord.PartialEmoji(name="CA", id=862295452116451328): 862293503002411020,
    discord.PartialEmoji(name="DA", id=862295470226407424): 862293595440676865,
}


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    await bot.change_presence(
        activity=discord.Game(name="World of Dungeons", type=2, url="https://world-of-dungeons.de"))
    print('------')
    save_to_disk.start()
    pprint(bot.presences)
    print('------')
    pprint(bot.stats)
    print('------')


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    if after.raw_status in ("online", "dnd", "idle"):
        bot.presences |= {str(after.id): datetime.now().strftime("%x %X")}


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    current_reaction_count = bot.stats["reaction_count"].get(str(payload.member.id), 0)
    bot.stats["reaction_count"] |= {str(payload.member.id): current_reaction_count + 1}

    if payload.message_id != bot.role_message_id:
        return

    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return

    try:
        role_id = bot.emoji_to_role[payload.emoji]
    except KeyError:
        return

    role = guild.get_role(role_id)
    if role is None:
        return

    await payload.member.add_roles(role)


@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    if payload.message_id != bot.role_message_id:
        return

    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return

    try:
        role_id = bot.emoji_to_role[payload.emoji]
    except KeyError:
        return

    role = guild.get_role(role_id)
    if role is None:
        return

    member = guild.get_member(payload.user_id)
    if member is None:
        return

    await member.remove_roles(role)


@bot.event
async def on_message(message: discord.Message):
    author = message.author
    bot.presences |= {str(author.id): datetime.now().strftime("%x %X")}
    current_message_count = bot.stats["message_count"].get(str(author.id), 0)
    bot.stats["message_count"] |= {str(author.id): current_message_count + 1}
    embed = discord.Embed()
    processed = []
    for matches in re_all.finditer(message.content):
        matches = matches.groupdict()
        for key, value in matches.items():
            if value is None or value in processed:
                continue
            processed.append(value)
            text = ""
            if "post" == key:
                for world in bot.worlds:
                    text += f"[{value}@{world}](https://{world}.world-of-dungeons.de/wod/spiel/forum/viewtopic.php?pid={value}#{value})\n"
                embed.add_field(name="Link zum Post", value=text, inline=False)
            elif "pcom" == key:
                world_id, cat, post_id = value.split("_")
                world = bot.worlds_short.get(world_id, "Algarion")
                embed.add_field(name="Link zum Post",
                                value=f"[{post_id}@{world}](https://{world}.world-of-dungeons.de/wod/spiel/forum/viewtopic.php?pid={post_id}&board={cat}#{post_id})",
                                inline=False)
            elif "item" == key:
                for world in bot.worlds:
                    text += f"[{value}@{world}](https://{world}.world-of-dungeons.de/wod/spiel/hero/item.php?name={urllib.parse.quote_plus(value)}&IS_POPUP=1&is_popup=1)\n"
                embed.add_field(name="Link zum Item", value=text, inline=False)
            elif "clan" == key:
                for world in bot.worlds:
                    text += f"[{value}@{world}](https://{world}.world-of-dungeons.de/wod/spiel/clan/clan.php?name={urllib.parse.quote_plus(value)})\n"
                embed.add_field(name="Link zum Clan", value=text, inline=False)
            elif "group" == key:
                for world in bot.worlds:
                    text += f"[{value}@{world}](https://{world}.world-of-dungeons.de/wod/spiel/dungeon/group.php?name={urllib.parse.quote_plus(value)})\n"
                embed.add_field(name="Link zur Gruppe", value=text, inline=False)
    if len(embed.fields) > 0:
        await message.reply(embed=embed)
    await bot.process_commands(message)


@bot.command()
async def wiki(ctx: commands.Context, *suche: str):
    """Sucht nach einem Begriff in der Enzyklopädie. Zeigt nur die Top 10 Ergebnisse!"""
    params = {
        'action': 'query',
        'list': 'search',
        'srsearch': suche,
        'srprop': 'snippet',
        'utf8': '',
        'format': 'json',
    }
    r = s.get("http://wiki.world-of-dungeons.de/wiki/api.php", params=params)
    print(r.url)
    embed = discord.Embed()
    embed.title = "Hier ist dein Suchergebnis:"
    wiki_result_to_embed(embed, r)
    params.update({'srwhat': 'text'})
    r = s.get("http://wiki.world-of-dungeons.de/wiki/api.php", params=params)
    print(r.url)
    wiki_result_to_embed(embed, r)
    await ctx.send(embed=embed)


@bot.command()
async def joined(ctx: commands.Context, member: discord.Member):
    """Seit wann ist ein Nutzer Mitglied des Servers?"""
    await ctx.send(f'{member.name} joined in {member.joined_at}')


@bot.command()
async def seen(ctx: commands.Context, member: discord.Member):
    """Wann war der Nutzer zuletzt aktiv?"""
    current_status = member.raw_status
    if current_status in ("online", "dnd", "idle"):
        await ctx.send(f'{member.name} ist gerade online!')
    else:
        last_seen = bot.presences.get(str(member.id), "<Unbekannt>")
        await ctx.send(f'{member.name} wurde zuletzt am {last_seen} gesehen!')


@bot.command()
@commands.cooldown(1, 30, commands.BucketType.user)
async def stats(ctx: commands.Context):
    """Nutzungsstatistiken. 30 Sekunden Abklingzeit."""
    data1 = Table(names=("Nutzer", "Nachrichten",), dtype=('str', 'int32'))
    data2 = Table(names=("Nutzer", "Reactions"), dtype=('str', 'int32'))
    for key, value in bot.stats["message_count"].items():
        member = ctx.guild.get_member(int(key))
        if member:
            data1.add_row((member.name, value))
    for key, value in bot.stats["reaction_count"].items():
        member = ctx.guild.get_member(int(key))
        if member:
            data2.add_row((member.name, value))
    data = join(data1, data2, join_type='outer').filled(0)
    await ctx.send(f"```\n{data}\n\nLetzter Reset: {bot.stats['last_wipe']}```")


@stats.error
async def stats_error(ctx: commands.Context, error):
    if isinstance(error, commands.CommandOnCooldown):
        em = discord.Embed(title=f"Langsam mit den jungen Pferden!",
                           description=f"Versuche es erneut in: {error.retry_after:.2f}s.")
        await ctx.send(embed=em)
    else:
        print('Ignoring exception in command {}:'.format(ctx.command), file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)


@bot.command(hidden=True)
async def post(ctx: commands.Context, *message: str):
    if await bot.is_owner(ctx.author):
        await ctx.send(' '.join(message))
        await ctx.message.delete()


@bot.command(hidden=True)
async def wipe_stats(ctx: commands.Context):
    if await bot.is_owner(ctx.author):
        bot.stats = {
            "last_wipe": datetime.now().strftime("%x %X"),
            "message_count": {
                str(bot.user.id): 0
            },
            "reaction_count": {
                str(bot.user.id): 0
            },
        }
        await ctx.message.delete()


@tasks.loop(seconds=60)
async def save_to_disk():
    with open("presences.json", "w") as f:
        json.dump(bot.presences, f)
    with open("stats.json", "w") as f:
        json.dump(bot.stats, f)


def wiki_result_to_embed(embed: discord.Embed, r: requests.Response):
    for result in json.loads(r.text)['query']['search']:
        text = f"""
                   {html.unescape(BeautifulSoup(result['snippet'], 'html.parser').get_text())}
                   Direktlink: [{result['title']}](https://world-of-dungeons.de/ency/{result['title'].replace(' ', '_')})
                   """
        embed.add_field(name=result['title'], value=text, inline=False)


bot.run(TOKEN)
