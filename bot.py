import html
import json
import locale
import os
import re
import sqlite3
import urllib.parse
from datetime import datetime

import nextcord
import requests
from astropy.table import Table
from bs4 import BeautifulSoup
from nextcord import Interaction
from nextcord.ext import commands, tasks

from secrets import TOKEN

intents = nextcord.Intents.all()

help_command = commands.DefaultHelpCommand(no_category='Commands')

bot = commands.Bot(command_prefix='!', intents=intents, help_command=help_command,
                   activity=nextcord.Game(name="World of Dungeons", type=2))

re_all = re.compile(
    "\\[item: ?(?P<item>.+?)]|\\[post: ?(?P<post>.+)]|\\[pcom: ?(?P<pcom>[0-9a-z_]+)]|\\[group: ?(?P<group>.+?)]|\\[clan: ?(?P<clan>.+?)]|\\[hero: ?(?P<hero>.+?)]|\\[player: ?(?P<player>.+?)]")

locale.setlocale(locale.LC_TIME, "de_DE.UTF-8")
s = requests.Session()

if not os.path.exists("database.sqlite"):
    import sqlite3_setup

    sqlite3_setup.init()
with sqlite3.connect("database.sqlite") as connection:  # Will not auto close, but makes sure to have consistent state
    pass

bot.worlds = ["Algarion", "Barkladesh", "Cartegon", "Darakesh"]
bot.worlds_short = {
    "wa": "Algarion",
    "wb": "Barkladesh",
    "wc": "Cartegon",
    "wd": "Darakesh",
}


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')


@bot.event
async def on_member_update(_, after: nextcord.Member):
    if after.raw_status in ("online", "dnd", "idle"):
        connection.execute("INSERT INTO presences (id, time) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET time = ?",
                           (after.id, datetime.now().strftime('%x %X'), datetime.now().strftime('%x %X')))
        connection.commit()


@bot.event
async def on_raw_reaction_add(payload: nextcord.RawReactionActionEvent):
    connection.execute(
        "INSERT INTO stats (guild, id, reactions) VALUES (?,?,1) ON CONFLICT(guild, id) DO UPDATE SET reactions = reactions+1",
        (payload.guild_id, payload.member.id))
    connection.commit()

    rs = connection.execute(f"SELECT parameters FROM vote WHERE id = ?", (payload.message_id,)).fetchone()
    if rs:
        symbol_base = 127462
        symbol = payload.emoji.name
        option_number = ord(symbol) - symbol_base
        dvote = json.loads(rs[0])
        if dvote["active"]:
            vote_message: nextcord.Message = await bot.get_channel(payload.channel_id).fetch_message(dvote["id"])
            for option in dvote["options"]:
                if option["number"] == option_number:
                    option["count"] += 1
            connection.execute("UPDATE vote SET parameters = ? WHERE id = ?", (json.dumps(dvote), payload.message_id))
            connection.commit()
            await update_vote_message(vote_message, dvote)


@bot.event
async def on_raw_reaction_remove(payload: nextcord.RawReactionActionEvent):
    rs = connection.execute("SELECT parameters FROM vote WHERE id = ?", (payload.message_id,)).fetchone()
    if rs:
        symbol_base = 127462
        symbol = payload.emoji.name
        option_number = ord(symbol) - symbol_base
        dvote = json.loads(rs[0])
        if dvote["active"]:
            vote_message: nextcord.Message = await bot.get_channel(payload.channel_id).fetch_message(dvote["id"])
            for option in dvote["options"]:
                if option["number"] == option_number:
                    option["count"] -= 1
            connection.execute("UPDATE vote SET parameters = ? WHERE id = ?", (json.dumps(dvote), payload.message_id))
            connection.commit()
            await update_vote_message(vote_message, dvote)


