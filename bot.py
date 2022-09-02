import html
import json
import locale
import os
import re
import sqlite3
import urllib.parse
from datetime import datetime
from uuid import uuid4

import nextcord
import requests
from astropy import conf as astropy_conf
from astropy.table import Table
from bs4 import BeautifulSoup
from nextcord import Interaction
from nextcord.ext import commands, tasks
from nextcord.ui import View

from secrets import TOKEN

intents = nextcord.Intents.all()

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None,
                   activity=nextcord.Game(name="World of Dungeons", type=2))

re_all = re.compile(
    "\\[skill: ?(?P<skill>.+?)]|\\[item: ?(?P<item>.+?)]|\\[post: ?(?P<post>.+)]|\\[pcom: ?(?P<pcom>[0-9a-z_]+)]|\\[group: ?(?P<group>.+?)]|\\[clan: ?(?P<clan>.+?)]|\\[hero: ?(?P<hero>.+?)]|\\[player: ?(?P<player>.+?)]")

locale.setlocale(locale.LC_TIME, "de_DE.UTF-8")
astropy_conf.max_lines = -1
astropy_conf.max_width = -1
s = requests.Session()

if not os.path.exists("database.sqlite"):
    import sqlite3_setup

    sqlite3_setup.init()
with sqlite3.connect("database.sqlite") as connection:  # Will not auto close, but makes sure to have consistent state
    pass

with open("settings.json", "r") as f:
    bot.settings = json.load(f)


@bot.event
async def on_ready():
    await cleanup_vote()
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


