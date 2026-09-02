import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import asyncio
import os
import json

# ==============================================================================
# Discord Music Bot - Headless / Server Version (No GUI)
# ใช้สำหรับ deploy บนเซิร์ฟเวอร์ เช่น Wispbyte
# Token อ่านจาก .env / environment variable / config.json
# ==============================================================================

# การตั้งค่าสำหรับ yt-dlp
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -probesize 200M',
    'options': '-vn -b:a 192k -bufsize 10M'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

ytdl_flat_options = {
    'extract_flat': True,
    'playlist_items': '1-50',
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}
ytdl_flat = youtube_dl.YoutubeDL(ytdl_flat_options)

# ตัวแปรระบบคิวเพลง
music_queues = {}
current_song = {}
disconnect_timers = {}

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix=commands.when_mentioned_or("!"),
    description='บอทเปิดเพลงง่ายๆ',
    intents=intents,
)

# ----------------- ระบบตัดการเชื่อมต่ออัตโนมัติ ----------------- #
def start_disconnect_timer(ctx, guild_id):
    if guild_id in disconnect_timers:
        disconnect_timers[guild_id].cancel()

    async def timer():
        print(f"[Timer] ⏳ เริ่มจับเวลา 5 นาทีสำหรับห้อง {guild_id}...")
        try:
            await asyncio.sleep(300)
            if current_song.get(guild_id) is None and ctx.voice_client and ctx.voice_client.is_connected():
                print(f"[Disconnect] 🔌 ออกจากห้อง {guild_id} เนื่องจากไม่ได้ใช้งานเกิน 5 นาที")
                await ctx.voice_client.disconnect()
                get_queue(guild_id).clear()
                bot.loop.create_task(ctx.send("👋 ออกจากห้องเสียงอัตโนมัติ เนื่องจากไม่มีการใช้งานเกิน 5 นาที"))
        except asyncio.CancelledError:
            pass

    disconnect_timers[guild_id] = bot.loop.create_task(timer())

def cancel_disconnect_timer(guild_id):
    if guild_id in disconnect_timers:
        disconnect_timers[guild_id].cancel()
        del disconnect_timers[guild_id]
        print(f"[Timer] ❌ ยกเลิกจับเวลาสำหรับห้อง {guild_id}")

def get_queue(guild_id):
    if guild_id not in music_queues:
        music_queues[guild_id] = []
    return music_queues[guild_id]

def play_next(ctx):
    queue_list = get_queue(ctx.guild.id)
    if len(queue_list) > 0:
        cancel_disconnect_timer(ctx.guild.id)
        song = queue_list.pop(0)
        current_song[ctx.guild.id] = song
        print(f"[Queue] ⏩ ดึงเพลงถัดไปจากคิว: {song['title']} (เหลือในคิว: {len(queue_list)})")
        bot.loop.create_task(prepare_and_play(ctx, song))
    else:
        current_song[ctx.guild.id] = None
        print(f"[Queue] 📭 คิวเพลงว่างเปล่าในห้อง {ctx.guild.id}")
        start_disconnect_timer(ctx, ctx.guild.id)

async def prepare_and_play(ctx, song):
    try:
        loop = bot.loop
        print(f"[Audio] ⏳ กำลังโหลด Stream URL ของเพลง: {song['title']}")
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(song['url'], download=False))

        if 'entries' in data:
            data = data['entries'][0]

        stream_url = data['url']
        print(f"[Audio] ✅ โหลดสำเร็จ! เริ่มจำลองเสียงไปที่ Discord")

        audio_source = discord.FFmpegPCMAudio(stream_url, **ffmpeg_options)
        ctx.voice_client.play(discord.PCMVolumeTransformer(audio_source, volume=0.5), after=lambda e: play_next(ctx))

        print(f"[Play] ▶️ กำลังเล่น: {song['title']}")
        await ctx.send(f'🎶 กำลังเล่น: **{song["title"]}**')
    except Exception as e:
        print(f"[Error] ❌ โหลดเสียงล้มเหลว: {e}")
        await ctx.send(f"❌ เกิดข้อผิดพลาดในการดึงเสียงของเพลง **{song['title']}**: {str(e)}")
        play_next(ctx)

def get_audio_info(query):
    search_query = query if query.startswith('http') else f"ytsearch1:{query}"
    data = ytdl_flat.extract_info(search_query, download=False)

    entries = []
    if 'entries' in data:
        for entry in data['entries']:
            if entry:
                url = entry.get('url') or entry.get('webpage_url')
                if not url and entry.get('id'):
                    url = f"https://www.youtube.com/watch?v={entry.get('id')}"
                if url:
                    entries.append({'url': url, 'title': entry.get('title', 'Unknown Title')})
    else:
        url = data.get('webpage_url') or data.get('url')
        if not url and data.get('id'):
            url = f"https://www.youtube.com/watch?v={data.get('id')}"
        if url:
            entries.append({'url': url, 'title': data.get('title', 'Unknown Title')})

    return entries

# ----------------- คำสั่งบอท ----------------- #

@bot.event
async def on_ready():
    print('=================================')
    print(f'✅ บอทออนไลน์แล้ว! ชื่อ: {bot.user}')
    print(f'🆔 ID: {bot.user.id}')
    print('=================================')
    print('พร้อมรับคำสั่ง !play, !stop, !skip, !queue')

@bot.event
async def on_voice_state_update(member, before, after):
    if member.id == bot.user.id and before.channel and not after.channel:
        guild_id = member.guild.id
        print(f"[Voice] 🔌 บอทถูกตัดการเชื่อมต่อจากห้อง {guild_id}")
        if guild_id in music_queues:
            music_queues[guild_id].clear()
        current_song[guild_id] = None
        cancel_disconnect_timer(guild_id)

