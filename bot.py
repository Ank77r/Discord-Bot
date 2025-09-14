import asyncio
import discord
from discord.ext import commands
from discord.ui import Button, View
import os
import json
import random
import string
from dotenv import load_dotenv
from itertools import combinations
from datetime import datetime, timezone
import math

# 🔐 This is YOUR Discord user ID
OWNER_ID = 1284068409029558308  # Replace this number with your actual ID

# Load token
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# --- PATH SETUP ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
FIXTURE_DIR = os.path.join(PROJECT_ROOT, "fixtures")
RECORD_DIR = os.path.join(PROJECT_ROOT, "records")
TOURNAMENT_DIR = os.path.join(BASE_DIR, "tournaments")

os.makedirs(FIXTURE_DIR, exist_ok=True)
os.makedirs(RECORD_DIR, exist_ok=True)
os.makedirs(TOURNAMENT_DIR, exist_ok=True)

FIXTURE_FILE = os.path.join(FIXTURE_DIR, "fixtures.json")
RECORD_FILE = os.path.join(RECORD_DIR, "records.json")
TOURNAMENT_FILE = os.path.join(TOURNAMENT_DIR, "tournaments.json")

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

# --- UTILITIES ---
def load_fixtures():
    if not os.path.exists(FIXTURE_FILE): return {}
    with open(FIXTURE_FILE, 'r') as f: return json.load(f)
def save_fixtures(data):
    with open(FIXTURE_FILE, 'w') as f: json.dump(data, f, indent=2)
def load_records():
    if not os.path.exists(RECORD_FILE): return {}
    with open(RECORD_FILE, 'r') as f: return json.load(f)
def save_records(data):
    with open(RECORD_FILE, 'w') as f: json.dump(data, f, indent=2)
def load_tournaments():
    if not os.path.exists(TOURNAMENT_FILE): return {"active_count": 0, "completed_count": 0}
    try:
        with open(TOURNAMENT_FILE, 'r') as f: return json.load(f)
    except json.JSONDecodeError: return {"active_count": 0, "completed_count": 0}
def save_tournaments(data):
    with open(TOURNAMENT_FILE, 'w') as f: json.dump(data, f, indent=2)
def update_tournament_counts():
    fixtures = load_fixtures()
    active_count = 0; completed_count = 0
    for data in fixtures.values():
        if data.get("status") == "completed": completed_count += 1
        else: active_count += 1
    save_tournaments({"active_count": active_count, "completed_count": completed_count})
def generate_code():
    return "fixture-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