@bot.event
async def on_message(msg: nextcord.Message):
    if msg.guild is None:
        return
    author = msg.author
    connection.execute("INSERT INTO presences (id, time) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET time = ?",
                       (author.id, datetime.now().strftime('%x %X'), datetime.now().strftime('%x %X')))
    connection.execute(
        "INSERT INTO stats (guild, id, messages) VALUES (?,?,1) ON CONFLICT(guild, id) DO UPDATE SET messages = messages+1",
        (msg.guild.id, author.id))
    connection.commit()
    embed = nextcord.Embed()
    processed = []
    for matches in re_all.finditer(msg.content):
        matches = matches.groupdict()
        for key, value in matches.items():
            if value is not None and "|" in value:
                value = value.split("|")[0]
            if value is None or value in processed:
                continue
            processed.append(value)
            text = ""
            if "post" == key:
                for world in bot.settings["worlds"]:
                    text += f"[{value}@{world}](https://{world}.{bot.settings['game_domain']}/wod/spiel/forum/viewtopic.php?pid={value}#{value})\n"
                embed.add_field(name="Link zum Post", value=text, inline=False)
            elif "pcom" == key:
                world_id, cat, post_id = value.split("_")
                world = bot.settings["worlds_short"]
                embed.add_field(name="Link zum Post",
                                value=f"[{post_id}@{world}](https://{world}.{bot.settings['game_domain']}/wod/spiel/forum/viewtopic.php?pid={post_id}&board={cat}#{post_id})",
                                inline=False)
            elif "item" == key:
                if "@" in value:
                    name, world = value.split("@")
                    if world not in bot.settings["worlds"] and world.lower() in bot.settings["worlds_short"]:
                        world = bot.settings["worlds_short"][world.lower()]
                    text += f"[{name}@{world}](https://{world}.{bot.settings['game_domain']}/wod/spiel/hero/item.php?name={urllib.parse.quote_plus(name)}&IS_POPUP=1&is_popup=1)\n"
                else:
                    for world in bot.settings["worlds"]:
                        text += f"[{value}@{world}](https://{world}.{bot.settings['game_domain']}/wod/spiel/hero/item.php?name={urllib.parse.quote_plus(value)}&IS_POPUP=1&is_popup=1)\n"
                embed.add_field(name="Link zum Item", value=text, inline=False)
            elif "clan" == key:
                if "@" in value:
                    name, world = value.split("@")
                    if world not in bot.settings["worlds"] and world.lower() in bot.settings["worlds_short"]:
                        world = bot.settings["worlds_short"][world.lower()]
                    text += f"[{name}@{world}](https://{world}.{bot.settings['game_domain']}/wod/spiel/clan/clan.php?name={urllib.parse.quote_plus(name)})\n"
                else:
                    for world in bot.settings["worlds"]:
                        text += f"[{value}@{world}](https://{world}.{bot.settings['game_domain']}/wod/spiel/clan/clan.php?name={urllib.parse.quote_plus(value)})\n"
                embed.add_field(name="Link zum Clan", value=text, inline=False)
            elif "group" == key:
                if "@" in value:
                    name, world = value.split("@")
                    if world not in bot.settings["worlds"] and world.lower() in bot.settings["worlds_short"]:
                        world = bot.settings["worlds_short"][world.lower()]
                    text += f"[{name}@{world}](https://{world}.{bot.settings['game_domain']}/wod/spiel/dungeon/group.php?name={urllib.parse.quote_plus(name)})\n"
                else:
                    for world in bot.settings["worlds"]:
                        text += f"[{value}@{world}](https://{world}.{bot.settings['game_domain']}/wod/spiel/dungeon/group.php?name={urllib.parse.quote_plus(value)})\n"
                embed.add_field(name="Link zur Gruppe", value=text, inline=False)
            elif "hero" == key:
                if "@" in value:
                    name, world = value.split("@")
                    if world not in bot.settings["worlds"] and world.lower() in bot.settings["worlds_short"]:
                        world = bot.settings["worlds_short"][world.lower()]
                    text += f"[{name}@{world}](https://{world}.{bot.settings['game_domain']}/wod/spiel/hero/profile.php?name={urllib.parse.quote_plus(name)})\n"
                else:
                    for world in bot.settings["worlds"]:
                        text += f"[{value}@{world}](https://{world}.{bot.settings['game_domain']}/wod/spiel/hero/profile.php?name={urllib.parse.quote_plus(value)})\n"
                embed.add_field(name="Link zum Held", value=text, inline=False)
            elif "player" == key:
                if "@" in value:
                    name, world = value.split("@")
                    if world not in bot.settings["worlds"] and world.lower() in bot.settings["worlds_short"]:
                        world = bot.settings["worlds_short"][world.lower()]
                    text += f"[{name}@{world}](https://{world}.{bot.settings['game_domain']}/wod/spiel/profiles/player.php?name={urllib.parse.quote_plus(name)})\n"
                else:
                    for world in bot.settings["worlds"]:
                        text += f"[{value}@{world}](https://{world}.{bot.settings['game_domain']}/wod/spiel/profiles/player.php?name={urllib.parse.quote_plus(value)})\n"
                embed.add_field(name="Link zum Held", value=text, inline=False)
            elif "skill" == key:
                if "@" in value:
                    name, world = value.split("@")
                    if world not in bot.settings["worlds"] and world.lower() in bot.settings["worlds_short"]:
                        world = bot.settings["worlds_short"][world.lower()]
                    text += f"[{name}@{world}](https://{world}.{bot.settings['game_domain']}/wod/spiel/hero/skill.php?name={urllib.parse.quote_plus(name)}&IS_POPUP=1&is_popup=1)\n"
                else:
                    for world in bot.settings["worlds"]:
                        text += f"[{value}@{world}](https://{world}.{bot.settings['game_domain']}/wod/spiel/hero/skill.php?name={urllib.parse.quote_plus(value)}&IS_POPUP=1&is_popup=1)\n"
                embed.add_field(name="Link zum Skill", value=text, inline=False)
    if len(embed.fields) > 0:
        await msg.reply(embed=embed)
    await bot.process_commands(msg)


@bot.slash_command()
async def wiki(ia: Interaction, suche: str):
    """Sucht nach einem Begriff in der Enzyklopädie. Zeigt nur die Top 10 Ergebnisse!"""
    params = {
        'action': 'query',
        'list': 'search',
        'srsearch': suche,
        'srprop': 'snippet',
        'utf8': '',
        'format': 'json',
    }
    r = s.get(f"{bot.settings['wiki_url']}/api.php", params=params)
    print(r.url)
    embed = nextcord.Embed()
    embed.title = "Hier ist dein Suchergebnis:"
    wiki_result_to_embed(embed, r)
    params.update({'srwhat': 'text'})
    r = s.get(f"{bot.settings['wiki_url']}/api.php", params=params)
    print(r.url)
    wiki_result_to_embed(embed, r)
    await ia.send(embed=embed)


@bot.slash_command()
async def joined(ia: Interaction, member: nextcord.Member):
    """Seit wann ist ein Nutzer Mitglied des Servers?"""
    await ia.send(f'{member.name} joined in {member.joined_at}')


