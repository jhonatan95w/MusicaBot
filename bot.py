import discord
from discord.ext import commands, tasks
import yt_dlp
import asyncio
import random
from collections import deque
import re
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import os
import sys
import json
import time
from dotenv import load_dotenv

# WebSocket para comunicação com dashboard
try:
    import websockets
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False
    print("⚠️ websockets não instalado - usando fallback JSON")

# Banco de dados para histórico e favoritos
try:
    from database import db
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False
    db = None
    print("⚠️ database.py não encontrado - histórico desabilitado")

# Configurar encoding UTF-8 para o console do Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Carregar variáveis de ambiente do diretório do script
script_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(script_dir, '.env')
load_dotenv(env_path)

# Mudar para o diretório do script (importante para ffmpeg)
os.chdir(script_dir)

# Configurações
TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    raise ValueError("DISCORD_TOKEN não encontrado no arquivo .env")

# Configurar Spotify
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')

if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
    print('Spotify API configurada com credenciais')
    sp = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET
    ))
else:
    print('⚠️ Spotify sem credenciais - apenas tracks públicas funcionarão')
    print('Para usar playlists, configure SPOTIFY_CLIENT_ID e SPOTIFY_CLIENT_SECRET no arquivo .env')
    sp = spotipy.Spotify()

# Configurações do yt-dlp
ytdl_format_options = {
    'format': 'bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best',
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch1',
    'source_address': '0.0.0.0',
    'geo_bypass': True,
    'prefer_insecure': True,
    'extractor_args': {'youtube': {'player_client': ['android', 'web'], 'skip': ['hls', 'dash']}},
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.original_url = data.get('webpage_url', data.get('url'))
        self.duration = data.get('duration', 0)
        self.thumbnail = data.get('thumbnail')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True, volume=0.5):
        loop = loop or asyncio.get_event_loop()

        partial_data = await loop.run_in_executor(
            None,
            lambda: ytdl.extract_info(url, download=False)
        )

        if partial_data is None:
            raise Exception("Não foi possível obter informações da música")

        if 'entries' in partial_data:
            if len(partial_data['entries']) == 0:
                raise Exception("Nenhum resultado encontrado")
            partial_data = partial_data['entries'][0]

        return cls(discord.FFmpegPCMAudio(partial_data['url'], **ffmpeg_options), data=partial_data, volume=volume)

# Sistema de filas por servidor
music_queues = {}
shuffle_mode = {}
history = {}

# Arquivos de comunicação com o dashboard
STATUS_FILE = os.path.join(script_dir, ".bot_status.json")
COMMAND_FILE = os.path.join(script_dir, ".bot_command.json")

# Guild ativa para comandos do dashboard
active_guild_id = None
active_voice_client = None
last_voice_channel_id = None  # Armazena o último canal de voz para reconexão via dashboard
last_text_channel_id = None  # Armazena o último canal de texto para mensagens via dashboard

# Informações da música atual para o dashboard
current_song_start_time = None  # Timestamp de quando a música começou
current_song_duration = 0  # Duração em segundos
current_song_thumbnail = None  # URL da thumbnail
current_volume = 0.5  # Volume atual (0.0 a 1.0)
songs_played_count = 0  # Contador de músicas tocadas

# WebSocket
WEBSOCKET_PORT = 8765
WEBSOCKET_HOST = "0.0.0.0"  # Aceita conexões de qualquer IP
websocket_clients = {}  # {client_id: {"websocket": ws, "connected_at": timestamp, "name": str, "is_host": bool}}
next_client_id = 1

def get_host_client_id():
    """Retorna o ID do cliente host (mais antigo conectado)"""
    if not websocket_clients:
        return None
    # Encontrar o cliente mais antigo
    oldest_id = min(websocket_clients.keys(), key=lambda cid: websocket_clients[cid]["connected_at"])
    return oldest_id

def is_host(client_id):
    """Verifica se o cliente é o host"""
    return client_id == get_host_client_id()

def get_users_list():
    """Retorna lista de usuários conectados"""
    users = []
    host_id = get_host_client_id()
    for cid, data in websocket_clients.items():
        users.append({
            "id": cid,
            "name": data.get("name", f"Usuário {cid}"),
            "is_host": cid == host_id,
            "connected_at": data["connected_at"]
        })
    # Ordenar por tempo de conexão
    users.sort(key=lambda u: u["connected_at"])
    return users

async def broadcast_status(status_data):
    """Envia status para todos os clientes WebSocket conectados"""
    if websocket_clients:
        # Adicionar informações de usuários ao status
        status_data["users"] = get_users_list()
        status_data["total_users"] = len(websocket_clients)
        message = json.dumps(status_data)
        await asyncio.gather(
            *[client["websocket"].send(message) for client in websocket_clients.values()],
            return_exceptions=True
        )

async def broadcast_users_update():
    """Envia atualização da lista de usuários para todos"""
    users_data = {
        "type": "users_update",
        "users": get_users_list(),
        "total_users": len(websocket_clients)
    }
    message = json.dumps(users_data)
    await asyncio.gather(
        *[client["websocket"].send(message) for client in websocket_clients.values()],
        return_exceptions=True
    )

def update_dashboard_status(guild_id=None):
    """Atualiza o arquivo de status para o dashboard"""
    import time
    try:
        status = {
            "current_song": None,
            "current_song_url": None,
            "is_paused": False,
            "queue": [],
            "duration": 0,
            "start_time": None,
            "thumbnail": None,
            "volume": current_volume,
            "voice_channel": None,
            "songs_played": songs_played_count,
            "guilds": [],
            "active_guild_id": None
        }

        # Lista de servidores disponíveis
        for guild in bot.guilds:
            guild_info = {
                "id": guild.id,
                "name": guild.name,
                "has_voice": guild.voice_client is not None,
                "voice_channel": guild.voice_client.channel.name if guild.voice_client and guild.voice_client.channel else None
            }
            status["guilds"].append(guild_info)

        gid = guild_id or active_guild_id
        status["active_guild_id"] = gid

        if gid and gid in music_queues:
            queue = music_queues[gid]
            current = queue.get_current()
            if current:
                status["current_song"] = current.get("title", "Música desconhecida")
                status["current_song_url"] = current.get("url")
                status["thumbnail"] = current.get("thumbnail")
                status["duration"] = current.get("duration", 0)

            queue_list = queue.get_queue()
            status["queue"] = [s.get("title", "?") for s in queue_list[:10]]

            # Verificar se está pausado e obter canal de voz
            for guild in bot.guilds:
                if guild.id == gid and guild.voice_client:
                    status["is_paused"] = guild.voice_client.is_paused()
                    status["voice_channel"] = guild.voice_client.channel.name if guild.voice_client.channel else None
                    break

        # Adicionar timestamp de início
        if current_song_start_time:
            status["start_time"] = current_song_start_time

        # Salvar em arquivo (fallback)
        with open(STATUS_FILE, 'w', encoding='utf-8') as f:
            json.dump(status, f, ensure_ascii=False)

        # Enviar via WebSocket
        if WEBSOCKET_AVAILABLE and websocket_clients:
            asyncio.create_task(broadcast_status(status))
    except Exception as e:
        print(f"Erro ao atualizar status: {e}")

