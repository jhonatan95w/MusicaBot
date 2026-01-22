"""
Dashboard para o Bot de Música do Discord
Execute como programa independente: python dashboard.py
"""

import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import threading
import queue
import os
import sys
import json
import time
import io
import urllib.request
import asyncio
from datetime import datetime

# Tentar importar PIL para thumbnails (opcional)
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("PIL não encontrado - thumbnails desabilitadas. Instale com: pip install Pillow")

# Tentar importar websockets para comunicação em tempo real
try:
    import websockets
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False
    print("websockets não encontrado - usando fallback JSON. Instale com: pip install websockets")

# Configuração do servidor - pode ser alterada para conectar a outro PC
WEBSOCKET_HOST = "localhost"  # Mude para o IP do PC que roda o bot
WEBSOCKET_PORT = 8765
WEBSOCKET_URI = f"ws://{WEBSOCKET_HOST}:{WEBSOCKET_PORT}"

# Arquivo de configuração para salvar o IP do servidor
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".dashboard_config.json")

def load_server_config():
    """Carrega configuração do servidor"""
    global WEBSOCKET_HOST, WEBSOCKET_URI
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                WEBSOCKET_HOST = config.get("host", "localhost")
                WEBSOCKET_URI = f"ws://{WEBSOCKET_HOST}:{WEBSOCKET_PORT}"
    except:
        pass

