import html
import json
import locale
import os
import re
import sqlite3
import urllib.parse
from datetime import datetime

import discord
import requests
from astropy.table import Table
from bs4 import BeautifulSoup
from discord.ext import commands

from secrets import TOKEN

intents = discord.Intents.all()

help_command = commands.DefaultHelpCommand(no_category='Commands')

bot = commands.Bot(command_prefix='!', intents=intents, help_command=help_command)

re_all = re.compile(
    "\\[item: ?(?P<item>.+?)]|\\[post: ?(?P<post>[0-9]+)]|\\[pcom: ?(?P<pcom>[0-9a-z_]+)]|\\[group: ?(?P<group>.+?)]|\\[clan: ?(?P<clan>.+?)]")

locale.setlocale(locale.LC_TIME, "de_DE.UTF-8")
s = requests.Session()

if not os.path.exists("database.sqlite"):
    # Prevent optimizing
    import sqlite3_setup
    pass
with sqlite3.connect("database.sqlite") as connection:  # Will not auto close, but makes sure to have consistent state
    pass

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


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    if after.raw_status in ("online", "dnd", "idle"):
        connection.execute(f"""
            INSERT INTO presences (id, time) VALUES ('{str(after.id)}','{datetime.now().strftime('%x %X')}')
            ON CONFLICT(id) DO UPDATE SET time = '{datetime.now().strftime('%x %X')}'
            """)
        connection.commit()


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    connection.execute(f"""
        INSERT INTO stats (guild, id, reactions) VALUES ('{str(payload.guild_id)}','{str(payload.member.id)}',1)
        ON CONFLICT(guild, id) DO UPDATE SET reactions = reactions+1
        """)
    connection.commit()

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
    connection.execute(f"""
        INSERT INTO presences (id, time) VALUES ('{str(author.id)}','{datetime.now().strftime('%x %X')}')
        ON CONFLICT(id) DO UPDATE SET time = '{datetime.now().strftime('%x %X')}'
        """)
    connection.execute(f"""
        INSERT INTO stats (guild, id, messages) VALUES ('{str(message.guild.id)}','{str(author.id)}',1)
        ON CONFLICT(guild, id) DO UPDATE SET messages = messages+1
        """)
    connection.commit()
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
        last_seen = connection.execute(f"SELECT time FROM presences WHERE id = '{str(member.id)}'").fetchone()[0]
        await ctx.send(f'{member.name} wurde zuletzt am {last_seen} gesehen!')


@bot.command()
async def stats(ctx: commands.Context):
    """Nutzungsstatistiken. 30 Sekunden Abklingzeit."""
    data = Table(names=("Nutzer", "Nachrichten", "Reactions"), dtype=('str', 'int32', 'int32'))
    rs = connection.execute(f"""
        SELECT id,messages,reactions FROM stats WHERE guild = '{str(ctx.guild.id)}'
        """).fetchall()
    for key, messages, reactions in rs:
        member = ctx.guild.get_member(int(key))
        if member:
            messages = messages if messages is not None else 0
            reactions = reactions if reactions is not None else 0
            data.add_row((member.name, messages, reactions))
    await ctx.send(f"```\n{data}\n```")


@bot.command(hidden=True)
async def post(ctx: commands.Context, *message: str):
    if await bot.is_owner(ctx.author):
        await ctx.send(' '.join(message))
        await ctx.message.delete()


@bot.command(hidden=True)
async def wipe_stats(ctx: commands.Context):
    if await bot.is_owner(ctx.author):
        connection.execute(f"DELETE FROM stats WHERE guild = '{ctx.guild.id}'")
        connection.commit()
        await ctx.message.delete()


def wiki_result_to_embed(embed: discord.Embed, r: requests.Response):
    for result in json.loads(r.text)['query']['search']:
        text = f"""
           {html.unescape(BeautifulSoup(result['snippet'], 'html.parser').get_text())}
           Direktlink: [{result['title']}](https://world-of-dungeons.de/ency/{result['title'].replace(' ', '_')})
           """
        embed.add_field(name=result['title'], value=text, inline=False)


bot.run(TOKEN)