class MusicQueue:
    def __init__(self):
        self.all_songs = deque()  # Lista completa de músicas
        self.current_index = -1  # Índice da música atual
        self.loop = None
        self.control_message = None
        self.manual_control = False  # Flag para navegação manual

    def add(self, song_data):
        self.all_songs.append(song_data)

    def next(self):
        if not self.all_songs:
            return None

        # Se ainda não tocou nenhuma ou está na última, vai para primeira
        if self.current_index >= len(self.all_songs) - 1:
            self.current_index = 0
        else:
            # Avança para próxima
            self.current_index += 1

        return self.all_songs[self.current_index] if self.current_index < len(self.all_songs) else None

    def previous(self):
        if not self.all_songs:
            return None

        # Se está na primeira ou antes, fica na primeira
        if self.current_index <= 0:
            self.current_index = 0
            return self.all_songs[0]

        self.current_index -= 1
        return self.all_songs[self.current_index]

    def get_current(self):
        if 0 <= self.current_index < len(self.all_songs):
            return self.all_songs[self.current_index]
        return None

    def get_history(self):
        # Retorna todas as músicas antes da atual
        if self.current_index <= 0:
            return []
        return list(self.all_songs)[:self.current_index]

    def get_queue(self):
        # Retorna todas as músicas depois da atual
        if self.current_index < 0 or self.current_index >= len(self.all_songs) - 1:
            return []
        return list(self.all_songs)[self.current_index + 1:]

    def clear(self):
        self.all_songs.clear()
        self.current_index = -1

    def get_list(self):
        return self.get_queue()

# Configurar intents
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

# Criar bot
bot = commands.Bot(command_prefix='!', intents=intents)

def get_queue(guild_id):
    if guild_id not in music_queues:
        music_queues[guild_id] = MusicQueue()
    return music_queues[guild_id]

def extract_spotify_track(url):
    """Extrai informações de uma track do Spotify"""
    try:
        track_id = url.split('track/')[-1].split('?')[0]
        print(f'Extraindo track ID: {track_id}')
        track = sp.track(track_id)
        artist = track['artists'][0]['name']
        title = track['name']
        search_query = f"{artist} - {title}"
        print(f'Query de busca: {search_query}')
        return search_query
    except Exception as e:
        print(f'Erro ao extrair track do Spotify: {e}')
        import traceback
        traceback.print_exc()
    return None

def extract_spotify_playlist(url):
    """Extrai todas as músicas de uma playlist do Spotify"""
    try:
        playlist_id = url.split('playlist/')[-1].split('?')[0]
        print(f'Extraindo playlist ID: {playlist_id}')

        playlist = sp.playlist(playlist_id)
        tracks = []

        for item in playlist['tracks']['items']:
            if item['track']:
                track = item['track']
                artist = track['artists'][0]['name']
                title = track['name']
                search_query = f"{artist} - {title}"
                tracks.append(search_query)

        print(f'Playlist extraída: {len(tracks)} músicas')
        return tracks
    except Exception as e:
        print(f'Erro ao extrair playlist do Spotify: {e}')
        import traceback
        traceback.print_exc()
    return None

def extract_spotify_album(url):
    """Extrai todas as músicas de um álbum do Spotify"""
    try:
        album_id = url.split('album/')[-1].split('?')[0]
        print(f'Extraindo album ID: {album_id}')

        album = sp.album(album_id)
        tracks = []

        for track in album['tracks']['items']:
            artist = track['artists'][0]['name']
            title = track['name']
            search_query = f"{artist} - {title}"
            tracks.append(search_query)

        print(f'Álbum extraído: {len(tracks)} músicas')
        return tracks
    except Exception as e:
        print(f'Erro ao extrair álbum do Spotify: {e}')
        import traceback
        traceback.print_exc()
    return None

def is_spotify_url(url):
    """Verifica se a URL é do Spotify"""
    spotify_patterns = [
        r'open\.spotify\.com/track/',
        r'open\.spotify\.com/playlist/',
        r'open\.spotify\.com/album/'
    ]
    return any(re.search(pattern, url) for pattern in spotify_patterns)

async def play_next(guild, voice_client):
    global active_guild_id, current_song_start_time, songs_played_count
    import time
    queue = get_queue(guild.id)
    active_guild_id = guild.id

    # Se está em controle manual, ignora o play_next automático
    if queue.manual_control:
        queue.manual_control = False
        return

    # Deletar mensagem anterior com botões
    if queue.control_message:
        try:
            await queue.control_message.delete()
        except Exception as e:
            print(f'Erro ao deletar mensagem: {e}')

    next_song = queue.next()

    if next_song:
        try:
            current_song_start_time = time.time()
            songs_played_count += 1
            player = await YTDLSource.from_url(next_song['url'], loop=bot.loop, stream=True, volume=current_volume)
            voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(guild, voice_client), bot.loop))

            # Salvar no histórico
            if DATABASE_AVAILABLE and db:
                db.add_to_history(
                    title=next_song.get('title', 'Desconhecido'),
                    url=next_song.get('url'),
                    thumbnail=next_song.get('thumbnail'),
                    duration=next_song.get('duration', 0),
                    guild_id=guild.id,
                    guild_name=guild.name
                )

            # Atualizar dashboard
            update_dashboard_status(guild.id)

            if queue.loop:
                # Criar nova mensagem com botões
                queue_list = queue.get_queue()

                # Criar descrição longa para formato retangular
                description_parts = [
                    f"**🎵 Tocando Agora**\n{player.title}\n"
                ]

                if queue_list:
                    next_title = queue_list[0]['title']
                    description_parts.append(f"**🎵 Próxima Música**\n{next_title}\n")
                    description_parts.append(f"**📝 Restante na Fila**\n{len(queue_list)}")
                else:
                    description_parts.append(f"**🎵 Próxima Música**\nNenhuma\n")
                    description_parts.append(f"**📝 Restante na Fila**\n0")

                embed = discord.Embed(
                    description='\n'.join(description_parts),
                    color=0x2f3136
                )

                view = MusicControls(guild.id)
                message = await queue.loop.send(embed=embed, view=view)
                queue.control_message = message
        except Exception as e:
            print(f'Erro ao tocar próxima música: {e}')
            await play_next(guild, voice_client)
    else:
        # Não há mais músicas
        update_dashboard_status(guild.id)