@bot.event
async def on_message(message: nextcord.Message):
    if message.guild is None:
        return
    author = message.author
    connection.execute("INSERT INTO presences (id, time) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET time = ?",
                       (author.id, datetime.now().strftime('%x %X'), datetime.now().strftime('%x %X')))
    connection.execute(
        "INSERT INTO stats (guild, id, messages) VALUES (?,?,1) ON CONFLICT(guild, id) DO UPDATE SET messages = messages+1",
        (message.guild.id, author.id))
    connection.commit()
    embed = nextcord.Embed()
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
                if "@" in value:
                    name, world = value.split("@")
                    if world not in bot.worlds and world.lower() in bot.worlds_short:
                        world = bot.worlds_short[world.lower()]
                    text += f"[{name}@{world}](https://{world}.world-of-dungeons.de/wod/spiel/hero/item.php?name={urllib.parse.quote_plus(name)}&IS_POPUP=1&is_popup=1)\n"
                else:
                    for world in bot.worlds:
                        text += f"[{value}@{world}](https://{world}.world-of-dungeons.de/wod/spiel/hero/item.php?name={urllib.parse.quote_plus(value)}&IS_POPUP=1&is_popup=1)\n"
                embed.add_field(name="Link zum Item", value=text, inline=False)
            elif "clan" == key:
                if "@" in value:
                    name, world = value.split("@")
                    if world not in bot.worlds and world.lower() in bot.worlds_short:
                        world = bot.worlds_short[world.lower()]
                    text += f"[{name}@{world}](https://{world}.world-of-dungeons.de/wod/spiel/clan/clan.php?name={urllib.parse.quote_plus(name)})\n"
                else:
                    for world in bot.worlds:
                        text += f"[{value}@{world}](https://{world}.world-of-dungeons.de/wod/spiel/clan/clan.php?name={urllib.parse.quote_plus(value)})\n"
                embed.add_field(name="Link zum Clan", value=text, inline=False)
            elif "group" == key:
                if "@" in value:
                    name, world = value.split("@")
                    if world not in bot.worlds and world.lower() in bot.worlds_short:
                        world = bot.worlds_short[world.lower()]
                    text += f"[{name}@{world}](https://{world}.world-of-dungeons.de/wod/spiel/dungeon/group.php?name={urllib.parse.quote_plus(name)})\n"
                else:
                    for world in bot.worlds:
                        text += f"[{value}@{world}](https://{world}.world-of-dungeons.de/wod/spiel/dungeon/group.php?name={urllib.parse.quote_plus(value)})\n"
                embed.add_field(name="Link zur Gruppe", value=text, inline=False)
            elif "hero" == key:
                if "@" in value:
                    name, world = value.split("@")
                    if world not in bot.worlds and world.lower() in bot.worlds_short:
                        world = bot.worlds_short[world.lower()]
                    text += f"[{name}@{world}](https://{world}.world-of-dungeons.de/wod/spiel/hero/profile.php?name={urllib.parse.quote_plus(name)})\n"
                else:
                    for world in bot.worlds:
                        text += f"[{value}@{world}](https://{world}.world-of-dungeons.de/wod/spiel/hero/profile.php?name={urllib.parse.quote_plus(value)})\n"
                embed.add_field(name="Link zum Held", value=text, inline=False)
            elif "player" == key:
                if "@" in value:
                    name, world = value.split("@")
                    if world not in bot.worlds and world.lower() in bot.worlds_short:
                        world = bot.worlds_short[world.lower()]
                    text += f"[{name}@{world}](https://{world}.world-of-dungeons.de/wod/spiel/profiles/player.php?name={urllib.parse.quote_plus(name)})\n"
                else:
                    for world in bot.worlds:
                        text += f"[{value}@{world}](https://{world}.world-of-dungeons.de/wod/spiel/profiles/player.php?name={urllib.parse.quote_plus(value)})\n"
                embed.add_field(name="Link zum Held", value=text, inline=False)
    if len(embed.fields) > 0:
        await message.reply(embed=embed)
    await bot.process_commands(message)