def save_server_config(host):
    """Salva configuração do servidor"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump({"host": host}, f)
    except:
        pass

load_server_config()

# Banco de dados para histórico e favoritos
try:
    from database import MusicDatabase
    db = MusicDatabase()
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False
    db = None
    print("database.py não encontrado - histórico e favoritos desabilitados")

class BotDashboard:
    def __init__(self, root):
        self.root = root
        self.root.title("🎵 Bot de Música - Dashboard")
        self.root.geometry("800x600")
        self.root.configure(bg="#2f3136")
        
        # Estado do bot
        self.bot_process = None
        self.bot_running = False
        self.output_queue = queue.Queue()
        self.log_lines = []
        
        # Estado da música atual
        self.current_song = "Nenhuma música tocando"
        self.current_song_url = None
        self.is_paused = False
        self.song_duration = 0
        self.song_start_time = None
        self.current_thumbnail_url = None
        self.thumbnail_image = None
        self.current_volume = 0.5
        self.voice_channel = None

        # Servidores
        self.guilds = []
        self.selected_guild_id = None

        # Arquivo de comunicação com o bot (fallback)
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.status_file = os.path.join(self.script_dir, ".bot_status.json")
        self.command_file = os.path.join(self.script_dir, ".bot_command.json")

        # WebSocket
        self.websocket = None
        self.websocket_connected = False
        self.websocket_loop = None
        self.websocket_thread = None
        self.message_queue = queue.Queue()

        # Multi-usuário
        self.client_id = None
        self.is_host = False
        self.connected_users = []
        self.user_name = os.getenv("USERNAME", os.getenv("USER", "Usuário"))

        # Estatísticas
        self.stats = {
            "start_time": None,
            "commands_executed": 0,
            "songs_played": 0,
            "playlists_loaded": 0,
            "errors": 0
        }
        
        self.setup_ui()
        self.check_output_queue()
        self.check_bot_status()
        self.update_progress()

    def setup_ui(self):
        # Estilo
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TFrame", background="#2f3136")
        style.configure("TLabel", background="#2f3136", foreground="white", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Stats.TLabel", font=("Segoe UI", 12))
        style.configure("TButton", font=("Segoe UI", 10))
        
        # Frame principal
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        title_label = ttk.Label(header_frame, text="🎵 Bot de Música - Dashboard", style="Title.TLabel")
        title_label.pack(side=tk.LEFT)

        # Seletor de servidor
        server_frame = tk.Frame(header_frame, bg="#2f3136")
        server_frame.pack(side=tk.LEFT, padx=20)

        tk.Label(server_frame, text="🖥️ Servidor:", bg="#2f3136", fg="#b9bbbe",
                 font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(0, 5))

        self.server_var = tk.StringVar()
        self.server_combo = ttk.Combobox(
            server_frame,
            textvariable=self.server_var,
            state="readonly",
            width=25,
            font=("Segoe UI", 10)
        )
        self.server_combo.pack(side=tk.LEFT)
        self.server_combo.bind("<<ComboboxSelected>>", self.on_server_select)

        # Status indicator
        self.status_frame = tk.Frame(header_frame, bg="#2f3136")
        self.status_frame.pack(side=tk.RIGHT)

        self.status_dot = tk.Canvas(self.status_frame, width=15, height=15, bg="#2f3136", highlightthickness=0)
        self.status_dot.pack(side=tk.LEFT, padx=5)
        self.status_indicator = self.status_dot.create_oval(2, 2, 13, 13, fill="#e74c3c", outline="")

        self.status_label = ttk.Label(self.status_frame, text="Desligado", style="Stats.TLabel")
        self.status_label.pack(side=tk.LEFT)

        # Frame de conexão e usuários
        connection_frame = ttk.Frame(main_frame)
        connection_frame.pack(fill=tk.X, pady=(0, 5))

        # IP do servidor (para conectar remotamente)
        ip_frame = tk.Frame(connection_frame, bg="#2f3136")
        ip_frame.pack(side=tk.LEFT)

        tk.Label(ip_frame, text="🌐 IP do Servidor:", bg="#2f3136", fg="#b9bbbe",
                 font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 5))

        self.server_ip_entry = tk.Entry(
            ip_frame,
            bg="#40444b",
            fg="white",
            font=("Segoe UI", 9),
            insertbackground="white",
            relief=tk.FLAT,
            width=15
        )
        self.server_ip_entry.pack(side=tk.LEFT, ipady=2)
        self.server_ip_entry.insert(0, WEBSOCKET_HOST)

        self.connect_btn = tk.Button(
            ip_frame,
            text="Conectar",
            command=self.connect_to_server,
            bg="#7289da", fg="white",
            font=("Segoe UI", 9),
            relief=tk.FLAT,
            padx=8, pady=1,
            cursor="hand2"
        )
        self.connect_btn.pack(side=tk.LEFT, padx=(5, 0))

        # Indicador de Host e usuários conectados
        users_frame = tk.Frame(connection_frame, bg="#2f3136")
        users_frame.pack(side=tk.RIGHT)

        self.host_label = tk.Label(
            users_frame,
            text="",
            bg="#2f3136",
            fg="#faa61a",
            font=("Segoe UI", 9, "bold")
        )
        self.host_label.pack(side=tk.LEFT, padx=(0, 10))

        self.users_label = tk.Label(
            users_frame,
            text="👥 0 conectados",
            bg="#2f3136",
            fg="#b9bbbe",
            font=("Segoe UI", 9)
        )
        self.users_label.pack(side=tk.LEFT)

        # Botões de controle
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=10)
        
        self.start_btn = tk.Button(
            control_frame, 
            text="▶ Iniciar Bot", 
            command=self.start_bot,
            bg="#43b581", fg="white", 
            font=("Segoe UI", 11, "bold"),
            relief=tk.FLAT,
            padx=20, pady=8,
            cursor="hand2"
        )
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = tk.Button(
            control_frame, 
            text="⏹ Parar Bot", 
            command=self.stop_bot,
            bg="#e74c3c", fg="white", 
            font=("Segoe UI", 11, "bold"),
            relief=tk.FLAT,
            padx=20, pady=8,
            cursor="hand2",
            state=tk.DISABLED
        )
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        self.clear_log_btn = tk.Button(
            control_frame, 
            text="🗑 Limpar Log", 
            command=self.clear_log,
            bg="#7289da", fg="white", 
            font=("Segoe UI", 11),
            relief=tk.FLAT,
            padx=15, pady=8,
            cursor="hand2"
        )
        self.clear_log_btn.pack(side=tk.RIGHT, padx=5)
        
        # Frame de música atual tocando
        now_playing_frame = tk.LabelFrame(
            main_frame,
            text=" 🎵 Tocando Agora ",
            bg="#36393f",
            fg="white",
            font=("Segoe UI", 11, "bold"),
            padx=10, pady=10
        )
        now_playing_frame.pack(fill=tk.X, pady=10)

        # Container principal com thumbnail e info
        now_playing_content = tk.Frame(now_playing_frame, bg="#36393f")
        now_playing_content.pack(fill=tk.X, pady=5)

        # Thumbnail (lado esquerdo)
        self.thumbnail_frame = tk.Frame(now_playing_content, bg="#36393f", width=80, height=80)
        self.thumbnail_frame.pack(side=tk.LEFT, padx=(0, 15))
        self.thumbnail_frame.pack_propagate(False)

        self.thumbnail_label = tk.Label(
            self.thumbnail_frame,
            text="🎵",
            bg="#40444b",
            fg="#72767d",
            font=("Segoe UI", 24),
            width=5,
            height=2
        )
        self.thumbnail_label.pack(fill=tk.BOTH, expand=True)

        # Info da música (lado direito)
        song_info_frame = tk.Frame(now_playing_content, bg="#36393f")
        song_info_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Indicador de canal de voz
        self.voice_channel_label = tk.Label(
            song_info_frame,
            text="🔊 Desconectado",
            bg="#36393f",
            fg="#72767d",
            font=("Segoe UI", 9)
        )
        self.voice_channel_label.pack(anchor=tk.W)

        # Label da música atual
        self.now_playing_label = tk.Label(
            song_info_frame,
            text="Nenhuma música tocando",
            bg="#36393f",
            fg="#43b581",
            font=("Segoe UI", 13, "bold"),
            wraplength=550,
            anchor=tk.W,
            justify=tk.LEFT
        )
        self.now_playing_label.pack(fill=tk.X, pady=(2, 5))

        # Frame da barra de progresso
        progress_frame = tk.Frame(song_info_frame, bg="#36393f")
        progress_frame.pack(fill=tk.X, pady=(0, 5))

        # Tempo atual
        self.time_current_label = tk.Label(
            progress_frame,
            text="0:00",
            bg="#36393f",
            fg="#b9bbbe",
            font=("Segoe UI", 9)
        )
        self.time_current_label.pack(side=tk.LEFT)

        # Barra de progresso
        self.progress_canvas = tk.Canvas(
            progress_frame,
            bg="#40444b",
            height=6,
            highlightthickness=0
        )
        self.progress_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        self.progress_bar = self.progress_canvas.create_rectangle(0, 0, 0, 6, fill="#43b581", outline="")

        # Tempo total
        self.time_total_label = tk.Label(
            progress_frame,
            text="0:00",
            bg="#36393f",
            fg="#b9bbbe",
            font=("Segoe UI", 9)
        )
        self.time_total_label.pack(side=tk.LEFT)

        # Frame dos controles (botões + volume)
        controls_container = tk.Frame(now_playing_frame, bg="#36393f")
        controls_container.pack(fill=tk.X, pady=(5, 0))

        # Frame dos botões de controle de música
        music_controls_frame = tk.Frame(controls_container, bg="#36393f")
        music_controls_frame.pack(side=tk.LEFT)

        # Botão Voltar
        self.prev_btn = tk.Button(
            music_controls_frame,
            text="⏮️",
            command=self.previous_song,
            bg="#7289da", fg="white",
            font=("Segoe UI", 12),
            relief=tk.FLAT,
            padx=12, pady=5,
            cursor="hand2",
            state=tk.DISABLED
        )
        self.prev_btn.pack(side=tk.LEFT, padx=2)

        # Botão Pausar/Retomar
        self.pause_btn = tk.Button(
            music_controls_frame,
            text="⏸️",
            command=self.toggle_pause,
            bg="#f39c12", fg="white",
            font=("Segoe UI", 12),
            relief=tk.FLAT,
            padx=12, pady=5,
            cursor="hand2",
            state=tk.DISABLED
        )
        self.pause_btn.pack(side=tk.LEFT, padx=2)

        # Botão Pular
        self.skip_btn = tk.Button(
            music_controls_frame,
            text="⏭️",
            command=self.skip_song,
            bg="#43b581", fg="white",
            font=("Segoe UI", 12),
            relief=tk.FLAT,
            padx=12, pady=5,
            cursor="hand2",
            state=tk.DISABLED
        )
        self.skip_btn.pack(side=tk.LEFT, padx=2)

        # Botão Favorito
        self.favorite_btn = tk.Button(
            music_controls_frame,
            text="☆",
            command=self.toggle_favorite,
            bg="#40444b", fg="#faa61a",
            font=("Segoe UI", 14),
            relief=tk.FLAT,
            padx=10, pady=3,
            cursor="hand2",
            state=tk.DISABLED
        )
        self.favorite_btn.pack(side=tk.LEFT, padx=(10, 2))

        # Frame do controle de volume (lado direito)
        volume_frame = tk.Frame(controls_container, bg="#36393f")
        volume_frame.pack(side=tk.RIGHT, padx=10)

        self.volume_icon_label = tk.Label(
            volume_frame,
            text="🔊",
            bg="#36393f",
            fg="#b9bbbe",
            font=("Segoe UI", 10)
        )
        self.volume_icon_label.pack(side=tk.LEFT, padx=(0, 5))

        self.volume_slider = tk.Scale(
            volume_frame,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            length=120,
            bg="#36393f",
            fg="white",
            highlightthickness=0,
            troughcolor="#40444b",
            activebackground="#43b581",
            sliderrelief=tk.FLAT,
            command=self.on_volume_change,
            showvalue=False
        )
        self.volume_slider.set(50)
        self.volume_slider.pack(side=tk.LEFT)

        self.volume_label = tk.Label(
            volume_frame,
            text="50%",
            bg="#36393f",
            fg="#b9bbbe",
            font=("Segoe UI", 9),
            width=4
        )
        self.volume_label.pack(side=tk.LEFT, padx=(5, 0))

        # Frame de adicionar música
        music_frame = tk.LabelFrame(
            main_frame, 
            text=" 🎵 Adicionar Música ", 
            bg="#36393f", 
            fg="white",
            font=("Segoe UI", 11, "bold"),
            padx=10, pady=10
        )
        music_frame.pack(fill=tk.X, pady=10)
        
        music_input_frame = tk.Frame(music_frame, bg="#36393f")
        music_input_frame.pack(fill=tk.X)
        
        # Entry para URL/busca
        self.music_entry = tk.Entry(
            music_input_frame,
            bg="#40444b",
            fg="white",
            font=("Segoe UI", 11),
            insertbackground="white",
            relief=tk.FLAT,
            width=50
        )
        self.music_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10), ipady=8)
        self.music_entry.insert(0, "Cole a URL do YouTube/Spotify ou digite o nome da música...")
        self.music_entry.bind("<FocusIn>", self.on_entry_focus_in)
        self.music_entry.bind("<FocusOut>", self.on_entry_focus_out)
        self.music_entry.bind("<Return>", lambda e: self.add_music())
        self.music_entry.config(fg="#72767d")
        
        self.add_music_btn = tk.Button(
            music_input_frame, 
            text="➕ Adicionar", 
            command=self.add_music,
            bg="#43b581", fg="white", 
            font=("Segoe UI", 11, "bold"),
            relief=tk.FLAT,
            padx=20, pady=6,
            cursor="hand2",
            state=tk.DISABLED
        )
        self.add_music_btn.pack(side=tk.RIGHT)
        
        # Lista de músicas na fila
        queue_container = tk.Frame(music_frame, bg="#36393f")
        queue_container.pack(fill=tk.X, pady=(10, 0))
        
        tk.Label(queue_container, text="📋 Fila de Reprodução:", bg="#36393f", fg="#b9bbbe", 
                 font=("Segoe UI", 9)).pack(anchor=tk.W)
        
        self.queue_listbox = tk.Listbox(
            queue_container,
            bg="#40444b",
            fg="white",
            font=("Segoe UI", 10),
            selectbackground="#7289da",
            relief=tk.FLAT,
            height=4,
            activestyle='none'
        )
        self.queue_listbox.pack(fill=tk.X, pady=5)
        
        # Botões de controle da fila
        queue_btns = tk.Frame(queue_container, bg="#36393f")
        queue_btns.pack(fill=tk.X)
        
        self.remove_btn = tk.Button(
            queue_btns,
            text="🗑 Remover",
            command=self.remove_from_queue,
            bg="#e74c3c", fg="white",
            font=("Segoe UI", 9),
            relief=tk.FLAT,
            padx=10, pady=4,
            cursor="hand2",
            state=tk.DISABLED
        )
        self.remove_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.clear_queue_btn = tk.Button(
            queue_btns,
            text="🧹 Limpar Fila",
            command=self.clear_queue,
            bg="#f39c12", fg="white",
            font=("Segoe UI", 9),
            relief=tk.FLAT,
            padx=10, pady=4,
            cursor="hand2",
            state=tk.DISABLED
        )
        self.clear_queue_btn.pack(side=tk.LEFT)
        
        # Frame de estatísticas
        stats_frame = tk.LabelFrame(
            main_frame, 
            text=" 📊 Estatísticas ", 
            bg="#36393f", 
            fg="white",
            font=("Segoe UI", 11, "bold"),
            padx=10, pady=10
        )
        stats_frame.pack(fill=tk.X, pady=10)
        
        # Grid de estatísticas
        stats_grid = tk.Frame(stats_frame, bg="#36393f")
        stats_grid.pack(fill=tk.X)
        
        # Tempo online
        self.create_stat_card(stats_grid, "⏱ Tempo Online", "time_online", "00:00:00", 0, 0)
        # Músicas tocadas
        self.create_stat_card(stats_grid, "🎵 Músicas Tocadas", "songs_played", "0", 0, 1)
        # Playlists carregadas
        self.create_stat_card(stats_grid, "📋 Playlists", "playlists_loaded", "0", 0, 2)
        # Erros
        self.create_stat_card(stats_grid, "⚠ Erros", "errors", "0", 0, 3)
        
        # Configurar colunas para expandir igualmente
        for i in range(4):
            stats_grid.columnconfigure(i, weight=1)

        # Frame de Histórico e Favoritos (abas)
        if DATABASE_AVAILABLE:
            library_frame = tk.LabelFrame(
                main_frame,
                text=" 📚 Biblioteca ",
                bg="#36393f",
                fg="white",
                font=("Segoe UI", 11, "bold"),
                padx=10, pady=10
            )
            library_frame.pack(fill=tk.X, pady=10)

            # Notebook (abas)
            self.library_notebook = ttk.Notebook(library_frame)
            self.library_notebook.pack(fill=tk.BOTH, expand=True)

            # Aba de Favoritos
            favorites_tab = tk.Frame(self.library_notebook, bg="#36393f")
            self.library_notebook.add(favorites_tab, text="⭐ Favoritos")

            # Lista de favoritos
            self.favorites_listbox = tk.Listbox(
                favorites_tab,
                bg="#40444b",
                fg="white",
                font=("Segoe UI", 10),
                selectbackground="#7289da",
                relief=tk.FLAT,
                height=5,
                activestyle='none'
            )
            self.favorites_listbox.pack(fill=tk.BOTH, expand=True, pady=(5, 5))
            self.favorites_listbox.bind("<Double-Button-1>", self.play_favorite)

            # Botões de favoritos
            fav_btns_frame = tk.Frame(favorites_tab, bg="#36393f")
            fav_btns_frame.pack(fill=tk.X)

            self.play_fav_btn = tk.Button(
                fav_btns_frame,
                text="▶ Tocar",
                command=self.play_favorite,
                bg="#43b581", fg="white",
                font=("Segoe UI", 9),
                relief=tk.FLAT,
                padx=10, pady=4,
                cursor="hand2"
            )
            self.play_fav_btn.pack(side=tk.LEFT, padx=(0, 5))

            self.remove_fav_btn = tk.Button(
                fav_btns_frame,
                text="🗑 Remover",
                command=self.remove_favorite,
                bg="#e74c3c", fg="white",
                font=("Segoe UI", 9),
                relief=tk.FLAT,
                padx=10, pady=4,
                cursor="hand2"
            )
            self.remove_fav_btn.pack(side=tk.LEFT)

            self.refresh_fav_btn = tk.Button(
                fav_btns_frame,
                text="🔄 Atualizar",
                command=self.load_favorites,
                bg="#7289da", fg="white",
                font=("Segoe UI", 9),
                relief=tk.FLAT,
                padx=10, pady=4,
                cursor="hand2"
            )
            self.refresh_fav_btn.pack(side=tk.RIGHT)

            # Aba de Histórico
            history_tab = tk.Frame(self.library_notebook, bg="#36393f")
            self.library_notebook.add(history_tab, text="📜 Histórico")

            # Busca no histórico
            history_search_frame = tk.Frame(history_tab, bg="#36393f")
            history_search_frame.pack(fill=tk.X, pady=(5, 5))

            self.history_search_entry = tk.Entry(
                history_search_frame,
                bg="#40444b",
                fg="white",
                font=("Segoe UI", 10),
                insertbackground="white",
                relief=tk.FLAT
            )
            self.history_search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5), ipady=4)
            self.history_search_entry.insert(0, "Buscar no histórico...")
            self.history_search_entry.bind("<FocusIn>", self.on_history_search_focus_in)
            self.history_search_entry.bind("<FocusOut>", self.on_history_search_focus_out)
            self.history_search_entry.bind("<Return>", lambda e: self.search_history())
            self.history_search_entry.config(fg="#72767d")

            self.search_history_btn = tk.Button(
                history_search_frame,
                text="🔍",
                command=self.search_history,
                bg="#7289da", fg="white",
                font=("Segoe UI", 10),
                relief=tk.FLAT,
                padx=8, pady=2,
                cursor="hand2"
            )
            self.search_history_btn.pack(side=tk.RIGHT)

            # Lista de histórico
            self.history_listbox = tk.Listbox(
                history_tab,
                bg="#40444b",
                fg="white",
                font=("Segoe UI", 10),
                selectbackground="#7289da",
                relief=tk.FLAT,
                height=5,
                activestyle='none'
            )
            self.history_listbox.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
            self.history_listbox.bind("<Double-Button-1>", self.play_from_history)

            # Botões do histórico
            hist_btns_frame = tk.Frame(history_tab, bg="#36393f")
            hist_btns_frame.pack(fill=tk.X)

            self.play_hist_btn = tk.Button(
                hist_btns_frame,
                text="▶ Tocar",
                command=self.play_from_history,
                bg="#43b581", fg="white",
                font=("Segoe UI", 9),
                relief=tk.FLAT,
                padx=10, pady=4,
                cursor="hand2"
            )
            self.play_hist_btn.pack(side=tk.LEFT, padx=(0, 5))

            self.add_hist_fav_btn = tk.Button(
                hist_btns_frame,
                text="⭐ Favoritar",
                command=self.add_history_to_favorites,
                bg="#faa61a", fg="white",
                font=("Segoe UI", 9),
                relief=tk.FLAT,
                padx=10, pady=4,
                cursor="hand2"
            )
            self.add_hist_fav_btn.pack(side=tk.LEFT, padx=(0, 5))

            self.clear_hist_btn = tk.Button(
                hist_btns_frame,
                text="🗑 Limpar Tudo",
                command=self.clear_history,
                bg="#e74c3c", fg="white",
                font=("Segoe UI", 9),
                relief=tk.FLAT,
                padx=10, pady=4,
                cursor="hand2"
            )
            self.clear_hist_btn.pack(side=tk.LEFT)

            self.refresh_hist_btn = tk.Button(
                hist_btns_frame,
                text="🔄 Atualizar",
                command=self.load_history,
                bg="#7289da", fg="white",
                font=("Segoe UI", 9),
                relief=tk.FLAT,
                padx=10, pady=4,
                cursor="hand2"
            )
            self.refresh_hist_btn.pack(side=tk.RIGHT)

            # Armazenar dados para referência
            self.favorites_data = []
            self.history_data = []

            # Carregar dados iniciais
            self.load_favorites()
            self.load_history()

        # Frame de log
        log_frame = tk.LabelFrame(
            main_frame, 
            text=" 📜 Log do Bot ", 
            bg="#36393f", 
            fg="white",
            font=("Segoe UI", 11, "bold"),
            padx=10, pady=10
        )
        log_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Text widget para log com scrollbar
        log_container = tk.Frame(log_frame, bg="#36393f")
        log_container.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = tk.Text(
            log_container,
            bg="#202225",
            fg="#dcddde",
            font=("Consolas", 9),
            wrap=tk.WORD,
            state=tk.DISABLED,
            relief=tk.FLAT,
            padx=10, pady=10
        )
        
        scrollbar = ttk.Scrollbar(log_container, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Tags para colorir o log
        self.log_text.tag_configure("info", foreground="#43b581")
        self.log_text.tag_configure("warning", foreground="#faa61a")
        self.log_text.tag_configure("error", foreground="#f04747")
        self.log_text.tag_configure("time", foreground="#7289da")
        
        # Footer
        footer_frame = ttk.Frame(main_frame)
        footer_frame.pack(fill=tk.X, pady=(10, 0))
        
        footer_label = ttk.Label(
            footer_frame, 
            text="Bot de Música Discord • Dashboard v1.0",
            font=("Segoe UI", 9),
            foreground="#72767d"
        )
        footer_label.pack(side=tk.LEFT)
        
        # Iniciar timer de atualização
        self.update_time()
        
    def create_stat_card(self, parent, title, key, initial_value, row, col):
        """Cria um card de estatística"""
        card = tk.Frame(parent, bg="#40444b", padx=15, pady=10)
        card.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
        
        title_lbl = tk.Label(card, text=title, bg="#40444b", fg="#b9bbbe", font=("Segoe UI", 9))
        title_lbl.pack()
        
        value_lbl = tk.Label(card, text=initial_value, bg="#40444b", fg="white", font=("Segoe UI", 16, "bold"))
        value_lbl.pack()
        
        # Salvar referência para atualização
        setattr(self, f"stat_{key}", value_lbl)
        
    def log(self, message, level="info"):
        """Adiciona mensagem ao log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{timestamp}] ", "time")
        self.log_text.insert(tk.END, f"{message}\n", level)
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)
        
        # Atualizar estatísticas baseado no log
        self.parse_log_for_stats(message)
        
    def parse_log_for_stats(self, message):
        """Analisa mensagens de log para atualizar estatísticas"""
        msg_lower = message.lower()
        
        if "tocando" in msg_lower or "playing" in msg_lower or "primeira música iniciada" in msg_lower:
            self.stats["songs_played"] += 1
            self.stat_songs_played.config(text=str(self.stats["songs_played"]))
            
        if "playlist" in msg_lower and ("carregada" in msg_lower or "extraída" in msg_lower):
            self.stats["playlists_loaded"] += 1
            self.stat_playlists_loaded.config(text=str(self.stats["playlists_loaded"]))
            
        if "erro" in msg_lower or "error" in msg_lower or "❌" in message:
            self.stats["errors"] += 1
            self.stat_errors.config(text=str(self.stats["errors"]))
        
    def clear_log(self):
        """Limpa o log"""
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state=tk.DISABLED)
    
    def on_entry_focus_in(self, event):
        """Remove placeholder ao focar"""
        if self.music_entry.get() == "Cole a URL do YouTube/Spotify ou digite o nome da música...":
            self.music_entry.delete(0, tk.END)
            self.music_entry.config(fg="white")
    
    def on_entry_focus_out(self, event):
        """Restaura placeholder se vazio"""
        if not self.music_entry.get():
            self.music_entry.insert(0, "Cole a URL do YouTube/Spotify ou digite o nome da música...")
            self.music_entry.config(fg="#72767d")
    
    def add_music(self):
        """Adiciona música à fila"""
        url = self.music_entry.get().strip()
        if not url or url == "Cole a URL do YouTube/Spotify ou digite o nome da música...":
            return
        
        if not self.bot_running:
            messagebox.showwarning("Bot Offline", "Inicie o bot primeiro antes de adicionar músicas!")
            return
        
        # Verificar se o bot está em um canal de voz (via status)
        try:
            if os.path.exists(self.status_file):
                with open(self.status_file, 'r', encoding='utf-8') as f:
                    status = json.load(f)
                # Se não há música atual e fila vazia, bot provavelmente não está em canal
        except:
            pass
        
        # Enviar comando para o bot adicionar música
        if self.send_bot_command("add_music", {"url": url}):
            # Adicionar à lista visual
            display_text = url[:60] + "..." if len(url) > 60 else url
            self.queue_listbox.insert(tk.END, f"⏳ {display_text}")
            
            self.log(f"Música enviada para reprodução: {url}", "info")
            self.log("⚠️ O bot precisa estar em um canal de voz no Discord!", "warning")
            
            # Habilitar botões
            self.remove_btn.config(state=tk.NORMAL)
            self.clear_queue_btn.config(state=tk.NORMAL)
        else:
            messagebox.showerror("Erro", "Não foi possível enviar a música para o bot.")
        
        # Limpar entrada
        self.music_entry.delete(0, tk.END)
        self.music_entry.insert(0, "Cole a URL do YouTube/Spotify ou digite o nome da música...")
        self.music_entry.config(fg="#72767d")
    
    def remove_from_queue(self):
        """Remove música selecionada da fila"""
        selection = self.queue_listbox.curselection()
        if selection:
            idx = selection[0]
            self.queue_listbox.delete(idx)
            if hasattr(self, 'pending_songs') and idx < len(self.pending_songs):
                del self.pending_songs[idx]
            self.log("Música removida da fila", "warning")
            
            if self.queue_listbox.size() == 0:
                self.remove_btn.config(state=tk.DISABLED)
                self.clear_queue_btn.config(state=tk.DISABLED)
    
    def clear_queue(self):
        """Limpa toda a fila"""
        self.queue_listbox.delete(0, tk.END)
        if hasattr(self, 'pending_songs'):
            self.pending_songs.clear()
        self.remove_btn.config(state=tk.DISABLED)
        self.clear_queue_btn.config(state=tk.DISABLED)
        self.log("Fila limpa", "warning")

    def on_volume_change(self, value):
        """Callback quando o volume é alterado"""
        vol = int(value)
        self.volume_label.config(text=f"{vol}%")
        # Atualizar ícone baseado no volume
        if vol == 0:
            self.volume_icon_label.config(text="🔇")
        elif vol < 33:
            self.volume_icon_label.config(text="🔈")
        elif vol < 66:
            self.volume_icon_label.config(text="🔉")
        else:
            self.volume_icon_label.config(text="🔊")
        # Enviar comando de volume para o bot
        if self.bot_running:
            self.send_bot_command("volume", {"value": vol / 100.0})

    def format_time(self, seconds):
        """Formata segundos em mm:ss ou hh:mm:ss"""
        if seconds <= 0:
            return "0:00"
        seconds = int(seconds)
        if seconds >= 3600:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            secs = seconds % 60
            return f"{hours}:{minutes:02d}:{secs:02d}"
        else:
            minutes = seconds // 60
            secs = seconds % 60
            return f"{minutes}:{secs:02d}"

    def update_progress(self):
        """Atualiza a barra de progresso da música"""
        if self.bot_running and self.song_start_time and self.song_duration > 0 and not self.is_paused:
            elapsed = time.time() - self.song_start_time
            if elapsed > self.song_duration:
                elapsed = self.song_duration

            # Atualizar tempo atual
            self.time_current_label.config(text=self.format_time(elapsed))

            # Atualizar barra de progresso
            self.progress_canvas.update_idletasks()
            canvas_width = self.progress_canvas.winfo_width()
            if canvas_width > 0:
                progress_width = (elapsed / self.song_duration) * canvas_width
                self.progress_canvas.coords(self.progress_bar, 0, 0, progress_width, 6)

        self.root.after(500, self.update_progress)

    def load_thumbnail(self, url):
        """Carrega thumbnail da URL em uma thread separada"""
        if not PIL_AVAILABLE or not url:
            return

        def fetch_image():
            try:
                with urllib.request.urlopen(url, timeout=5) as response:
                    image_data = response.read()
                img = Image.open(io.BytesIO(image_data))
                img = img.resize((80, 80), Image.Resampling.LANCZOS)
                self.thumbnail_image = ImageTk.PhotoImage(img)
                # Atualizar na thread principal
                self.root.after(0, lambda: self.thumbnail_label.config(
                    image=self.thumbnail_image,
                    text=""
                ))
            except Exception as e:
                print(f"Erro ao carregar thumbnail: {e}")

        thread = threading.Thread(target=fetch_image, daemon=True)
        thread.start()

    def on_server_select(self, event=None):
        """Callback quando um servidor é selecionado"""
        selected = self.server_combo.current()
        if selected >= 0 and selected < len(self.guilds):
            guild = self.guilds[selected]
            self.selected_guild_id = guild["id"]
            self.log(f"🖥️ Servidor selecionado: {guild['name']}", "info")
            # Enviar comando para mudar servidor ativo
            self.send_bot_command("select_guild", {"guild_id": guild["id"]})

    def update_server_list(self, guilds, active_guild_id):
        """Atualiza a lista de servidores no dropdown"""
        self.guilds = guilds
        server_names = []
        active_index = 0

        for i, guild in enumerate(guilds):
            status = "🔊" if guild.get("has_voice") else "🔇"
            name = f"{status} {guild['name']}"
            server_names.append(name)
            if guild["id"] == active_guild_id:
                active_index = i

        self.server_combo["values"] = server_names
        if server_names and self.server_combo.current() != active_index:
            self.server_combo.current(active_index)
            if guilds:
                self.selected_guild_id = guilds[active_index]["id"]

    # WebSocket Methods
    def connect_to_server(self):
        """Conecta a um servidor específico pelo IP"""
        global WEBSOCKET_HOST, WEBSOCKET_URI

        new_host = self.server_ip_entry.get().strip()
        if not new_host:
            messagebox.showwarning("IP inválido", "Digite o IP do servidor")
            return

        # Atualizar configuração
        WEBSOCKET_HOST = new_host
        WEBSOCKET_URI = f"ws://{WEBSOCKET_HOST}:{WEBSOCKET_PORT}"
        save_server_config(new_host)

        self.log(f"🌐 Conectando a {WEBSOCKET_URI}...", "info")

        # Reiniciar conexão WebSocket
        self.websocket_connected = False
        if self.websocket:
            try:
                asyncio.run_coroutine_threadsafe(self.websocket.close(), self.websocket_loop)
            except:
                pass
        self.start_websocket()

    def start_websocket(self):
        """Inicia a conexão WebSocket em uma thread separada"""
        if not WEBSOCKET_AVAILABLE:
            return

        def run_websocket():
            self.websocket_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.websocket_loop)
            try:
                self.websocket_loop.run_until_complete(self.websocket_connect())
            except Exception as e:
                print(f"Erro no WebSocket: {e}")

        self.websocket_thread = threading.Thread(target=run_websocket, daemon=True)
        self.websocket_thread.start()

    async def websocket_connect(self):
        """Conecta ao servidor WebSocket"""
        retry_delay = 1
        max_retries = 5
        retries = 0

        while True:
            try:
                self.root.after(0, lambda: self.connect_btn.config(text="Conectando...", state=tk.DISABLED))
                async with websockets.connect(WEBSOCKET_URI) as ws:
                    self.websocket = ws
                    self.websocket_connected = True
                    self.root.after(0, lambda: self.connect_btn.config(text="Conectado ✓", bg="#43b581", state=tk.NORMAL))
                    self.root.after(0, lambda: self.log(f"🔌 WebSocket conectado a {WEBSOCKET_HOST}!", "info"))
                    retry_delay = 1
                    retries = 0

                    async for message in ws:
                        try:
                            data = json.loads(message)
                            # Colocar na fila para processar na thread principal
                            self.message_queue.put(data)
                            self.root.after(0, self.process_websocket_message)
                        except json.JSONDecodeError:
                            pass

            except Exception as e:
                self.websocket_connected = False
                self.websocket = None
                self.root.after(0, lambda: self.connect_btn.config(text="Conectar", bg="#7289da", state=tk.NORMAL))
                self.root.after(0, lambda: self.host_label.config(text=""))
                self.root.after(0, lambda: self.users_label.config(text="👥 0 conectados"))

                retries += 1
                if retries <= max_retries:
                    self.root.after(0, lambda r=retries: self.log(f"⚠️ Tentando reconectar ({r}/{max_retries})...", "warning"))
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 10)
                else:
                    self.root.after(0, lambda: self.log("❌ Não foi possível conectar ao servidor", "error"))
                    break

    def process_websocket_message(self):
        """Processa mensagens do WebSocket na thread principal"""
        try:
            while not self.message_queue.empty():
                data = self.message_queue.get_nowait()
                msg_type = data.get("type")

                if msg_type == "welcome":
                    # Mensagem de boas-vindas com ID do cliente
                    self.client_id = data.get("client_id")
                    self.is_host = data.get("is_host", False)
                    self.connected_users = data.get("users", [])
                    self.update_users_display()
                    host_text = "👑 Você é o HOST" if self.is_host else ""
                    self.log(f"🔌 Conectado ao servidor (ID: {self.client_id}) {host_text}", "info")
                    # Enviar nome do usuário
                    self.send_websocket_command("set_name", {"name": self.user_name})

                elif msg_type == "users_update":
                    # Atualização da lista de usuários
                    self.connected_users = data.get("users", [])
                    self.update_users_display()

                elif msg_type == "response":
                    # Resposta a um comando
                    pass

                else:
                    # Status update (música, fila, etc)
                    self.handle_status_update(data)
        except queue.Empty:
            pass

    def update_users_display(self):
        """Atualiza o display de usuários conectados"""
        total = len(self.connected_users)
        self.users_label.config(text=f"👥 {total} conectado{'s' if total != 1 else ''}")

        # Encontrar o host
        host_name = None
        for user in self.connected_users:
            if user.get("is_host"):
                host_name = user.get("name", "Desconhecido")
                if user.get("id") == self.client_id:
                    self.is_host = True
                    self.host_label.config(text="👑 Você é o HOST", fg="#faa61a")
                else:
                    self.is_host = False
                    self.host_label.config(text=f"👑 Host: {host_name}", fg="#43b581")
                break

        if not host_name:
            self.host_label.config(text="")

    def handle_status_update(self, status):
        """Processa atualização de status recebida via WebSocket"""
        # Atualizar lista de usuários se incluída
        if "users" in status:
            self.connected_users = status["users"]
            self.update_users_display()

        # Atualizar lista de servidores
        if "guilds" in status:
            self.update_server_list(status["guilds"], status.get("active_guild_id"))

        # Atualizar música atual
        if "current_song" in status:
            new_song = status["current_song"]
            if new_song != self.current_song:
                self.current_song = new_song
                if new_song:
                    self.now_playing_label.config(text=new_song, fg="#43b581")
                else:
                    self.now_playing_label.config(text="Nenhuma música tocando", fg="#72767d")
                    self.time_current_label.config(text="0:00")
                    self.time_total_label.config(text="0:00")
                    self.progress_canvas.coords(self.progress_bar, 0, 0, 0, 6)
                    self.current_song_url = None

        # Atualizar URL da música atual
        if "current_song_url" in status:
            self.current_song_url = status["current_song_url"]
            self.update_favorite_button()

        # Atualizar duração
        if "duration" in status:
            self.song_duration = status["duration"] or 0
            self.time_total_label.config(text=self.format_time(self.song_duration))

        if "start_time" in status:
            self.song_start_time = status["start_time"]

        # Atualizar thumbnail
        if "thumbnail" in status:
            new_thumbnail = status["thumbnail"]
            if new_thumbnail and new_thumbnail != self.current_thumbnail_url:
                self.current_thumbnail_url = new_thumbnail
                self.load_thumbnail(new_thumbnail)
            elif not new_thumbnail:
                self.current_thumbnail_url = None
                self.thumbnail_label.config(image="", text="🎵")

        # Atualizar canal de voz
        if "voice_channel" in status:
            channel = status["voice_channel"]
            if channel:
                self.voice_channel_label.config(text=f"🔊 {channel}", fg="#43b581")
            else:
                self.voice_channel_label.config(text="🔊 Desconectado", fg="#72767d")

        # Atualizar estado de pausa
        if "is_paused" in status:
            self.is_paused = status["is_paused"]
            self.pause_btn.config(text="▶️" if self.is_paused else "⏸️")

        # Atualizar fila
        if "queue" in status:
            self.queue_listbox.delete(0, tk.END)
            if status["queue"]:
                for song in status["queue"][:10]:
                    self.queue_listbox.insert(tk.END, f"🎵 {song}")
                self.remove_btn.config(state=tk.NORMAL)
                self.clear_queue_btn.config(state=tk.NORMAL)
            else:
                self.remove_btn.config(state=tk.DISABLED)
                self.clear_queue_btn.config(state=tk.DISABLED)

        # Atualizar contador
        if "songs_played" in status:
            self.stats["songs_played"] = status["songs_played"]
            self.stat_songs_played.config(text=str(status["songs_played"]))

    def send_websocket_command(self, command, data=None):
        """Envia comando via WebSocket"""
        if not self.websocket_connected or not self.websocket:
            return False

        cmd = {"command": command, "data": data or {}}
        if self.selected_guild_id:
            cmd["data"]["guild_id"] = self.selected_guild_id

        try:
            asyncio.run_coroutine_threadsafe(
                self.websocket.send(json.dumps(cmd)),
                self.websocket_loop
            )
            return True
        except Exception as e:
            print(f"Erro ao enviar WebSocket: {e}")
            return False

    def send_bot_command(self, command, data=None):
        """Envia comando para o bot (WebSocket ou fallback JSON)"""
        # Tentar WebSocket primeiro
        if self.websocket_connected and self.send_websocket_command(command, data):
            return True

        # Fallback para arquivo JSON
        try:
            cmd = {"command": command, "timestamp": datetime.now().isoformat()}
            if data:
                cmd["data"] = data
            else:
                cmd["data"] = {}

            # Incluir guild_id selecionado
            if self.selected_guild_id:
                cmd["data"]["guild_id"] = self.selected_guild_id

            # Log do caminho do arquivo
            self.log(f"Salvando comando em: {self.command_file}", "info")
            
            with open(self.command_file, 'w', encoding='utf-8') as f:
                json.dump(cmd, f)
            
            # Verificar se arquivo foi criado
            if os.path.exists(self.command_file):
                self.log(f"✅ Arquivo de comando criado com sucesso", "info")
            else:
                self.log(f"❌ Arquivo não foi criado!", "error")
                
            return True
        except Exception as e:
            self.log(f"Erro ao enviar comando: {e}", "error")
            import traceback
            traceback.print_exc()
            return False
    
    def skip_song(self):
        """Pula a música atual"""
        if self.bot_running:
            self.send_bot_command("skip")
            self.log("⏭️ Pulando música...", "info")
    
    def toggle_pause(self):
        """Pausa ou retoma a música"""
        if self.bot_running:
            if self.is_paused:
                self.send_bot_command("resume")
                self.pause_btn.config(text="⏸️")
                self.is_paused = False
                self.log("▶️ Música retomada", "info")
            else:
                self.send_bot_command("pause")
                self.pause_btn.config(text="▶️")
                self.is_paused = True
                self.log("⏸️ Música pausada", "info")
    
    def previous_song(self):
        """Volta para música anterior"""
        if self.bot_running:
            self.send_bot_command("previous")
            self.log("⏮️ Voltando música...", "info")
    
    def check_bot_status(self):
        """Verifica status do bot via arquivo (fallback quando WebSocket não conectado)"""
        # Se WebSocket conectado, não precisa polling
        if self.websocket_connected:
            self.root.after(2000, self.check_bot_status)
            return

        try:
            if os.path.exists(self.status_file):
                with open(self.status_file, 'r', encoding='utf-8') as f:
                    status = json.load(f)

                # Atualizar lista de servidores
                if "guilds" in status:
                    self.update_server_list(status["guilds"], status.get("active_guild_id"))

                # Atualizar música atual
                if "current_song" in status:
                    new_song = status["current_song"]
                    if new_song != self.current_song:
                        self.current_song = new_song
                        if new_song:
                            self.now_playing_label.config(text=new_song, fg="#43b581")
                        else:
                            self.now_playing_label.config(text="Nenhuma música tocando", fg="#72767d")
                            # Resetar progresso
                            self.time_current_label.config(text="0:00")
                            self.time_total_label.config(text="0:00")
                            self.progress_canvas.coords(self.progress_bar, 0, 0, 0, 6)
                            self.current_song_url = None

                # Atualizar URL da música atual
                if "current_song_url" in status:
                    self.current_song_url = status["current_song_url"]
                    self.update_favorite_button()

                # Atualizar duração e tempo de início
                if "duration" in status:
                    self.song_duration = status["duration"] or 0
                    self.time_total_label.config(text=self.format_time(self.song_duration))

                if "start_time" in status:
                    self.song_start_time = status["start_time"]

                # Atualizar thumbnail
                if "thumbnail" in status:
                    new_thumbnail = status["thumbnail"]
                    if new_thumbnail and new_thumbnail != self.current_thumbnail_url:
                        self.current_thumbnail_url = new_thumbnail
                        self.load_thumbnail(new_thumbnail)
                    elif not new_thumbnail:
                        self.current_thumbnail_url = None
                        self.thumbnail_label.config(image="", text="🎵")

                # Atualizar canal de voz
                if "voice_channel" in status:
                    channel = status["voice_channel"]
                    if channel:
                        self.voice_channel_label.config(text=f"🔊 {channel}", fg="#43b581")
                    else:
                        self.voice_channel_label.config(text="🔊 Desconectado", fg="#72767d")

                # Atualizar estado de pausa
                if "is_paused" in status:
                    self.is_paused = status["is_paused"]
                    if self.is_paused:
                        self.pause_btn.config(text="▶️")
                    else:
                        self.pause_btn.config(text="⏸️")

                # Atualizar fila
                if "queue" in status:
                    self.queue_listbox.delete(0, tk.END)
                    if status["queue"]:
                        for song in status["queue"][:10]:
                            self.queue_listbox.insert(tk.END, f"🎵 {song}")
                        self.remove_btn.config(state=tk.NORMAL)
                        self.clear_queue_btn.config(state=tk.NORMAL)
                    else:
                        self.remove_btn.config(state=tk.DISABLED)
                        self.clear_queue_btn.config(state=tk.DISABLED)

                # Atualizar contador de músicas tocadas
                if "songs_played" in status:
                    self.stats["songs_played"] = status["songs_played"]
                    self.stat_songs_played.config(text=str(status["songs_played"]))
        except:
            pass

        self.root.after(1000, self.check_bot_status)
        
    def update_time(self):
        """Atualiza o tempo online"""
        if self.bot_running and self.stats["start_time"]:
            elapsed = datetime.now() - self.stats["start_time"]
            hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            self.stat_time_online.config(text=f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        
        self.root.after(1000, self.update_time)
        
    def start_bot(self):
        """Inicia o bot em uma thread separada"""
        if self.bot_running:
            return
            
        self.log("Iniciando bot...", "info")
        
        # Reset estatísticas
        self.stats["start_time"] = datetime.now()
        self.stats["commands_executed"] = 0
        self.stats["songs_played"] = 0
        self.stats["playlists_loaded"] = 0
        self.stats["errors"] = 0
        
        self.stat_songs_played.config(text="0")
        self.stat_playlists_loaded.config(text="0")
        self.stat_errors.config(text="0")
        
        # Iniciar processo do bot
        def run_bot():
            try:
                # Encontrar bot.py
                script_dir = os.path.dirname(os.path.abspath(__file__))
                bot_path = os.path.join(script_dir, "bot.py")
                
                if not os.path.exists(bot_path):
                    self.output_queue.put(("error", "bot.py não encontrado!"))
                    return
                
                self.output_queue.put(("log", f"Iniciando bot..."))
                
                # Iniciar processo SEM flags especiais
                self.bot_process = subprocess.Popen(
                    [sys.executable, bot_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=script_dir,
                    encoding='utf-8',
                    errors='replace'
                )
                
                self.bot_running = True
                self.output_queue.put(("status", "running"))

                # Aguardar um pouco e iniciar WebSocket
                time.sleep(2)
                self.root.after(0, self.start_websocket)

                # Ler stdout em thread separada
                def read_stdout():
                    try:
                        while self.bot_process and self.bot_process.poll() is None:
                            line = self.bot_process.stdout.readline()
                            if line:
                                self.output_queue.put(("log", line.strip()))
                    except:
                        pass
                
                # Ler stderr em thread separada
                def read_stderr():
                    try:
                        while self.bot_process and self.bot_process.poll() is None:
                            line = self.bot_process.stderr.readline()
                            if line:
                                self.output_queue.put(("log", line.strip()))
                    except:
                        pass
                
                stdout_thread = threading.Thread(target=read_stdout, daemon=True)
                stderr_thread = threading.Thread(target=read_stderr, daemon=True)
                stdout_thread.start()
                stderr_thread.start()
                
                # Aguardar processo terminar
                self.bot_process.wait()
                
            except Exception as e:
                self.output_queue.put(("error", str(e)))
            finally:
                self.output_queue.put(("status", "stopped"))
                self.bot_running = False
                
        thread = threading.Thread(target=run_bot, daemon=True)
        thread.start()
        
    def stop_bot(self):
        """Para o bot"""
        if self.bot_process and self.bot_running:
            self.log("Parando bot...", "warning")
            try:
                self.bot_process.terminate()
                self.bot_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.bot_process.kill()
            except Exception as e:
                self.log(f"Erro ao parar bot: {e}", "error")
            
            self.bot_running = False
            self.update_ui_state(False)
            self.log("Bot parado.", "warning")
            
    def check_output_queue(self):
        """Verifica a fila de output periodicamente"""
        try:
            while True:
                msg_type, message = self.output_queue.get_nowait()
                
                if msg_type == "log":
                    level = "info"
                    if "erro" in message.lower() or "error" in message.lower() or "❌" in message:
                        level = "error"
                    elif "⚠" in message or "warning" in message.lower():
                        level = "warning"
                    self.log(message, level)
                    
                elif msg_type == "status":
                    if message == "running":
                        self.update_ui_state(True)
                        self.log("✅ Bot iniciado com sucesso!", "info")
                    elif message == "stopped":
                        self.update_ui_state(False)
                        
                elif msg_type == "error":
                    self.log(f"❌ Erro: {message}", "error")
                    
        except queue.Empty:
            pass
            
        self.root.after(100, self.check_output_queue)
        
    def update_ui_state(self, running):
        """Atualiza o estado da UI baseado no status do bot"""
        if running:
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            self.add_music_btn.config(state=tk.NORMAL)
            self.skip_btn.config(state=tk.NORMAL)
            self.pause_btn.config(state=tk.NORMAL)
            self.prev_btn.config(state=tk.NORMAL)
            self.favorite_btn.config(state=tk.NORMAL)
            self.status_dot.itemconfig(self.status_indicator, fill="#43b581")
            self.status_label.config(text="Online")
        else:
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
            self.add_music_btn.config(state=tk.DISABLED)
            self.skip_btn.config(state=tk.DISABLED)
            self.pause_btn.config(state=tk.DISABLED)
            self.prev_btn.config(state=tk.DISABLED)
            self.favorite_btn.config(state=tk.DISABLED)
            self.status_dot.itemconfig(self.status_indicator, fill="#e74c3c")
            self.status_label.config(text="Desligado")
            self.stat_time_online.config(text="00:00:00")
            self.stats["start_time"] = None
            self.now_playing_label.config(text="Nenhuma música tocando")
            self.current_song = "Nenhuma música tocando"
            # Limpar arquivos de status
            try:
                if os.path.exists(self.status_file):
                    os.remove(self.status_file)
                if os.path.exists(self.command_file):
                    os.remove(self.command_file)
            except:
                pass

    # === MÉTODOS DE FAVORITOS E HISTÓRICO ===

    def toggle_favorite(self):
        """Adiciona ou remove a música atual dos favoritos"""
        if not DATABASE_AVAILABLE or not db:
            messagebox.showwarning("Indisponível", "Banco de dados não disponível")
            return

        if not self.current_song_url:
            messagebox.showinfo("Sem música", "Nenhuma música tocando para favoritar")
            return

        if db.is_favorite(self.current_song_url):
            # Remover dos favoritos
            db.remove_favorite(self.current_song_url)
            self.favorite_btn.config(text="☆")
            self.log(f"⭐ Removido dos favoritos: {self.current_song}", "info")
        else:
            # Adicionar aos favoritos
            db.add_favorite(
                title=self.current_song,
                url=self.current_song_url,
                thumbnail=self.current_thumbnail_url,
                duration=self.song_duration
            )
            self.favorite_btn.config(text="★")
            self.log(f"⭐ Adicionado aos favoritos: {self.current_song}", "info")

        # Atualizar lista de favoritos
        if hasattr(self, 'favorites_listbox'):
            self.load_favorites()

    def update_favorite_button(self):
        """Atualiza o estado do botão de favorito baseado na música atual"""
        if not DATABASE_AVAILABLE or not db:
            return

        if self.current_song_url and db.is_favorite(self.current_song_url):
            self.favorite_btn.config(text="★")
        else:
            self.favorite_btn.config(text="☆")

    def load_favorites(self):
        """Carrega a lista de favoritos do banco de dados"""
        if not DATABASE_AVAILABLE or not db:
            return

        self.favorites_data = db.get_favorites(limit=50)
        self.favorites_listbox.delete(0, tk.END)

        for fav in self.favorites_data:
            duration_str = self.format_time(fav.get('duration', 0))
            title = fav.get('title', 'Sem título')
            self.favorites_listbox.insert(tk.END, f"⭐ {title} [{duration_str}]")

        if not self.favorites_data:
            self.favorites_listbox.insert(tk.END, "Nenhum favorito ainda...")

    def play_favorite(self, event=None):
        """Toca a música favorita selecionada"""
        if not hasattr(self, 'favorites_listbox'):
            return

        selection = self.favorites_listbox.curselection()
        if not selection:
            return

        idx = selection[0]
        if idx < len(self.favorites_data):
            fav = self.favorites_data[idx]
            url = fav.get('url')
            if url and self.bot_running:
                self.send_bot_command("add_music", {"url": url})
                self.log(f"▶ Tocando favorito: {fav.get('title')}", "info")
            elif not self.bot_running:
                messagebox.showwarning("Bot Offline", "Inicie o bot primeiro!")

    def remove_favorite(self):
        """Remove o favorito selecionado"""
        if not DATABASE_AVAILABLE or not db:
            return

        selection = self.favorites_listbox.curselection()
        if not selection:
            return

        idx = selection[0]
        if idx < len(self.favorites_data):
            fav = self.favorites_data[idx]
            url = fav.get('url')
            if url:
                db.remove_favorite(url)
                self.log(f"🗑 Favorito removido: {fav.get('title')}", "warning")
                self.load_favorites()
                self.update_favorite_button()

    def load_history(self):
        """Carrega o histórico do banco de dados"""
        if not DATABASE_AVAILABLE or not db:
            return

        self.history_data = db.get_history(limit=50)
        self.history_listbox.delete(0, tk.END)

        for item in self.history_data:
            title = item.get('title', 'Sem título')
            played_at = item.get('played_at', '')
            if played_at:
                try:
                    dt = datetime.fromisoformat(played_at)
                    time_str = dt.strftime("%d/%m %H:%M")
                except:
                    time_str = ""
            else:
                time_str = ""
            self.history_listbox.insert(tk.END, f"🎵 {title} ({time_str})")

        if not self.history_data:
            self.history_listbox.insert(tk.END, "Histórico vazio...")

    def search_history(self):
        """Busca no histórico"""
        if not DATABASE_AVAILABLE or not db:
            return

        query = self.history_search_entry.get().strip()
        if not query or query == "Buscar no histórico...":
            self.load_history()
            return

        self.history_data = db.search_history(query, limit=50)
        self.history_listbox.delete(0, tk.END)

        for item in self.history_data:
            title = item.get('title', 'Sem título')
            self.history_listbox.insert(tk.END, f"🎵 {title}")

        if not self.history_data:
            self.history_listbox.insert(tk.END, f"Nenhum resultado para '{query}'")

    def on_history_search_focus_in(self, event):
        """Remove placeholder ao focar na busca do histórico"""
        if self.history_search_entry.get() == "Buscar no histórico...":
            self.history_search_entry.delete(0, tk.END)
            self.history_search_entry.config(fg="white")

    def on_history_search_focus_out(self, event):
        """Restaura placeholder se vazio"""
        if not self.history_search_entry.get():
            self.history_search_entry.insert(0, "Buscar no histórico...")
            self.history_search_entry.config(fg="#72767d")

    def play_from_history(self, event=None):
        """Toca uma música do histórico"""
        if not hasattr(self, 'history_listbox'):
            return

        selection = self.history_listbox.curselection()
        if not selection:
            return

        idx = selection[0]
        if idx < len(self.history_data):
            item = self.history_data[idx]
            url = item.get('url')
            if url and self.bot_running:
                self.send_bot_command("add_music", {"url": url})
                self.log(f"▶ Tocando do histórico: {item.get('title')}", "info")
            elif not self.bot_running:
                messagebox.showwarning("Bot Offline", "Inicie o bot primeiro!")
            elif not url:
                messagebox.showinfo("URL indisponível", "Esta música não possui URL salva")

    def add_history_to_favorites(self):
        """Adiciona a música do histórico selecionada aos favoritos"""
        if not DATABASE_AVAILABLE or not db:
            return

        selection = self.history_listbox.curselection()
        if not selection:
            return

        idx = selection[0]
        if idx < len(self.history_data):
            item = self.history_data[idx]
            url = item.get('url')
            if url:
                db.add_favorite(
                    title=item.get('title', 'Sem título'),
                    url=url,
                    thumbnail=item.get('thumbnail'),
                    duration=item.get('duration', 0)
                )
                self.log(f"⭐ Adicionado aos favoritos: {item.get('title')}", "info")
                self.load_favorites()
            else:
                messagebox.showinfo("URL indisponível", "Esta música não possui URL salva")

    def clear_history(self):
        """Limpa todo o histórico"""
        if not DATABASE_AVAILABLE or not db:
            return

        if messagebox.askyesno("Confirmar", "Deseja realmente limpar todo o histórico?"):
            db.clear_history()
            self.load_history()
            self.log("🗑 Histórico limpo", "warning")


def main():
    root = tk.Tk()
    
    # Ícone (se disponível)
    try:
        root.iconbitmap("icon.ico")
    except:
        pass
    
    # Centralizar janela
    root.update_idletasks()
    width = 900
    height = 900
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f"{width}x{height}+{x}+{y}")
    
    # Configurar fechamento
    app = BotDashboard(root)
    
    def on_closing():
        if app.bot_running:
            if messagebox.askokcancel("Fechar", "O bot está rodando. Deseja parar o bot e fechar?"):
                app.stop_bot()
                root.destroy()
        else:
            root.destroy()
            
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