class MusicControls(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @discord.ui.button(emoji='⏮️', style=discord.ButtonStyle.secondary, row=0)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_client = interaction.guild.voice_client
        if not voice_client:
            await interaction.response.send_message('Não estou em um canal de voz!', ephemeral=True)
            return

        queue = get_queue(self.guild_id)

        # Verificar se tem histórico
        if queue.current_index <= 0:
            await interaction.response.send_message('Já está na primeira música!', ephemeral=True)
            return

        await interaction.response.send_message('⏮️ Voltando...', ephemeral=True)

        # Ativar flag de controle manual
        queue.manual_control = True

        # Decrementar índice manualmente
        queue.current_index -= 1
        prev_song = queue.get_current()

        # Deletar mensagem atual com botões
        if queue.control_message:
            try:
                await queue.control_message.delete()
                queue.control_message = None
            except:
                pass

        voice_client.stop()

        try:
            player = await YTDLSource.from_url(prev_song['url'], loop=bot.loop, stream=True)
            voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(interaction.guild, voice_client), bot.loop))

            # Criar nova mensagem com botões
            queue_list = queue.get_queue()
            description_parts = [
                f"**🎵 Tocando Agora**\n{player.title}\n"
            ]

            if queue_list:
                next_title = queue_list[0]['title']
                description_parts.append(f"**🎵 Próxima Música**\n{next_title}\n")
                description_parts.append(f"**📝 Restante na Fila**\n{len(queue_list)}")
            else:
                description_parts.append(f"**🎵 Próxima Música**\nNenhuma\n")
                description_parts.append(f"**📝 Restante na Fila**\n0")

            embed = discord.Embed(
                description='\n'.join(description_parts),
                color=0x2f3136
            )

            view = MusicControls(interaction.guild.id)
            message = await interaction.channel.send(embed=embed, view=view)
            queue.control_message = message
        except Exception as e:
            await interaction.followup.send(f'Erro: {str(e)}', ephemeral=True)

    @discord.ui.button(emoji='⏸️', style=discord.ButtonStyle.secondary, row=0)
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_client = interaction.guild.voice_client
        if not voice_client:
            await interaction.response.send_message('Não estou em um canal de voz!', ephemeral=True)
            return

        if voice_client.is_playing():
            voice_client.pause()
            button.emoji = '▶️'
            await interaction.response.edit_message(view=self)
        elif voice_client.is_paused():
            voice_client.resume()
            button.emoji = '⏸️'
            await interaction.response.edit_message(view=self)
        else:
            await interaction.response.send_message('Nenhuma música tocando!', ephemeral=True)

    @discord.ui.button(emoji='⏭️', style=discord.ButtonStyle.secondary, row=0)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_client = interaction.guild.voice_client
        if not voice_client:
            await interaction.response.send_message('Não estou em um canal de voz!', ephemeral=True)
            return

        queue = get_queue(self.guild_id)

        if not queue.get_queue():
            await interaction.response.send_message('Não há próximas músicas na fila!', ephemeral=True)
            return

        if voice_client.is_playing() or voice_client.is_paused():
            await interaction.response.send_message('⏭️ Pulando...', ephemeral=True)

            # Deletar mensagem atual com botões
            if queue.control_message:
                try:
                    await queue.control_message.delete()
                    queue.control_message = None
                except:
                    pass

            # Não precisa de flag manual aqui pois queremos o comportamento normal do play_next
            voice_client.stop()
        else:
            await interaction.response.send_message('Nenhuma música tocando!', ephemeral=True)

    @discord.ui.button(emoji='🔀', style=discord.ButtonStyle.secondary, row=0)
    async def shuffle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        queue = get_queue(self.guild_id)

        # Pegar as músicas da fila (não tocadas ainda)
        queue_list = queue.get_queue()

        if not queue_list:
            await interaction.response.send_message('Não há músicas na fila para embaralhar!', ephemeral=True)
            return

        # Embaralhar as músicas da fila
        import random as rand
        rand.shuffle(queue_list)

        # Reconstruir all_songs: histórico + atual + fila embaralhada
        if queue.current_index >= 0:
            # Pegar histórico + música atual
            kept_songs = list(queue.all_songs)[:queue.current_index + 1]
            # Substituir com histórico + atual + fila embaralhada
            queue.all_songs = deque(kept_songs + queue_list)

        button.style = discord.ButtonStyle.success
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(f'🔀 Fila embaralhada! ({len(queue_list)} músicas)', ephemeral=True)

    @discord.ui.button(emoji='📜', style=discord.ButtonStyle.primary, row=0)
    async def queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        queue = get_queue(self.guild_id)
        current_song = queue.get_current()
        queue_list = queue.get_queue()

        if not current_song:
            embed = discord.Embed(color=0x2f3136)
            embed.add_field(
                name='📋 Fila Vazia',
                value='Nenhuma música na fila.\nUse `/play` para adicionar!',
                inline=False
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(color=0x2f3136)

        embed.add_field(
            name='🎵 Tocando Agora',
            value=current_song["title"],
            inline=False
        )

        if queue_list:
            # Listar próximas músicas
            for i, song in enumerate(queue_list[:10], 1):
                embed.add_field(
                    name=f'{i}. Próxima Música',
                    value=song['title'],
                    inline=False
                )

            if len(queue_list) > 10:
                embed.add_field(
                    name='➕ Mais',
                    value=f'{len(queue_list) - 10} música(s) restante(s)',
                    inline=False
                )

            embed.add_field(
                name='📝 Total na Fila',
                value=str(len(queue_list)),
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

# WebSocket Handler
async def handle_websocket_command(command, data):
    """Processa comandos recebidos via WebSocket"""
    global active_guild_id, current_volume, current_song_start_time, songs_played_count

    target_guild_id = data.get("guild_id")
    voice_client = None
    guild = None

    if target_guild_id:
        guild = bot.get_guild(target_guild_id)
        if guild:
            voice_client = guild.voice_client
            active_guild_id = guild.id
    else:
        for g in bot.guilds:
            if g.voice_client:
                voice_client = g.voice_client
                guild = g
                active_guild_id = g.id
                break

    if command == "select_guild":
        new_guild_id = data.get("guild_id")
        if new_guild_id:
            active_guild_id = new_guild_id
            update_dashboard_status(new_guild_id)
        return {"success": True}

    elif command == "skip" and voice_client:
        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()
        return {"success": True}

    elif command == "pause" and voice_client:
        if voice_client.is_playing():
            voice_client.pause()
            update_dashboard_status(guild.id)
        return {"success": True}

    elif command == "resume" and voice_client:
        if voice_client.is_paused():
            voice_client.resume()
            update_dashboard_status(guild.id)
        return {"success": True}

    elif command == "volume" and voice_client:
        new_volume = data.get("value", 0.5)
        current_volume = max(0.0, min(1.0, new_volume))
        if voice_client.source and hasattr(voice_client.source, 'volume'):
            voice_client.source.volume = current_volume
        update_dashboard_status(guild.id if guild else None)
        return {"success": True}

    elif command == "previous" and voice_client and guild:
        queue = get_queue(guild.id)
        if queue.current_index > 0:
            queue.manual_control = True
            queue.current_index -= 1
            prev_song = queue.get_current()
            if queue.control_message:
                try:
                    await queue.control_message.delete()
                    queue.control_message = None
                except:
                    pass
            voice_client.stop()
            try:
                player = await YTDLSource.from_url(prev_song['url'], loop=bot.loop, stream=True, volume=current_volume)
                voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(guild, voice_client), bot.loop))
                update_dashboard_status(guild.id)
            except Exception as e:
                return {"success": False, "error": str(e)}
        return {"success": True}

    elif command == "add_music" and data.get("url"):
        url = data["url"]
        # Reconectar se necessário
        if not voice_client and last_voice_channel_id and active_guild_id:
            try:
                guild = bot.get_guild(active_guild_id)
                if guild:
                    channel = guild.get_channel(last_voice_channel_id)
                    if channel:
                        voice_client = await channel.connect(timeout=30.0, reconnect=True)
            except:
                pass

        if voice_client:
            if not guild:
                guild = voice_client.guild
            queue = get_queue(guild.id)
            text_channel = guild.get_channel(last_text_channel_id) if last_text_channel_id else None
            queue.loop = text_channel

            try:
                search_url = url
                if is_spotify_url(url) and 'track' in url:
                    track_query = extract_spotify_track(url)
                    if track_query:
                        search_url = track_query

                partial_data = await bot.loop.run_in_executor(
                    None, lambda u=search_url: ytdl.extract_info(u, download=False)
                )

                if partial_data:
                    if 'entries' in partial_data and partial_data['entries']:
                        partial_data = partial_data['entries'][0]

                    song_data = {
                        'url': search_url,
                        'title': partial_data.get('title'),
                        'webpage_url': partial_data.get('webpage_url', search_url),
                        'duration': partial_data.get('duration', 0),
                        'thumbnail': partial_data.get('thumbnail')
                    }
                    queue.add(song_data)

                    if not voice_client.is_playing() and not voice_client.is_paused():
                        current_song_start_time = time.time()
                        songs_played_count += 1
                        queue.current_index = len(queue.all_songs) - 1
                        player = await YTDLSource.from_url(search_url, loop=bot.loop, stream=True, volume=current_volume)
                        voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(guild, voice_client), bot.loop))

                        if text_channel:
                            embed = discord.Embed(
                                description=f"**🎵 Tocando Agora (via Dashboard)**\n{player.title}",
                                color=0x2f3136
                            )
                            view = MusicControls(guild.id)
                            message = await text_channel.send(embed=embed, view=view)
                            queue.control_message = message
                    else:
                        if text_channel:
                            position = len(queue.all_songs) - queue.current_index - 1
                            embed = discord.Embed(
                                description=f"**📝 Adicionado à fila (via Dashboard)**\n{song_data['title']}\n\n**Posição:** #{position}",
                                color=0x2f3136
                            )
                            await text_channel.send(embed=embed)

                    update_dashboard_status(guild.id)
                    return {"success": True, "title": song_data['title']}
            except Exception as e:
                return {"success": False, "error": str(e)}

    return {"success": False, "error": "Comando não reconhecido ou bot não conectado"}