@bot.slash_command(description="Sucht nach einem Begriff in der Enzyklopädie. Zeigt nur die Top 10 Ergebnisse!")
async def wiki(interaction: Interaction, suche: str):
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
    embed = nextcord.Embed()
    embed.title = "Hier ist dein Suchergebnis:"
    wiki_result_to_embed(embed, r)
    params.update({'srwhat': 'text'})
    r = s.get("http://wiki.world-of-dungeons.de/wiki/api.php", params=params)
    print(r.url)
    wiki_result_to_embed(embed, r)
    await interaction.send(embed=embed)


@bot.slash_command(description="Seit wann ist ein Nutzer Mitglied des Servers?")
async def joined(interaction: Interaction, member: nextcord.Member):
    """Seit wann ist ein Nutzer Mitglied des Servers?"""
    await interaction.send(f'{member.name} joined in {member.joined_at}')


@bot.slash_command(description="Wann war der Nutzer zuletzt aktiv?")
async def seen(interaction: Interaction, member: nextcord.Member):
    """Wann war der Nutzer zuletzt aktiv?"""
    current_status = member.raw_status
    if current_status in ("online", "dnd", "idle"):
        await interaction.send(f'{member.name} ist gerade online!')
    else:
        last_seen = connection.execute(f"SELECT time FROM presences WHERE id = ?", (member.id,)).fetchone()[0]
        await interaction.send(f'{member.name} wurde zuletzt am {last_seen} gesehen!')


@bot.slash_command(description="Globale Nutzungsstatistiken.")
async def stats(interaction: Interaction):
    """Globale Nutzungsstatistiken."""
    data = Table(names=("Nutzer", "Nachrichten", "Reactions"), dtype=('str', 'int32', 'int32'))
    rs = connection.execute("SELECT id,messages,reactions FROM stats WHERE guild = ?", (ctx.guild.id,)).fetchall()
    for key, messages, reactions in rs:
        member = interaction.guild.get_member(int(key))
        if member:
            messages = messages if messages is not None else 0
            reactions = reactions if reactions is not None else 0
            data.add_row((member.name, messages, reactions))
    await interaction.send(f"```\n{data}\n```")


# FIXME: Does not work like this anymore, refactor with clean Buttons/Dropdown
@bot.slash_command(description="Starte eine Abstimmung.")
async def vote_start(interaction: Interaction, message: str, options: str):
    """
    Starte eine Abstimmung.

    Beispiel:
                !vote Abstimmung A B
                !vote "Texte mit Leerzeichen müssen in Quotes" "Gilt auch für Optionen" B C
    """
    dvote = {
        "author": interaction.user.id,
        "message": message,
        "options": [],
        "active": True
    }
    embed = nextcord.Embed()
    embed.title = f"Abstimmung gestartet von {interaction.user}"
    embed.description = message
    txt: str = ""
    options_count = len(options)
    for i in range(options_count):
        option = options[i]
        dvote["options"].append({
            "number": i,
            "option": option,
            "count": 0
        })
        embed.add_field(name=f":regional_indicator_{chr(97 + i)}: 0", value=option, inline=False)
        txt += f":regional_indicator_{chr(97 + i)}:"
        if i + 2 > options_count:
            pass
        elif i + 3 > options_count:
            txt += " oder "
        else:
            txt += ", "
    embed.add_field(name="Nutze Reactions zum Abstimmen:", value=txt, inline=False)
    embed.set_footer(text=f"Abstimmung aktiv")
    sent: nextcord.Message = await interaction.send(embed=embed)
    dvote |= {"id": sent.id}
    await interaction.delete_original_message()
    await interaction.user.send(f"```Abstimmung gestartet:\n\nID: {sent.id}\nFrage: {message}```")
    connection.execute("INSERT INTO vote (id, parameters) VALUES (?, ?)", (sent.id, json.dumps(dvote)))
    connection.commit()


