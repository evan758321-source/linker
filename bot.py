import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import os
from datetime import datetime

# ── Config ───────────────────────────────────────────────────────────────────
DISCORD_TOKEN    = os.environ["DISCORD_TOKEN"]
REQUIRED_ROLE_ID = 1440883006658187375

# Set API_URL to your Railway service's public URL, e.g.:
#   https://your-project.up.railway.app
API_URL    = os.environ["API_URL"].rstrip("/")
API_SECRET = os.environ["API_SECRET"]

API_HEADERS = {"X-API-Secret": API_SECRET, "Content-Type": "application/json"}

# ── Bot setup ─────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.members = True

class LinkBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print("Slash commands synced.")

bot = LinkBot()

# ── Helpers ───────────────────────────────────────────────────────────────────
def has_required_role(interaction: discord.Interaction) -> bool:
    if interaction.guild is None:
        return False
    return any(r.id == REQUIRED_ROLE_ID for r in interaction.user.roles)

def role_error_embed() -> discord.Embed:
    return discord.Embed(
        title="❌ Missing Role",
        description="You need the required role to use this bot.",
        color=discord.Color.red(),
    )

def normalise_hwid(raw: str) -> str | None:
    clean = raw.replace("-", "").upper().strip()
    return clean if len(clean) == 12 else None

def fmt_hwid(hwid: str) -> str:
    return f"{hwid[:4]}-{hwid[4:8]}-{hwid[8:]}"

async def api_post(session: aiohttp.ClientSession, path: str, body: dict):
    async with session.post(f"{API_URL}{path}", json=body, headers=API_HEADERS) as r:
        return r.status, await r.json(content_type=None)

async def api_get(session: aiohttp.ClientSession, path: str):
    async with session.get(f"{API_URL}{path}", headers=API_HEADERS) as r:
        return r.status, await r.json(content_type=None)

# ── /link-device ──────────────────────────────────────────────────────────────
@bot.tree.command(name="link-device", description="Link your device code to your Discord account.")
@app_commands.describe(hwid="Your 12-character device code (e.g. ABCD-EFGH-JKLM)")
async def link_device(interaction: discord.Interaction, hwid: str):
    await interaction.response.defer(ephemeral=True)

    if not has_required_role(interaction):
        await interaction.followup.send(embed=role_error_embed(), ephemeral=True)
        return

    clean = normalise_hwid(hwid)
    if not clean:
        await interaction.followup.send(embed=discord.Embed(
            title="❌ Invalid Code",
            description="Must be exactly 12 characters — e.g. `ABCD-EFGH-JKLM`.",
            color=discord.Color.orange(),
        ), ephemeral=True)
        return

    discord_id = str(interaction.user.id)

    async with aiohttp.ClientSession() as session:
        try:
            status, data = await api_post(session, "/link", {
                "discord_id": discord_id,
                "hwid": clean,
            })
        except Exception as ex:
            await interaction.followup.send(embed=discord.Embed(
                title="⚠️ Connection Error", description=str(ex), color=discord.Color.red(),
            ), ephemeral=True)
            return

    if status == 200:
        e = discord.Embed(
            title="✅ Device Linked!",
            description=f"Linked `{fmt_hwid(clean)}` to your account.\nMod menu unlocks within 30 seconds.",
            color=discord.Color.green(),
            timestamp=datetime.utcnow(),
        )
        e.set_footer(text=f"Discord ID: {discord_id}")
    elif status == 409:
        error = data.get("error", "")
        if error == "already_linked":
            existing = fmt_hwid(data.get("hwid", "????????????"))
            e = discord.Embed(
                title="⚠️ Already Linked",
                description=f"Your account is already linked to `{existing}`.\nUse `/change-device` to switch devices.",
                color=discord.Color.orange(),
            )
        else:
            e = discord.Embed(
                title="❌ HWID Taken",
                description="This device code is already linked to another account.",
                color=discord.Color.red(),
            )
    else:
        e = discord.Embed(
            title="⚠️ Error", description=str(data), color=discord.Color.red(),
        )

    await interaction.followup.send(embed=e, ephemeral=True)