async def websocket_handler(websocket):
    """Handler para conexões WebSocket"""
    global next_client_id

    # Registrar novo cliente
    client_id = next_client_id
    next_client_id += 1

    websocket_clients[client_id] = {
        "websocket": websocket,
        "connected_at": time.time(),
        "name": f"Usuário {client_id}",
        "is_host": len(websocket_clients) == 0  # Primeiro a conectar é host
    }

    is_this_host = is_host(client_id)
    print(f"🔌 Cliente #{client_id} conectado {'(HOST)' if is_this_host else ''}. Total: {len(websocket_clients)}")

    # Enviar info inicial para o cliente
    welcome_msg = {
        "type": "welcome",
        "client_id": client_id,
        "is_host": is_this_host,
        "users": get_users_list()
    }
    await websocket.send(json.dumps(welcome_msg))

    # Notificar todos sobre novo usuário
    await broadcast_users_update()

    # Enviar status inicial
    update_dashboard_status()

    try:
        async for message in websocket:
            try:
                cmd = json.loads(message)
                command = cmd.get("command")
                data = cmd.get("data", {})

                # Comando para definir nome do usuário
                if command == "set_name":
                    new_name = data.get("name", f"Usuário {client_id}")
                    websocket_clients[client_id]["name"] = new_name
                    print(f"👤 Cliente #{client_id} agora é '{new_name}'")
                    await broadcast_users_update()
                    await websocket.send(json.dumps({"type": "response", "command": command, "success": True}))
                    continue

                print(f"📨 WebSocket comando de #{client_id}: {command}")

                result = await handle_websocket_command(command, data)
                await websocket.send(json.dumps({"type": "response", "command": command, **result}))
            except json.JSONDecodeError:
                await websocket.send(json.dumps({"type": "error", "message": "JSON inválido"}))
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        # Remover cliente
        was_host = is_host(client_id)
        del websocket_clients[client_id]
        print(f"🔌 Cliente #{client_id} desconectado. Total: {len(websocket_clients)}")

        # Se era o host, notificar novo host
        if was_host and websocket_clients:
            new_host_id = get_host_client_id()
            print(f"👑 Novo host: Cliente #{new_host_id}")

        # Notificar todos sobre saída do usuário
        if websocket_clients:
            await broadcast_users_update()