# FIXME: See vote_start
@bot.slash_command(description="Beendet eine Abstimmung.")
async def vote_end(interaction: Interaction, id: str):
    """
    Beendet eine Abstimmung.
    """
    rs = connection.execute("SELECT parameters FROM vote WHERE id = ?", (id,)).fetchone()
    if rs:
        dvote = json.loads(rs[0])
        if dvote["active"]:
            if dvote["author"] == interaction.user or await bot.is_owner(interaction.user):
                vote_message: nextcord.Message = await interaction.channel.fetch_message(dvote["id"])
                dvote |= {"active": False, "finished": datetime.now().strftime('%x %X')}
                connection.execute("UPDATE vote SET parameters = ? WHERE id = ?", (json.dumps(dvote), dvote["id"]))
                connection.commit()
                await update_vote_message(vote_message, dvote)
                await vote_message.reply("Abstimmung beendet")
    await interaction.message.delete()


@bot.slash_command(description="Serviert dem Nutzer Kekse.")
async def kekse(interaction: Interaction):
    """Serviert dem Nutzer Kekse."""
    if interaction.user.id == 182156526612512769:
        reset_kekse.cancel()
        await interaction.send("Hier sind Ihre Kekse :cookie: und ein heißer Kakao :coffee: werte Keksgöttin :bow:!")
        await bot.change_presence(activity=nextcord.Activity(type=nextcord.ActivityType.listening, name="der Keksgöttin"))
        reset_kekse.start()
    else:
        await interaction.send("Hier sind deine Kekse :cookie:!")


@tasks.loop(minutes=5, count=1)
async def reset_kekse():
    pass  # Ugly hack to only run once


@reset_kekse.after_loop
async def reset_status():
    print("Status changed")
    await bot.change_presence(activity=nextcord.Game(name="World of Dungeons", type=2))


# FIXME: Hide from normal users?
@bot.slash_command(default_permission=False)
async def post(interaction: Interaction, message: str):
    if await bot.is_owner(interaction.user):
        await interaction.send(message)


# FIXME: Hide from normal users?
@bot.slash_command(default_permission=False)
async def wipe_stats(interaction: Interaction):
    if await bot.is_owner(interaction.user):
        connection.execute("DELETE FROM stats WHERE guild = ?", (interaction.guild.id,))
        connection.commit()
        await interaction.delete_original_message()


# FIXME: Hide from normal users?
@bot.slash_command(default_permission=False)
async def wipe_vote(interaction: Interaction):
    if await bot.is_owner(interaction.user):
        rs = connection.execute("SELECT parameters FROM vote").fetchall()
        if rs:
            for result in rs:
                dvote = json.loads(result[0])
                if not dvote["active"]:
                    connection.execute("DELETE FROM vote WHERE id = ?", (dvote["id"],))
                    connection.commit()
        await interaction.delete_original_message()


async def update_vote_message(message: nextcord.Message, dvote: dict):
    embed = nextcord.Embed()
    embed.title = f"Abstimmung gestartet von {message.guild.get_member(int(dvote['author']))}"
    embed.description = dvote["message"]
    txt: str = ""
    options_count = len(dvote["options"])
    for option in dvote["options"]:
        i = option["number"]
        option_value = option["option"]
        count = option["count"]
        embed.add_field(name=f":regional_indicator_{chr(97 + i)}: {count}", value=option_value, inline=False)
        txt += f":regional_indicator_{chr(97 + i)}:"
        if i + 2 > options_count:
            pass
        elif i + 3 > options_count:
            txt += " oder "
        else:
            txt += ", "
    embed.add_field(name="Nutze Reactions zum Abstimmen:", value=txt, inline=False)
    if dvote["active"]:
        embed.set_footer(text="Abstimmung aktiv")
    else:
        embed.set_footer(text=f"Abstimmung beendet: {dvote['finished']}")
    await message.edit(embed=embed)


def wiki_result_to_embed(embed: nextcord.Embed, r: requests.Response):
    for result in json.loads(r.text)['query']['search']:
        text = f"""
           {html.unescape(BeautifulSoup(result['snippet'], 'html.parser').get_text())}
           Direktlink: [{result['title']}](https://world-of-dungeons.de/ency/{result['title'].replace(' ', '_')})
           """
        embed.add_field(name=result['title'], value=text, inline=False)


bot.run(TOKEN)
