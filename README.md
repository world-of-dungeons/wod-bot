# WoD Discord Bot

## Zukunft

Die Zukunft dieses Bots steht aktuell in den Sternen. Die Weiterentwicklung von `discord.py` wurde eingestellt und ob und wann ich die Zeit habe den Code an die neuen Vorraussetzungen von Discord anzupassen ist unklar. Die aktuelle Version sollte bis April 2022 funktionieren.

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