async def start_websocket_server():
    """Inicia o servidor WebSocket"""
    if not WEBSOCKET_AVAILABLE:
        return
    try:
        # Obter IP local para exibir
        import socket
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)

        server = await websockets.serve(websocket_handler, WEBSOCKET_HOST, WEBSOCKET_PORT)
        print(f"🌐 Servidor WebSocket iniciado!")
        print(f"   Local: ws://localhost:{WEBSOCKET_PORT}")
        print(f"   Rede:  ws://{local_ip}:{WEBSOCKET_PORT}")
        return server
    except Exception as e:
        print(f"❌ Erro ao iniciar WebSocket: {e}")

@bot.event
async def on_ready():
    global active_guild_id
    print(f'Bot conectado como {bot.user.name}')
    print(f'ID: {bot.user.id}')
    print('------')
    await bot.tree.sync()
    print('Comandos slash sincronizados')

    # Iniciar servidor WebSocket
    if WEBSOCKET_AVAILABLE:
        await start_websocket_server()
    else:
        print(f'📁 Arquivo de comandos: {COMMAND_FILE}')

    # Iniciar task de verificação de comandos do dashboard (fallback)
    if not check_dashboard_commands.is_running():
        check_dashboard_commands.start()
        print('✅ Task de verificação de comandos do dashboard iniciada')

@tasks.loop(seconds=1)
async def check_dashboard_commands():
    """Verifica comandos enviados pelo dashboard"""
    global active_guild_id, active_voice_client, current_song_start_time, current_volume, songs_played_count

    try:
        # Debug: verificar se arquivo existe
        if os.path.exists(COMMAND_FILE):
            print(f"📥 Comando detectado no arquivo: {COMMAND_FILE}")
            with open(COMMAND_FILE, 'r', encoding='utf-8') as f:
                cmd = json.load(f)
            
            # Remover arquivo após ler
            os.remove(COMMAND_FILE)
            
            command = cmd.get("command")
            data = cmd.get("data", {})
            print(f"📋 Comando recebido: {command}, dados: {data}")

            # Usar guild_id especificado ou encontrar automaticamente
            target_guild_id = data.get("guild_id")
            voice_client = None
            guild = None

            if target_guild_id:
                # Usar guild específica
                guild = bot.get_guild(target_guild_id)
                if guild:
                    voice_client = guild.voice_client
                    active_guild_id = guild.id
                    print(f"🎯 Usando guild específica: {guild.name}")
            else:
                # Encontrar guild ativa com voice client
                for g in bot.guilds:
                    if g.voice_client:
                        voice_client = g.voice_client
                        guild = g
                        active_guild_id = g.id
                        print(f"✅ Guild com voice client encontrada: {g.name}")
                        break

            if not voice_client and command not in ["select_guild"]:
                print("❌ Nenhuma guild com voice client encontrada!")
                print(f"   Guilds disponíveis: {[g.name for g in bot.guilds]}")

            # Comando para selecionar guild
            if command == "select_guild":
                new_guild_id = data.get("guild_id")
                if new_guild_id:
                    active_guild_id = new_guild_id
                    new_guild = bot.get_guild(new_guild_id)
                    if new_guild:
                        print(f"🖥️ Guild selecionada: {new_guild.name}")
                        update_dashboard_status(new_guild_id)

            elif command == "skip" and voice_client:
                if voice_client.is_playing() or voice_client.is_paused():
                    voice_client.stop()
                    print("⏭️ Música pulada via dashboard")
                    
            elif command == "pause" and voice_client:
                if voice_client.is_playing():
                    voice_client.pause()
                    print("⏸️ Música pausada via dashboard")
                    update_dashboard_status(guild.id)
                    
            elif command == "resume" and voice_client:
                if voice_client.is_paused():
                    voice_client.resume()
                    print("▶️ Música retomada via dashboard")
                    update_dashboard_status(guild.id)

            elif command == "volume" and voice_client:
                global current_volume
                new_volume = data.get("value", 0.5)
                current_volume = max(0.0, min(1.0, new_volume))
                # Atualizar volume do player atual se estiver tocando
                if voice_client.source and hasattr(voice_client.source, 'volume'):
                    voice_client.source.volume = current_volume
                print(f"🔊 Volume alterado para: {int(current_volume * 100)}%")
                update_dashboard_status(guild.id if guild else None)

            elif command == "previous" and voice_client and guild:
                queue = get_queue(guild.id)
                if queue.current_index > 0:
                    queue.manual_control = True
                    queue.current_index -= 1
                    prev_song = queue.get_current()
                    
                    if queue.control_message:
                        try:
                            await queue.control_message.delete()
                            queue.control_message = None
                        except:
                            pass
                    
                    voice_client.stop()
                    
                    try:
                        player = await YTDLSource.from_url(prev_song['url'], loop=bot.loop, stream=True)
                        voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(guild, voice_client), bot.loop))
                        print(f"⏮️ Voltando para: {player.title}")
                        update_dashboard_status(guild.id)
                    except Exception as e:
                        print(f"Erro ao voltar música: {e}")
                        
            elif command == "add_music" and data.get("url"):
                url = data["url"]
                print(f"🎵 Adicionando música via dashboard: {url}")

                # Se não há voice_client, tentar reconectar ao último canal usado
                if not voice_client and last_voice_channel_id and active_guild_id:
                    try:
                        guild = bot.get_guild(active_guild_id)
                        if guild:
                            channel = guild.get_channel(last_voice_channel_id)
                            if channel:
                                voice_client = await channel.connect(timeout=30.0, reconnect=True)
                                print(f"✅ Reconectado ao canal de voz: {channel.name}")
                    except Exception as e:
                        print(f"❌ Erro ao reconectar ao canal de voz: {e}")
                        voice_client = None

                if not voice_client:
                    print("⚠️ Bot não está em nenhum canal de voz. Use /play no Discord primeiro para conectar.")
                else:
                    # Garantir que guild está definida
                    if not guild:
                        guild = voice_client.guild
                    queue = get_queue(guild.id)

                    # Obter canal de texto para enviar mensagens
                    text_channel = None
                    if last_text_channel_id:
                        text_channel = guild.get_channel(last_text_channel_id)
                    queue.loop = text_channel

                    try:
                        # Verificar se é Spotify
                        search_url = url
                        if is_spotify_url(url):
                            if 'track' in url:
                                track_query = extract_spotify_track(url)
                                if track_query:
                                    search_url = track_query
                                    print(f"Spotify track convertido para: {search_url}")

                        partial_data = await bot.loop.run_in_executor(
                            None,
                            lambda u=search_url: ytdl.extract_info(u, download=False)
                        )

                        if partial_data:
                            if 'entries' in partial_data and partial_data['entries']:
                                partial_data = partial_data['entries'][0]

                            song_data = {
                                'url': search_url,
                                'title': partial_data.get('title'),
                                'webpage_url': partial_data.get('webpage_url', search_url),
                                'duration': partial_data.get('duration', 0),
                                'thumbnail': partial_data.get('thumbnail')
                            }

                            queue.add(song_data)
                            print(f"✅ Música adicionada à fila: {song_data['title']}")

                            # Se não está tocando, começar a tocar
                            was_playing = voice_client.is_playing() or voice_client.is_paused()
                            if not was_playing:
                                import time
                                current_song_start_time = time.time()
                                songs_played_count += 1
                                queue.current_index = len(queue.all_songs) - 1
                                player = await YTDLSource.from_url(search_url, loop=bot.loop, stream=True, volume=current_volume)
                                voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(guild, voice_client), bot.loop))
                                print(f"▶️ Tocando: {player.title}")

                                # Enviar mensagem no Discord
                                if text_channel:
                                    embed = discord.Embed(
                                        description=f"**🎵 Tocando Agora (via Dashboard)**\n{player.title}",
                                        color=0x2f3136
                                    )
                                    view = MusicControls(guild.id)
                                    message = await text_channel.send(embed=embed, view=view)
                                    queue.control_message = message
                            else:
                                # Música adicionada à fila
                                if text_channel:
                                    position = len(queue.all_songs) - queue.current_index - 1
                                    embed = discord.Embed(
                                        description=f"**📝 Adicionado à fila (via Dashboard)**\n{song_data['title']}\n\n**Posição:** #{position}",
                                        color=0x2f3136
                                    )
                                    await text_channel.send(embed=embed)

                            update_dashboard_status(guild.id)
                        else:
                            print(f"❌ Não foi possível obter informações da música")
                    except Exception as e:
                        print(f"❌ Erro ao adicionar música: {e}")
                        import traceback
                        traceback.print_exc()
    except Exception as e:
        if "No such file" not in str(e) and "cannot find" not in str(e).lower():
            print(f"Erro ao verificar comandos: {e}")