# ── /change-device ────────────────────────────────────────────────────────────
@bot.tree.command(name="change-device", description="Unlink your old device and link a new one.")
@app_commands.describe(new_hwid="Your new 12-character device code (e.g. ABCD-EFGH-JKLM)")
async def change_device(interaction: discord.Interaction, new_hwid: str):
    await interaction.response.defer(ephemeral=True)

    if not has_required_role(interaction):
        await interaction.followup.send(embed=role_error_embed(), ephemeral=True)
        return

    clean = normalise_hwid(new_hwid)
    if not clean:
        await interaction.followup.send(embed=discord.Embed(
            title="❌ Invalid Code",
            description="Must be exactly 12 characters — e.g. `ABCD-EFGH-JKLM`.",
            color=discord.Color.orange(),
        ), ephemeral=True)
        return

    discord_id = str(interaction.user.id)

    async with aiohttp.ClientSession() as session:
        try:
            status, data = await api_post(session, "/change", {
                "discord_id": discord_id,
                "new_hwid": clean,
            })
        except Exception as ex:
            await interaction.followup.send(embed=discord.Embed(
                title="⚠️ Connection Error", description=str(ex), color=discord.Color.red(),
            ), ephemeral=True)
            return

    if status == 200:
        old = data.get("old_hwid", "")
        old_fmt = fmt_hwid(old) if old else "none"
        e = discord.Embed(
            title="🔄 Device Changed!",
            color=discord.Color.blurple(),
            timestamp=datetime.utcnow(),
        )
        e.add_field(name="Old Device", value=f"`{old_fmt}`", inline=True)
        e.add_field(name="New Device", value=f"`{fmt_hwid(clean)}`", inline=True)
        e.set_footer(text=f"Discord ID: {discord_id}")
    elif status == 409:
        e = discord.Embed(
            title="❌ HWID Taken",
            description="That device code is already linked to another account.",
            color=discord.Color.red(),
        )
    else:
        e = discord.Embed(
            title="⚠️ Error", description=str(data), color=discord.Color.red(),
        )

    await interaction.followup.send(embed=e, ephemeral=True)

# ── /check-link ───────────────────────────────────────────────────────────────
@bot.tree.command(name="check-link", description="Check the link status for your account (or another user).")
@app_commands.describe(user="The user to check (leave empty for yourself)")
async def check_link(interaction: discord.Interaction, user: discord.Member = None):
    await interaction.response.defer(ephemeral=True)

    if not has_required_role(interaction):
        await interaction.followup.send(embed=role_error_embed(), ephemeral=True)
        return

    target     = user or interaction.user
    discord_id = str(target.id)

    async with aiohttp.ClientSession() as session:
        try:
            status, data = await api_get(session, f"/status/{discord_id}")
        except Exception as ex:
            await interaction.followup.send(embed=discord.Embed(
                title="⚠️ Connection Error", description=str(ex), color=discord.Color.red(),
            ), ephemeral=True)
            return

    if status == 200 and data.get("linked"):
        e = discord.Embed(
            title="🔗 Device Linked",
            description=f"{target.mention} → `{fmt_hwid(data['hwid'])}`",
            color=discord.Color.green(),
        )
    else:
        e = discord.Embed(
            title="🔓 Not Linked",
            description=f"{target.mention} has no device linked.",
            color=discord.Color.light_grey(),
        )
    await interaction.followup.send(embed=e, ephemeral=True)

# ── /unlink (admin) ───────────────────────────────────────────────────────────
@bot.tree.command(name="unlink", description="[Admin] Force-unlink a user's device.")
@app_commands.describe(user="The user to unlink")
@app_commands.default_permissions(administrator=True)
async def unlink(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.defer(ephemeral=True)

    async with aiohttp.ClientSession() as session:
        try:
            status, data = await api_post(session, "/unlink", {
                "discord_id": str(user.id),
            })
        except Exception as ex:
            await interaction.followup.send(embed=discord.Embed(
                title="⚠️ Connection Error", description=str(ex), color=discord.Color.red(),
            ), ephemeral=True)
            return

    if status == 200 and data.get("ok"):
        hwid = data.get("removed_hwid", "")
        e = discord.Embed(
            title="🗑️ Unlinked",
            description=f"{user.mention} unlinked from `{fmt_hwid(hwid)}`.",
            color=discord.Color.red(),
        )
    else:
        e = discord.Embed(
            title="ℹ️ Not Linked",
            description=f"{user.mention} had no device linked.",
            color=discord.Color.light_grey(),
        )
    await interaction.followup.send(embed=e, ephemeral=True)

# ── Ready ─────────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, name="device links"
    ))

def start():
    bot.run(DISCORD_TOKEN)

if __name__ == "__main__":
    start()