# --- INTERACTIVE FIXTURE CREATION VIEW (WITH ENHANCED VISUALS) ---
class TournamentTypeView(View):
    def __init__(self, ctx, game_name, teams):
        super().__init__(timeout=180.0)
        self.ctx = ctx
        self.game_name = game_name
        self.teams = teams
        self.fixture_code = generate_code()
        self.message = None

    async def on_timeout(self):
        if self.message:
            for item in self.children:
                item.disabled = True
            await self.message.edit(content="Fixture creation timed out.", view=self)

    async def disable_all_buttons(self, interaction: discord.Interaction):
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

    @discord.ui.button(label="League (Round Robin)", style=discord.ButtonStyle.primary, emoji="🏆")
    async def league_button(self, interaction: discord.Interaction, button: Button):
        await self.disable_all_buttons(interaction)
        await interaction.response.send_message("How many times should each team play every other team? (e.g., 1, 2)", ephemeral=True)
        try:
            def check(m):
                return m.author == self.ctx.author and m.channel == self.ctx.channel and m.content.isdigit()

            msg = await bot.wait_for('message', check=check, timeout=60.0)
            rounds = int(msg.content)
            if rounds <= 0:
                await self.ctx.send("❌ Number must be positive. Aborting."); return

            matchups = list(combinations(self.teams, 2))
            full_match_list = matchups * rounds
            random.shuffle(full_match_list)

            fixtures = load_fixtures()
            fixtures[self.fixture_code] = {
                "game_name": self.game_name, "tournament_type": "league",
                "teams": list(self.teams), "matches": [list(match) for match in full_match_list],
                "date": datetime.now(timezone.utc).isoformat(), "status": "active"
            }
            save_fixtures(fixtures); update_tournament_counts()
            
            matches_text = "\n".join([f"• {a} vs {b}" for a, b in full_match_list[:20]])
            if len(full_match_list) > 20: matches_text += "\n• ..."

            # --- NEW EMBED VISUAL ---
            embed = discord.Embed(
                title="🏆 League Fixture Created!",
                description=f"A new round-robin tournament has been set up.",
                color=discord.Color.blue()
            )
            embed.add_field(name="Game", value=self.game_name, inline=True)
            embed.add_field(name="Fixture Code", value=f"`{self.fixture_code}`", inline=True)
            embed.add_field(name="Teams", value=", ".join(self.teams), inline=False)
            embed.add_field(name="Format", value=f"Each team plays every other team **{rounds}** time(s).", inline=False)
            embed.add_field(name="🎲 Randomized Matches (First 20)", value=matches_text, inline=False)
            embed.set_footer(text=f"Fixture created by {self.ctx.author.name}")

            await self.ctx.send(embed=embed)

        except asyncio.TimeoutError:
            await self.ctx.send("⌛ Timed out waiting for response. Fixture creation cancelled.")

    @discord.ui.button(label="Knockout", style=discord.ButtonStyle.secondary, emoji="⚔️")
    async def knockout_button(self, interaction: discord.Interaction, button: Button):
        await self.disable_all_buttons(interaction)
        
        shuffled_teams = list(self.teams)
        random.shuffle(shuffled_teams)
        
        num_teams = len(shuffled_teams)
        next_power_of_2 = 2**math.ceil(math.log2(num_teams))
        byes = next_power_of_2 - num_teams
        
        teams_with_byes = shuffled_teams[:byes]
        teams_in_round1 = shuffled_teams[byes:]
        round1_matches = [teams_in_round1[i:i + 2] for i in range(0, len(teams_in_round1), 2)]

        fixtures = load_fixtures()
        fixtures[self.fixture_code] = {
            "game_name": self.game_name, "tournament_type": "knockout",
            "teams": list(self.teams), "byes_to_round2": teams_with_byes,
            "bracket": {"Round 1": {"matches": round1_matches, "winners": []}},
            "date": datetime.now(timezone.utc).isoformat(), "status": "active"
        }
        save_fixtures(fixtures); update_tournament_counts()

        matches_text = "\n".join([f"• {a} vs {b}" for a,b in round1_matches]) if round1_matches else "No matches in this round."
        byes_text = "\n".join([f"• {bye}" for bye in teams_with_byes]) if teams_with_byes else "None"
        
        # --- NEW EMBED VISUAL ---
        embed = discord.Embed(
            title="⚔️ Knockout Fixture Created!",
            description=f"A new single-elimination tournament has been set up.",
            color=discord.Color.gold()
        )
        embed.add_field(name="Game", value=self.game_name, inline=True)
        embed.add_field(name="Fixture Code", value=f"`{self.fixture_code}`", inline=True)
        embed.add_field(name="Teams", value=", ".join(self.teams), inline=False)
        embed.add_field(name="Round 1 Matches", value=matches_text, inline=False)
        embed.add_field(name="Byes to Round 2", value=byes_text, inline=False)
        embed.set_footer(text=f"Fixture created by {self.ctx.author.name}")

        await self.ctx.send(embed=embed)

# ----------------- Bot Ready -----------------
@bot.event
async def on_ready():
    print(f" Bot is online as {bot.user}")
    update_tournament_counts()
    print(" Tournament counts synced.")

# --- /fixture (NOW INTERACTIVE) ---
@bot.command(name="fixture")
async def create_fixture(ctx, game_name: str, *teams: str):
    if len(teams) < 2:
        await ctx.send("❌ You need at least 2 teams. If your game name has spaces, enclose it in quotes."); return
    
    unique_teams = list(set(teams))
    if len(unique_teams) < 2:
        await ctx.send("❌ You need at least 2 unique teams."); return

    view = TournamentTypeView(ctx, game_name, unique_teams)
    message = await ctx.send(f"Creating a **{game_name}** fixture for **{len(unique_teams)} teams**. Please select a format:", view=view)
    view.message = message # Pass message to view for timeout editing