@bot.command(name='play', help='เล่นเพลง (YouTube, SoundCloud, Twitch)')
async def play(ctx, *, query):
    if not ctx.author.voice:
        return await ctx.send("❌ คุณต้องอยู่ในห้องเสียงก่อนนะ!")

    channel = ctx.author.voice.channel
    permissions = channel.permissions_for(ctx.me)
    if not permissions.connect or not permissions.speak:
        return await ctx.send("❌ บอทไม่มีสิทธิ์ Connect/Speak ในห้องนี้")

    if not ctx.voice_client:
        await channel.connect()
    elif ctx.voice_client.channel != channel:
        await ctx.voice_client.move_to(channel)

    async with ctx.typing():
        try:
            loop = asyncio.get_event_loop()
            songs = await loop.run_in_executor(None, get_audio_info, query)

            if not songs:
                await ctx.send("❌ ไม่พบข้อมูลเพลงจากคำค้นหาหรือลิงก์นี้")
                return

            if len(songs) > 50:
                songs = songs[:50]
                await ctx.send("📢 **เพิ่มเพลย์ลิสต์ลงคิวแล้ว!** (ดึงมาสูงสุด 50 เพลงน้า 🎵)")

            queue_list = get_queue(ctx.guild.id)
            queue_list.extend(songs)

            is_active = ctx.voice_client.is_playing() or ctx.voice_client.is_paused() or current_song.get(ctx.guild.id) is not None

            if not is_active:
                play_next(ctx)
                if len(songs) == 1:
                    await ctx.send(f'⏳ กำลังเตรียมเล่น: **{songs[0]["title"]}**')
                else:
                    await ctx.send(f'⏳ เพิ่ม **{len(songs)}** เพลงลงคิว และกำลังเตรียมเล่นเพลงแรก...')
            else:
                if len(songs) == 1:
                    await ctx.send(f'✅ เพิ่มลงในคิว: **{songs[0]["title"]}**')
                else:
                    await ctx.send(f'✅ เพิ่ม **{len(songs)}** เพลงจากเพลย์ลิสต์ลงในคิวแล้ว!')

        except Exception as e:
            print(f"[Error] ❌ เกิดข้อผิดพลาดในคำสั่ง play: {e}")
            await ctx.send(f"❌ เกิดข้อผิดพลาดในการโหลดข้อมูล: {str(e)}")

@bot.command(name='stop', help='หยุดเพลงและออกจากห้อง')
async def stop(ctx):
    if ctx.voice_client:
        get_queue(ctx.guild.id).clear()
        current_song[ctx.guild.id] = None
        cancel_disconnect_timer(ctx.guild.id)
        await ctx.voice_client.disconnect()
        await ctx.send("👋 หยุดเพลงและออกจากห้องแล้วนะ")
    else:
        await ctx.send("❌ บอทยังไม่ได้อยู่ในห้องเสียงเลย")

@bot.command(name='skip', help='ข้ามเพลง')
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭️ ข้ามเพลงแล้ว!")
    else:
        await ctx.send("❌ ตอนนี้ไม่ได้เล่นเพลงอะไรอยู่นะ")

@bot.command(name='queue', help='ดูรายชื่อเพลงในคิว')
async def queue(ctx):
    queue_list = get_queue(ctx.guild.id)
    current = current_song.get(ctx.guild.id)

    if not queue_list and not current:
        return await ctx.send("📭 คิวเพลงว่างเปล่า")

    msg = ""
    if current:
        msg += f"🔊 **กำลังเล่น:** {current['title']}\n\n"

    if not queue_list:
        msg += "📭 ไม่มีเพลงในคิวถัดไป"
    else:
        show_limit = 10
        q_list = "\n".join([f"{i+1}. {song['title']}" for i, song in enumerate(queue_list[:show_limit])])
        msg += f"📜 **Queue:**\n{q_list}"
        if len(queue_list) > show_limit:
            msg += f"\n\n*(...and {len(queue_list) - show_limit} more)*"

    await ctx.send(msg)

# ----------------- โหลด Token ----------------- #
def load_dotenv_manual():
    """อ่านไฟล์ .env แล้วโหลดเข้า os.environ เอง"""
    # ลองหา .env จากหลายที่
    possible_paths = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
        os.path.join(os.getcwd(), ".env"),
        "/home/container/.env",
    ]
    for env_path in possible_paths:
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if key:
                            os.environ[key] = value
                print(f"[Config] ✅ โหลด .env จาก {env_path}")
                return
            except Exception as e:
                print(f"[Config] ⚠️ อ่าน .env ล้มเหลว: {e}")

def load_token():
    # โหลด .env ก่อนเสมอ
    load_dotenv_manual()

    # อ่านจาก environment variable
    token = os.environ.get("DISCORD_TOKEN")
    if token:
        print("[Config] ✅ โหลด Token สำเร็จ")
        return token

    # fallback: อ่านจาก config.json
    for config_path in ["config.json", "/home/container/config.json"]:
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    token = data.get("token")
                    if token:
                        print(f"[Config] ✅ โหลด Token จาก {config_path}")
                        return token
            except Exception as e:
                print(f"[Config] ❌ อ่าน {config_path} ล้มเหลว: {e}")

    print("[Config] ❌ ไม่พบ Token!")
    print("[Config] วิธีแก้: ตั้งค่า DISCORD_TOKEN ใน Variables บน Wispbyte")
    return None

if __name__ == "__main__":
    token = load_token()
    if token:
        bot.run(token)
    else:
        exit(1)