@bot.slash_command()
async def seen(ia: Interaction, member: nextcord.Member):
    """Wann war der Nutzer zuletzt aktiv?"""
    current_status = member.raw_status
    if current_status in ("online", "dnd", "idle"):
        await ia.send(f'{member.name} ist gerade online!')
    else:
        last_seen = connection.execute(f"SELECT time FROM presences WHERE id = ?", (member.id,)).fetchone()[0]
        await ia.send(f'{member.name} wurde zuletzt am {last_seen} gesehen!')


@bot.slash_command()
async def stats(ia: Interaction):
    """Globale Nutzungsstatistiken."""
    data = Table(names=("Nutzer", "Nachrichten", "Reactions"), dtype=('str', 'int32', 'int32'))
    rs = connection.execute(
        "SELECT id,messages,reactions FROM stats WHERE guild = ? ORDER BY messages DESC, reactions DESC",
        (ia.guild.id,)).fetchall()
    for key, messages, reactions in rs:
        member = ia.guild.get_member(int(key))
        if member:
            messages = messages if messages is not None else 0
            reactions = reactions if reactions is not None else 0
            data.add_row((member.name, messages, reactions))
    await ia.send(f"```\n{data.__str__()[:1980]}\n```")


@bot.slash_command()
async def vote_start(ia: Interaction, frage: str, optionen: str):
    """
    Starte eine Abstimmung. Optionen müssen mit `+` getrennt werden.
    """
    uuid = str(uuid4())
    dvote = {
        "author": ia.user.id,
        "message": frage,
        "options": [],
        "active": True,
        "voted": [],
        "channel": ia.channel.id
    }
    embed = nextcord.Embed()
    embed.title = f"Abstimmung gestartet von {ia.user}"
    embed.description = frage
    options = optionen.split("+")
    view: View = View(timeout=0)
    for option in options:
        dvote["options"].append({
            "option": option,
            "count": 0
        })
        embed.add_field(name=option, value=0, inline=False)
        view.add_item(PollButton(label=option, uuid=uuid))
    embed.set_footer(text=f"Abstimmung aktiv - Abgegebene Stimmen sind endgültig.")
    await ia.send(embed=embed, view=view)
    sent = await ia.original_message()
    dvote |= {"id": sent.id}
    await ia.user.send(f"```Abstimmung gestartet:\n\nID: {uuid}\nFrage: {frage}```")
    connection.execute("INSERT INTO vote (id, parameters) VALUES (?, ?)", (uuid, json.dumps(dvote)))
    connection.commit()


@bot.slash_command()
async def vote_end(ia: Interaction, id: str):
    """
    Beendet eine Abstimmung.
    """
    rs = connection.execute("SELECT parameters FROM vote WHERE id = ?", (id,)).fetchone()
    if rs:
        dvote = json.loads(rs[0])
        if dvote["active"]:
            if dvote["author"] == ia.user or await bot.is_owner(ia.user):
                vote_message: nextcord.Message = await ia.channel.fetch_message(dvote["id"])
                dvote |= {"active": False, "finished": datetime.now().strftime('%x %X')}
                connection.execute("UPDATE vote SET parameters = ? WHERE id = ?", (json.dumps(dvote), id))
                connection.commit()
                await update_vote_message(vote_message, dvote)
                await vote_message.reply("Abstimmung beendet")
                await ia.send("Done")
                await ia.delete_original_message()


@bot.slash_command()
async def kekse(ia: Interaction):
    """Serviert dem Nutzer Kekse."""
    if ia.user.id == 182156526612512769:
        reset_kekse.cancel()
        await ia.send("Hier sind Ihre Kekse :cookie: und ein heißer Kakao :coffee: werte Keksgöttin :bow:!")
        await bot.change_presence(
            activity=nextcord.Activity(type=nextcord.ActivityType.listening, name="der Keksgöttin"))
        reset_kekse.start()
    else:
        await ia.send("Hier sind deine Kekse :cookie:!")


@tasks.loop(minutes=5, count=1)
async def reset_kekse():
    pass  # Ugly hack to only run once


@reset_kekse.after_loop
async def reset_status():
    await bot.change_presence(activity=nextcord.Game(name="World of Dungeons", type=2))


@bot.slash_command()
async def status(ia: Interaction):
    """
    Zeige den aktuellen Status der WoD Server an.
    """
    base_url = "https://wodstatus.de/api/v1"
    r = s.get(f"{base_url}/components/groups")
    data = r.json()["data"]
    msg = ""
    for group in data:
        components = group["enabled_components"]
        table = Table(names=(group["name"], "Status"), dtype=('str', 'str'))
        for component in components:
            table.add_row((component["name"], component["status_name"]))
        msg += table.__str__() + '\n\n'
    await ia.send(f"```\n{msg}\n```\n\nLivestatus von <https://wodstatus.de>")