@bot.event
async def on_voice_state_update(member, before, after):
    # Verificar se alguém saiu de um canal de voz
    if before.channel is not None:
        voice_client = member.guild.voice_client

        # Verificar se o bot está no canal
        if voice_client and voice_client.channel == before.channel:
            # Contar quantos membros (exceto o bot) estão no canal
            members = [m for m in before.channel.members if not m.bot]

            # Se não há ninguém além de bots, sair
            if len(members) == 0:
                await voice_client.disconnect()
                # Limpar fila
                queue = get_queue(member.guild.id)
                queue.clear()
                queue.control_message = None

@bot.tree.command(name='play', description='Toca uma música do YouTube ou Spotify')
async def play(interaction: discord.Interaction, url: str):
    if not interaction.user.voice:
        await interaction.response.send_message('Você precisa estar em um canal de voz!')
        return

    # Defer IMEDIATAMENTE para evitar timeout
    try:
        await interaction.response.defer()
    except:
        return  # Interação já expirou

    try:
        global last_voice_channel_id, last_text_channel_id, active_guild_id, current_song_start_time, songs_played_count

        if not interaction.guild.voice_client:
            channel = interaction.user.voice.channel
            voice_client = await channel.connect(timeout=30.0, reconnect=True)
        else:
            voice_client = interaction.guild.voice_client

        # Salvar canal e guild para uso do dashboard
        last_voice_channel_id = voice_client.channel.id
        last_text_channel_id = interaction.channel.id
        active_guild_id = interaction.guild.id

        queue = get_queue(interaction.guild.id)
        queue.loop = interaction.channel

        # Verificar se é link do Spotify
        spotify_tracks = []
        is_spotify = is_spotify_url(url)

        if is_spotify:
            print(f'Link do Spotify detectado: {url}')

            # Detectar tipo de link do Spotify
            if 'track' in url:
                track_query = extract_spotify_track(url)
                if track_query:
                    spotify_tracks = [track_query]
            elif 'playlist' in url:
                playlist_tracks = extract_spotify_playlist(url)
                if playlist_tracks:
                    spotify_tracks = playlist_tracks
            elif 'album' in url:
                album_tracks = extract_spotify_album(url)
                if album_tracks:
                    spotify_tracks = album_tracks

            if not spotify_tracks:
                print('Falha ao extrair informações do Spotify')
                await interaction.followup.send('❌ Não foi possível processar este link do Spotify. Verifique o console para mais detalhes.')
                return

        # Processar músicas (única ou múltiplas do Spotify)
        if spotify_tracks:
            # Playlist/Album do Spotify
            is_playing_before = voice_client.is_playing() or voice_client.is_paused()

            # Tocar primeira música IMEDIATAMENTE (com fallback)
            if not is_playing_before and spotify_tracks:
                first_song_started = False
                attempts = 0
                max_attempts = min(5, len(spotify_tracks))  # Tentar até 5 músicas

                while not first_song_started and attempts < max_attempts:
                    try:
                        first_query = spotify_tracks[attempts]
                        print(f'Tentando tocar: {first_query}')

                        partial_data = await bot.loop.run_in_executor(
                            None,
                            lambda fq=first_query: ytdl.extract_info(fq, download=False)
                        )

                        if partial_data is None:
                            raise Exception("Sem dados")
                        
                        if 'entries' in partial_data:
                            if len(partial_data['entries']) == 0:
                                raise Exception("Sem resultados")
                            partial_data = partial_data['entries'][0]

                        first_song = {
                            'url': first_query,
                            'title': partial_data.get('title'),
                            'webpage_url': partial_data.get('webpage_url', first_query),
                            'duration': partial_data.get('duration', 0),
                            'thumbnail': partial_data.get('thumbnail')
                        }

                        queue.add(first_song)
                        queue.current_index = 0

                        import time
                        current_song_start_time = time.time()
                        songs_played_count += 1
                        player = await YTDLSource.from_url(first_query, loop=bot.loop, stream=True, volume=current_volume)
                        voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(interaction.guild, voice_client), bot.loop))

                        # Atualizar dashboard
                        update_dashboard_status(interaction.guild.id)

                        # Mostrar mensagem de "tocando agora"
                        embed = discord.Embed(
                            description=f"**🎵 Tocando Agora**\n{player.title}\n\n**⏳ Carregando playlist...**\n{len(spotify_tracks) - attempts - 1} músicas restantes",
                            color=0x2f3136
                        )
                        view = MusicControls(interaction.guild.id)
                        message = await interaction.followup.send(embed=embed, view=view)
                        queue.control_message = message

                        first_song_started = True
                        print(f'✅ Primeira música iniciada: {player.title}')

                        # Remover músicas tentadas da lista
                        spotify_tracks = spotify_tracks[attempts + 1:]
                    except Exception as e:
                        print(f'❌ Erro ao tocar música {attempts + 1}: {first_query} - {e}')
                        attempts += 1

                        if attempts >= max_attempts:
                            await interaction.followup.send(f'❌ Não foi possível iniciar reprodução após {max_attempts} tentativas. Verifique o console.')
                            return

            # Adicionar resto em background
            async def add_remaining_tracks():
                added_count = 1 if not is_playing_before else 0  # Contar a primeira
                failed_count = 0
                total_to_add = len(spotify_tracks)

                for search_query in spotify_tracks:
                    try:
                        partial_data = await bot.loop.run_in_executor(
                            None,
                            lambda sq=search_query: ytdl.extract_info(sq, download=False)
                        )

                        if partial_data is None:
                            raise Exception("Sem dados")

                        if 'entries' in partial_data:
                            if len(partial_data['entries']) == 0:
                                raise Exception("Sem resultados")
                            partial_data = partial_data['entries'][0]

                        song_data = {
                            'url': search_query,
                            'title': partial_data.get('title'),
                            'webpage_url': partial_data.get('webpage_url', search_query),
                            'duration': partial_data.get('duration', 0),
                            'thumbnail': partial_data.get('thumbnail')
                        }

                        queue.add(song_data)
                        added_count += 1

                        # Atualizar mensagem a cada 5 músicas
                        if added_count % 5 == 0 and queue.control_message:
                            try:
                                current = queue.get_current()
                                queue_list = queue.get_queue()
                                description_parts = [f"**🎵 Tocando Agora**\n{current['title'] if current else 'Carregando...'}\n"]

                                if queue_list:
                                    description_parts.append(f"**🎵 Próxima Música**\n{queue_list[0]['title']}\n")
                                    description_parts.append(f"**📝 Restante na Fila**\n{len(queue_list)} | ⏳ {added_count}/{total_to_add}")
                                else:
                                    description_parts.append(f"**⏳ Carregando...**\n{added_count}/{total_to_add} músicas")

                                embed = discord.Embed(description='\n'.join(description_parts), color=0x2f3136)
                                view = MusicControls(interaction.guild.id)
                                await queue.control_message.edit(embed=embed, view=view)
                            except:
                                pass

                    except Exception as e:
                        error_msg = str(e)
                        if 'DRM protected' in error_msg:
                            print(f'⚠️ Vídeo protegido por DRM, pulando: {search_query}')
                        else:
                            print(f'❌ Erro ao adicionar música: {search_query} - {e}')
                        failed_count += 1

                # Atualizar mensagem final
                if queue.control_message:
                    try:
                        current = queue.get_current()
                        queue_list = queue.get_queue()
                        description_parts = [f"**🎵 Tocando Agora**\n{current['title'] if current else 'Nenhuma'}\n"]

                        if queue_list:
                            description_parts.append(f"**🎵 Próxima Música**\n{queue_list[0]['title']}\n")
                            description_parts.append(f"**📝 Restante na Fila**\n{len(queue_list)}")
                        else:
                            description_parts.append(f"**🎵 Próxima Música**\nNenhuma\n")
                            description_parts.append(f"**📝 Restante na Fila**\n0")

                        embed = discord.Embed(description='\n'.join(description_parts), color=0x2f3136)
                        view = MusicControls(interaction.guild.id)
                        await queue.control_message.edit(embed=embed, view=view)
                    except:
                        pass

                print(f'✅ Playlist carregada: {added_count} adicionadas, {failed_count} falharam')

            # Se estava tocando antes, mostrar mensagem de "adicionando"
            if is_playing_before:
                embed = discord.Embed(color=0x2f3136)
                embed.add_field(
                    name='⏳ Adicionando à Fila',
                    value=f'{len(spotify_tracks)} música(s) do Spotify',
                    inline=False
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

            # Executar em background
            asyncio.create_task(add_remaining_tracks())
        else:
            # Link normal do YouTube ou busca
            print(f"Buscando: {url}")
            
            try:
                partial_data = await bot.loop.run_in_executor(
                    None,
                    lambda: ytdl.extract_info(url, download=False)
                )
            except Exception as e:
                print(f"Erro no yt-dlp: {e}")
                await interaction.followup.send(f'❌ Erro ao buscar música: {str(e)[:100]}')
                return

            print(f"Resultado obtido do yt-dlp (tipo: {type(partial_data).__name__})")

            if partial_data is None:
                await interaction.followup.send('❌ Não foi possível obter informações da música.')
                return

            if 'entries' in partial_data:
                print(f"Entries encontradas: {len(partial_data.get('entries', []))}")
                if not partial_data['entries'] or len(partial_data['entries']) == 0:
                    await interaction.followup.send('❌ Nenhum resultado encontrado.')
                    return
                partial_data = partial_data['entries'][0]

            song_data = {
                'url': url,
                'title': partial_data.get('title'),
                'webpage_url': partial_data.get('webpage_url', url),
                'duration': partial_data.get('duration', 0),
                'thumbnail': partial_data.get('thumbnail')
            }

            if voice_client.is_playing() or voice_client.is_paused():
                queue.add(song_data)
                embed = discord.Embed(color=0x2f3136)
                embed.add_field(
                    name='✅ Adicionado à Fila',
                    value=song_data["title"],
                    inline=False
                )
                embed.add_field(
                    name='📝 Posição na Fila',
                    value=str(len(queue.get_list())),
                    inline=False
                )
                await interaction.followup.send(embed=embed)
                update_dashboard_status(interaction.guild.id)
                return  # Sair aqui pois música foi adicionada à fila
            else:
                # Adicionar na lista e setar índice como 0
                queue.add(song_data)
                queue.current_index = 0

                import time
                current_song_start_time = time.time()
                songs_played_count += 1

                await asyncio.sleep(0.5)
                player = await YTDLSource.from_url(url, loop=bot.loop, stream=True, volume=current_volume)
                voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(interaction.guild, voice_client), bot.loop))

                # Atualizar dashboard
                update_dashboard_status(interaction.guild.id)

                queue_list = queue.get_queue()

                # Criar descrição longa para formato retangular
                description_parts = [
                    f"**🎵 Tocando Agora**\n{player.title}\n"
                ]

                if queue_list:
                    next_title = queue_list[0]['title']
                    description_parts.append(f"**🎵 Próxima Música**\n{next_title}\n")
                    description_parts.append(f"**📝 Restante na Fila**\n{len(queue_list)}")
                else:
                    description_parts.append(f"**🎵 Próxima Música**\nNenhuma\n")
                    description_parts.append(f"**📝 Restante na Fila**\n0")

                embed = discord.Embed(
                    description='\n'.join(description_parts),
                    color=0x2f3136
                )

                view = MusicControls(interaction.guild.id)
                message = await interaction.followup.send(embed=embed, view=view)
                queue.control_message = message

    except discord.errors.ConnectionClosed:
        await interaction.followup.send('Erro de conexão ao canal de voz. Tente novamente.')
    except Exception as e:
        import traceback
        traceback.print_exc()
        await interaction.followup.send(f'Erro ao tocar música: {str(e)}')

