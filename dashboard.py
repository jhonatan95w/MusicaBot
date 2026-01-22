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
from datetime import datetime

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
        self.is_paused = False
        
        # Arquivo de comunicação com o bot
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.status_file = os.path.join(self.script_dir, ".bot_status.json")
        self.command_file = os.path.join(self.script_dir, ".bot_command.json")
        
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
        
        # Status indicator
        self.status_frame = tk.Frame(header_frame, bg="#2f3136")
        self.status_frame.pack(side=tk.RIGHT)
        
        self.status_dot = tk.Canvas(self.status_frame, width=15, height=15, bg="#2f3136", highlightthickness=0)
        self.status_dot.pack(side=tk.LEFT, padx=5)
        self.status_indicator = self.status_dot.create_oval(2, 2, 13, 13, fill="#e74c3c", outline="")
        
        self.status_label = ttk.Label(self.status_frame, text="Desligado", style="Stats.TLabel")
        self.status_label.pack(side=tk.LEFT)
        
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
        
        # Label da música atual
        self.now_playing_label = tk.Label(
            now_playing_frame,
            text="Nenhuma música tocando",
            bg="#36393f",
            fg="#43b581",
            font=("Segoe UI", 14, "bold"),
            wraplength=700
        )
        self.now_playing_label.pack(fill=tk.X, pady=5)
        
        # Frame dos botões de controle de música
        music_controls_frame = tk.Frame(now_playing_frame, bg="#36393f")
        music_controls_frame.pack(pady=10)
        
        # Botão Voltar
        self.prev_btn = tk.Button(
            music_controls_frame, 
            text="⏮️ Voltar", 
            command=self.previous_song,
            bg="#7289da", fg="white", 
            font=("Segoe UI", 11, "bold"),
            relief=tk.FLAT,
            padx=15, pady=8,
            cursor="hand2",
            state=tk.DISABLED
        )
        self.prev_btn.pack(side=tk.LEFT, padx=5)
        
        # Botão Pausar/Retomar
        self.pause_btn = tk.Button(
            music_controls_frame, 
            text="⏸️ Pausar", 
            command=self.toggle_pause,
            bg="#f39c12", fg="white", 
            font=("Segoe UI", 11, "bold"),
            relief=tk.FLAT,
            padx=15, pady=8,
            cursor="hand2",
            state=tk.DISABLED
        )
        self.pause_btn.pack(side=tk.LEFT, padx=5)
        
        # Botão Pular
        self.skip_btn = tk.Button(
            music_controls_frame, 
            text="⏭️ Pular", 
            command=self.skip_song,
            bg="#43b581", fg="white", 
            font=("Segoe UI", 11, "bold"),
            relief=tk.FLAT,
            padx=15, pady=8,
            cursor="hand2",
            state=tk.DISABLED
        )
        self.skip_btn.pack(side=tk.LEFT, padx=5)
        
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
    
    def send_bot_command(self, command, data=None):
        """Envia comando para o bot via arquivo"""
        try:
            cmd = {"command": command, "timestamp": datetime.now().isoformat()}
            if data:
                cmd["data"] = data
            
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
                self.pause_btn.config(text="⏸️ Pausar")
                self.is_paused = False
                self.log("▶️ Música retomada", "info")
            else:
                self.send_bot_command("pause")
                self.pause_btn.config(text="▶️ Retomar")
                self.is_paused = True
                self.log("⏸️ Música pausada", "info")
    
    def previous_song(self):
        """Volta para música anterior"""
        if self.bot_running:
            self.send_bot_command("previous")
            self.log("⏮️ Voltando música...", "info")
    
    def check_bot_status(self):
        """Verifica status do bot via arquivo"""
        try:
            if os.path.exists(self.status_file):
                with open(self.status_file, 'r', encoding='utf-8') as f:
                    status = json.load(f)
                
                # Atualizar música atual
                if "current_song" in status:
                    new_song = status["current_song"]
                    if new_song != self.current_song:
                        self.current_song = new_song
                        if new_song:
                            self.now_playing_label.config(text=new_song, fg="#43b581")
                        else:
                            self.now_playing_label.config(text="Nenhuma música tocando", fg="#72767d")
                
                # Atualizar estado de pausa
                if "is_paused" in status:
                    self.is_paused = status["is_paused"]
                    if self.is_paused:
                        self.pause_btn.config(text="▶️ Retomar")
                    else:
                        self.pause_btn.config(text="⏸️ Pausar")
                
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
            self.status_dot.itemconfig(self.status_indicator, fill="#43b581")
            self.status_label.config(text="Online")
        else:
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
            self.add_music_btn.config(state=tk.DISABLED)
            self.skip_btn.config(state=tk.DISABLED)
            self.pause_btn.config(state=tk.DISABLED)
            self.prev_btn.config(state=tk.DISABLED)
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