# --- /record (NOW HANDLES LEAGUE & KNOCKOUT) ---
@bot.command(name="record")
async def record_result(ctx, fixture_code: str, team1: str, result1: str, team2: str, result2: str):
    fixtures = load_fixtures()
    records = load_records()

    if fixture_code not in fixtures:
        await ctx.send("❌ Fixture not found."); return
    
    fixture_data = fixtures[fixture_code]

    if fixture_data.get("status") == "completed":
        await ctx.send(f"⚠️ This fixture (`{fixture_code}`) is already complete."); return

    tourney_type = fixture_data.get("tournament_type", "league")

    if tourney_type == "league":
        teams = fixture_data["teams"]
        if team1 not in teams or team2 not in teams:
            await ctx.send("❌ One or both teams are not in this fixture."); return

        result1 = result1.upper(); result2 = result2.upper()
        if result1 not in ['W', 'L', 'T'] or result2 not in ['W', 'L', 'T']:
            await ctx.send("❌ Use only W (win), L (loss), or T (tie) for result."); return

        if fixture_code not in records: records[fixture_code] = {}
        for team in teams:
            if team not in records[fixture_code]:
                records[fixture_code][team] = {"played": 0, "wins": 0, "losses": 0, "draws": 0, "points": 0}

        records[fixture_code][team1]["played"] += 1
        records[fixture_code][team2]["played"] += 1

        if result1 == 'W' and result2 == 'L':
            records[fixture_code][team1]["wins"] += 1; records[fixture_code][team1]["points"] += 3
            records[fixture_code][team2]["losses"] += 1
        elif result1 == 'L' and result2 == 'W':
            records[fixture_code][team2]["wins"] += 1; records[fixture_code][team2]["points"] += 3
            records[fixture_code][team1]["losses"] += 1
        elif result1 == 'T' and result2 == 'T':
            records[fixture_code][team1]["draws"] += 1; records[fixture_code][team2]["draws"] += 1
            records[fixture_code][team1]["points"] += 1; records[fixture_code][team2]["points"] += 1
        else:
            await ctx.send("❌ Invalid result combination."); return
        
        is_complete = False
        if len(fixture_data.get("matches", [])) > 0:
            total_matches_in_fixture = len(fixture_data["matches"])
            total_played_stat = sum(team_data["played"] for team_data in records[fixture_code].values())
            matches_played_count = total_played_stat // 2
            if matches_played_count >= total_matches_in_fixture:
                fixtures[fixture_code]["status"] = "completed"; is_complete = True

        save_fixtures(fixtures); save_records(records); update_tournament_counts()
        await ctx.send(f"✅ Match recorded for `{fixture_code}`.")
        if is_complete:
            await ctx.send(f"🏆 **Fixture `{fixture_code}` is now complete!** 🏆")
        return

    elif tourney_type == "knockout":
        result1 = result1.upper(); result2 = result2.upper()
        if (result1, result2) not in [('W', 'L'), ('L', 'W')]:
            await ctx.send("❌ Knockout matches must have a winner (W) and a loser (L). Ties are not allowed."); return
        
        winner = team1 if result1 == 'W' else team2
        # NOTE: This only acknowledges the winner. Auto-generating the next round is the next feature to build.
        await ctx.send(f"✅ Knockout match recorded in `{fixture_code}`. **{winner}** advances!")
        return

# --- /table (NOW SHOWS LEADERBOARD OR BRACKET) ---
@bot.command(name="table")
async def show_leaderboard(ctx, fixture_name: str):
    fixtures = load_fixtures()
    records = load_records()

    if fixture_name not in fixtures:
        await ctx.send(f"❌ Fixture `{fixture_name}` not found."); return
    
    fixture_data = fixtures[fixture_name]
    tourney_type = fixture_data.get("tournament_type", "league")

    if tourney_type == "league":
        teams = fixture_data["teams"]
        stats = {}
        for team in teams:
            team_record = records.get(fixture_name, {}).get(team, {})
            stats[team] = {"played": team_record.get("played", 0), "wins": team_record.get("wins", 0),
                           "losses": team_record.get("losses", 0), "draws": team_record.get("draws", 0),
                           "points": team_record.get("points", 0)}

        sorted_teams = sorted(stats.items(), key=lambda x: (-x[1]["points"], x[0]))
        status = fixture_data.get("status", "active").upper()
        status_emoji = "✅" if status == "COMPLETED" else "▶️"
        
        game_info = f" for **{fixture_data.get('game_name', '')}**" if fixture_data.get('game_name') else ""
        table = f"🏆 **Leaderboard{game_info}** (`{fixture_name}`) [{status_emoji} {status}] 🏆\n"
        table += "```\n"
        table += f"{'Rank':<5}{'Team':<12}{'P':<4}{'W':<4}{'L':<4}{'D':<4}{'Pts':<5}\n"
        table += "-" * 40 + "\n"
        for i, (team, data) in enumerate(sorted_teams, 1):
            table += f"{i:<5}{team:<12}{data['played']:<4}{data['wins']:<4}{data['losses']:<4}{data['draws']:<4}{data['points']:<5}\n"
        table += "```"
        await ctx.send(table)
    
    elif tourney_type == "knockout":
        game_name = fixture_data.get('game_name', 'Knockout')
        embed = discord.Embed(
            title=f"⚔️ {game_name} Bracket",
            description=f"Fixture Code: `{fixture_name}`",
            color=discord.Color.dark_gold()
        )
        
        round1_matches = fixture_data.get("bracket", {}).get("Round 1", {}).get("matches", [])
        byes = fixture_data.get("byes_to_round2", [])

        round1_text = "\n".join([f"• {p1} vs {p2}" for p1, p2 in round1_matches]) if round1_matches else "Round 1 not yet generated."
        byes_text = "\n".join([f"• {bye}" for bye in byes]) if byes else "None"

        embed.add_field(name="Round 1 Matches", value=round1_text, inline=False)
        embed.add_field(name="Byes to Round 2", value=byes_text, inline=False)
        await ctx.send(embed=embed)