@bot.tree.command(name='queue', description='Mostra a fila de músicas')
async def queue_command(interaction: discord.Interaction):
    queue = get_queue(interaction.guild.id)
    current_song = queue.get_current()
    queue_list = queue.get_queue()

    if not current_song:
        embed = discord.Embed(color=0x2f3136)
        embed.add_field(
            name='📋 Fila Vazia',
            value='Nenhuma música na fila.\nUse `/play` para adicionar!',
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    embed = discord.Embed(color=0x2f3136)

    embed.add_field(
        name='🎵 Tocando Agora',
        value=current_song["title"],
        inline=False
    )

    if queue_list:
        # Listar próximas músicas
        for i, song in enumerate(queue_list[:10], 1):
            embed.add_field(
                name=f'{i}. Próxima Música',
                value=song['title'],
                inline=False
            )

        if len(queue_list) > 10:
            embed.add_field(
                name='➕ Mais',
                value=f'{len(queue_list) - 10} música(s) restante(s)',
                inline=False
            )

        embed.add_field(
            name='📝 Total na Fila',
            value=str(len(queue_list)),
            inline=False
        )

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name='skip', description='Pula a música atual')
async def skip(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if not voice_client or not voice_client.is_playing():
        embed = discord.Embed(
            title='❌ Nada Tocando',
            description='Não há música para pular no momento.',
            color=0xe74c3c
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    queue = get_queue(interaction.guild.id)
    current_song = queue.get_current()
    skipped_song = current_song['title'] if current_song else 'Música'

    voice_client.stop()

    embed = discord.Embed(
        title='⏭️ Música Pulada',
        description=f'```{skipped_song}```',
        color=0xf39c12
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name='stop', description='Para a reprodução e limpa a fila')
async def stop(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if not voice_client:
        await interaction.response.send_message('Não estou em um canal de voz!', ephemeral=True)
        return

    queue = get_queue(interaction.guild.id)

    # Deletar mensagem com botões
    if queue.control_message:
        try:
            await queue.control_message.delete()
        except:
            pass

    queue.clear()
    queue.control_message = None

    if voice_client.is_playing() or voice_client.is_paused():
        queue.manual_control = True  # Evitar que play_next toque após stop
        voice_client.stop()

    await voice_client.disconnect()

    embed = discord.Embed(
        title='⏹️ Reprodução Parada',
        description='Fila limpa e desconectado do canal de voz.',
        color=0xe74c3c
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name='clear', description='Limpa todas as mensagens do canal')
async def clear_messages(interaction: discord.Interaction):
    """Limpa todas as mensagens do canal"""

    await interaction.response.defer(ephemeral=True)

    try:
        deleted = 0
        messages_to_delete = []

        async for message in interaction.channel.history(limit=None):
            messages_to_delete.append(message)

            # Bulk delete em lotes de 50 para evitar rate limit
            if len(messages_to_delete) == 50:
                try:
                    await interaction.channel.delete_messages(messages_to_delete)
                    deleted += len(messages_to_delete)
                    messages_to_delete = []
                    await asyncio.sleep(1.5)  # Delay para evitar rate limit
                except:
                    # Se falhar bulk delete, deletar uma por uma com delay
                    for msg in messages_to_delete:
                        try:
                            await msg.delete()
                            deleted += 1
                            await asyncio.sleep(0.5)
                        except:
                            pass
                    messages_to_delete = []

        # Deletar mensagens restantes
        if messages_to_delete:
            try:
                if len(messages_to_delete) == 1:
                    await messages_to_delete[0].delete()
                else:
                    await interaction.channel.delete_messages(messages_to_delete)
                deleted += len(messages_to_delete)
            except:
                for msg in messages_to_delete:
                    try:
                        await msg.delete()
                        deleted += 1
                        await asyncio.sleep(0.5)
                    except:
                        pass

        await interaction.followup.send(f'🗑️ {deleted} mensagens apagadas!', ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f'Erro: {str(e)}', ephemeral=True)

bot.run(TOKEN)