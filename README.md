# WoD Discord Bot

## Voraussetzungen

- Python 3.9 oder neuer
- SQLite 2.24 oder neuer
- Gültiges Application-Secret von https://discord.com/developers/

## Installation

- `git clone https://github.com/world-of-dungeons/wod-bot`
- `cd wod-bot`
- `python3.9 -m pip install -r requirements.txt`
  
## Betrieb

- Erstelle eine `secrets.py` Datei mit einem gültigen Application-Secret (`TOKEN = "abc123"`)
- `nohup python3.9 -u bot.py &`