# --- UNCHANGED COMMANDS ---
@bot.command(name="summary")
async def tournament_summary(ctx):
    counts = load_tournaments()
    active = counts.get("active_count", 0); completed = counts.get("completed_count", 0)
    embed = discord.Embed(title="📊 Tournament Summary", description="A quick overview of all tournament activity.", color=discord.Color.blue())
    embed.add_field(name="Active Tournaments", value=f"▶️ {active}", inline=True)
    embed.add_field(name="Completed Tournaments", value=f"✅ {completed}", inline=True)
    embed.set_footer(text=f"Requested by {ctx.author.name}")
    await ctx.send(embed=embed)
@bot.command(name="delete")
async def delete_fixture(ctx, code: str):
    fixtures = load_fixtures(); records = load_records()
    if code not in fixtures: await ctx.send("❌ Fixture not found."); return
    warning = f"⚠️ This will permanently delete the fixture `{code}` and all its records.\n\nType `Y` to confirm or `N` to cancel."
    await ctx.send(warning)
    def check(msg): return msg.author == ctx.author and msg.channel == ctx.channel and msg.content.upper() in ['Y', 'N']
    try:
        response = await bot.wait_for("message", check=check, timeout=30.0)
        if response.content.upper() == "Y":
            del fixtures[code]
            if code in records: del records[code]
            save_fixtures(fixtures); save_records(records); update_tournament_counts()
            await ctx.send(f"✅ Fixture `{code}` and its records have been deleted.")
        else: await ctx.send("❎ Deletion cancelled.")
    except asyncio.TimeoutError: await ctx.send("⌛ Timeout. No action taken.")
@bot.command(name='delete-all')
async def delete_all(ctx):
    if ctx.author.id != OWNER_ID: await ctx.send("❌ You are not authorized to use this command."); return
    await ctx.send("⚠️ This will delete **ALL** fixtures and records permanently. Type `Y` to confirm or `N` to cancel.")
    def check(m): return m.author == ctx.author and m.channel == ctx.channel and m.content.upper() in ['Y', 'N']
    try:
        msg = await bot.wait_for('message', check=check, timeout=30)
        if msg.content.upper() == 'Y':
            save_fixtures({}); save_records({}); update_tournament_counts()
            await ctx.send("🧹 All fixture and record data has been successfully deleted.")
        else: await ctx.send("❎ Delete operation cancelled.")
    except asyncio.TimeoutError: await ctx.send("⌛ Confirmation timed out. Operation cancelled.")

# --- /bothelp (FORMAT UNCHANGED) ---
@bot.command(name='bothelp')
async def bot_help(ctx):
    help_message = """
╭────────────────────────────────────────────╮
│           📘 FIXTURE BOT COMMANDS           │
╰────────────────────────────────────────────╯

╭────────────┬────────────────────────────────────────────────────────────╮
│ Command    │ Description                                                │
├────────────┼────────────────────────────────────────────────────────────┤
│ /fixture   │ 🎲 Starts an interactive process to create a new tournament. │
│            │ ➤ Example: /fixture "Chess Championship" PlayerA PlayerB   │
│            │ ➤ Note: Game Name must be in quotes if it has spaces.      │
├────────────┼────────────────────────────────────────────────────────────┤
│ /table     │ 📊 Shows a leaderboard for Leagues or a bracket for Knockouts│
│            │ ➤ Example: /table fixture-XYZ123                           │
├────────────┼────────────────────────────────────────────────────────────┤
│ /record    │ 🏆 Records a match result. Use T for ties in Leagues only. │
│            │ ➤ Example: /record fixture-XYZ123 Alpha W Beta L           │
├────────────┼────────────────────────────────────────────────────────────┤
│ /summary   │ 📈 Show counts of active and completed tournaments         │
│            │ ➤ Example: /summary                                        │
├────────────┼────────────────────────────────────────────────────────────┤
│ /delete    │ 🗑️ Delete a fixture and its records                       │
│            │ ➤ Example: /delete fixture-XYZ123                          │
├────────────┼────────────────────────────────────────────────────────────┤
│ /bothelp   │ 📖 Show this help panel                                    │
╰────────────┴────────────────────────────────────────────────────────────╯
"""
    await ctx.send(f"```{help_message}```")

# ----------------- Run Bot -----------------
bot.run(TOKEN)