# FIXME: Hide from normal users?
@bot.slash_command()
@commands.check_any(commands.is_owner(), commands.has_permissions(administrator=True))
async def wipe_stats(ia: Interaction):
    """
    [ADMIN COMMAND] Löscht Statistiken des Servers aus der Datenbank.
    """
    connection.execute("DELETE FROM stats WHERE guild = ?", (ia.guild.id,))
    connection.commit()
    await ia.send("Done")
    await ia.delete_original_message()


# FIXME: Hide from normal users?
@bot.slash_command()
@commands.check_any(commands.is_owner(), commands.has_permissions(administrator=True))
async def wipe_vote(ia: Interaction):
    """
    [ADMIN COMMAND] Löscht beendete Abstimmungen aus der Datenbank.
    """
    rs = connection.execute("SELECT id, parameters FROM vote").fetchall()
    if rs:
        for result in rs:
            uuid = result[0]
            dvote = json.loads(result[1])
            if not dvote["active"]:
                connection.execute("DELETE FROM vote WHERE id = ?", (uuid,))
                connection.commit()
    await ia.send("Done")
    await ia.delete_original_message()


async def cleanup_vote():
    rs = connection.execute("SELECT id, parameters FROM vote").fetchall()
    if rs:
        for result in rs:
            dvote = json.loads(result[1])
            uuid = result[0]
            if dvote["active"]:
                try:
                    dvote |= {"active": False, "finished": datetime.now().strftime('%x %X')}
                    connection.execute("UPDATE vote SET parameters = ? WHERE id = ?", (json.dumps(dvote), uuid))
                    connection.commit()
                    msg = bot.get_channel(dvote["channel"]).get_partial_message(dvote["id"])
                    embed = nextcord.Embed()
                    embed.title = f"Abstimmung gestartet von {msg.guild.get_member(int(dvote['author']))}"
                    embed.description = dvote["message"]
                    embed.set_footer(text=f"Abstimmung beendet: {dvote['finished']}")
                    await msg.edit(embed=embed, view=None)
                except Exception:
                    pass


async def update_vote_message(msg: nextcord.Message, dvote: dict):
    embed = nextcord.Embed()
    embed.title = f"Abstimmung gestartet von {msg.guild.get_member(int(dvote['author']))}"
    embed.description = dvote["message"]
    for option in dvote["options"]:
        option_value = option["option"]
        count = option["count"]
        embed.add_field(name=option_value, value=count, inline=False)
    if dvote["active"]:
        embed.set_footer(text="Abstimmung aktiv - Abgegebene Stimmen sind endgültig.")
        await msg.edit(embed=embed)
    else:
        embed.set_footer(text=f"Abstimmung beendet: {dvote['finished']}")
        await msg.edit(embed=embed, view=None)


def wiki_result_to_embed(embed: nextcord.Embed, r: requests.Response):
    for result in json.loads(r.text)['query']['search']:
        text = f"""
           {html.unescape(BeautifulSoup(result['snippet'], 'html.parser').get_text())}
           Direktlink: [{result['title']}](https://world-of-dungeons.de/ency/{result['title'].replace(' ', '_')})
           """
        embed.add_field(name=result['title'], value=text, inline=False)


class PollButton(nextcord.ui.Button):
    def __init__(self, label, uuid):
        self.uuid = uuid
        super().__init__(label=label)

    async def callback(self, ia: nextcord.Interaction):
        rs = connection.execute(f"SELECT parameters FROM vote WHERE id = ?", (self.uuid,)).fetchone()
        if rs:
            dvote = json.loads(rs[0])
            if dvote["active"] and ia.user.id not in dvote["voted"]:
                vote_message: nextcord.Message = await bot.get_channel(ia.channel_id).fetch_message(dvote["id"])
                for option in dvote["options"]:
                    if option["option"] == self.label:
                        option["count"] += 1
                dvote["voted"].append(ia.user.id)
                connection.execute("UPDATE vote SET parameters = ? WHERE id = ?",
                                   (json.dumps(dvote), self.uuid))
                connection.commit()
                await update_vote_message(vote_message, dvote)


bot.run(TOKEN)
