# Bot de Musica para Discord

Bot de musica para Discord com dashboard desktop, suporte a YouTube/Spotify e sistema multi-usuario.

## Indice

- [Caracteristicas](#caracteristicas)
- [Pre-requisitos](#pre-requisitos)
- [Instalacao](#instalacao)
- [Configuracao](#configuracao)
- [Uso](#uso)
- [Dashboard](#dashboard)
- [Multi-Usuario](#multi-usuario)
- [Comandos](#comandos)
- [Estrutura do Projeto](#estrutura-do-projeto)
- [Solucao de Problemas](#solucao-de-problemas)

## Caracteristicas

### Bot Discord
- Tocar musicas do **YouTube** (URL ou busca)
- Suporte completo a **Spotify** (tracks, playlists, albuns)
- **Fila de reproducao** com navegacao (proxima/anterior)
- **Comandos slash** (`/play`, `/skip`, `/pause`, etc)
- **Botoes interativos** nas mensagens do Discord
- Ajuste de **volume**
- Suporte a **multiplos servidores**

### Dashboard Desktop
- Interface grafica em **Tkinter**
- **Thumbnail** da musica atual
- **Barra de progresso** com tempo atual/total
- **Controle de volume** visual
- Visualizacao da **fila de reproducao**
- Selecao de **servidor Discord**
- **Historico** de musicas tocadas (SQLite)
- Sistema de **favoritos**
- **Busca** no historico

### Sistema Multi-Usuario
- Multiplas pessoas podem usar o dashboard **simultaneamente**
- Sistema de **Host** (primeiro a conectar)
- Visualizacao de **usuarios conectados**
- **Sincronizacao em tempo real** via WebSocket
- Conexao via **IP da rede local**

## Pre-requisitos

- **Python 3.10+** - [Download](https://www.python.org/downloads/)
- **FFmpeg** - Necessario para processar audio
  - Windows: [Download](https://ffmpeg.org/download.html) e adicione ao PATH
  - Linux: `sudo apt install ffmpeg`
  - macOS: `brew install ffmpeg`

## Instalacao

### 1. Clone o repositorio

```bash
git clone https://github.com/jhonatan95w/MusicaBot.git
cd MusicaBot
```

### 2. Instale as dependencias

```bash
pip install -r requirements.txt
```

### 3. Configure o arquivo `.env`

Crie um arquivo `.env` na pasta do projeto:

```env
DISCORD_TOKEN=seu_token_do_discord

# Opcional - para playlists do Spotify
SPOTIFY_CLIENT_ID=seu_client_id
SPOTIFY_CLIENT_SECRET=seu_client_secret
```

## Configuracao

### Criar o Bot no Discord

1. Acesse o [Discord Developer Portal](https://discord.com/developers/applications)
2. Clique em **"New Application"**
3. Va para a aba **"Bot"** no menu lateral
4. Clique em **"Reset Token"** e copie o token
5. Ative os **Privileged Gateway Intents**:
   - Message Content Intent
   - Server Members Intent
6. Va para **OAuth2** > **URL Generator**
7. Selecione: `bot` e `applications.commands`
8. Permissoes: Connect, Speak, Send Messages, Embed Links
9. Use a URL gerada para convidar o bot

### Configurar Spotify (Opcional)

1. Acesse [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Crie um novo App
3. Copie o Client ID e Client Secret para o `.env`

## Uso

### Iniciar pelo Dashboard

```bash
python dashboard.py
```

Ou use o arquivo `iniciar.bat` (Windows)

### Iniciar apenas o Bot

```bash
python bot.py
```

## Dashboard

O dashboard oferece controle visual completo do bot:

### Painel Principal
- **Iniciar/Parar Bot** - Controle do processo do bot
- **Seletor de Servidor** - Escolha qual servidor controlar
- **Status de Conexao** - Indica se o bot esta online

### Tocando Agora
- **Thumbnail** da musica atual
- **Nome da musica**
- **Barra de progresso** com tempo
- **Canal de voz** conectado
- **Botao de favorito** - Salva a musica atual

### Controles
- **Anterior** - Volta para musica anterior
- **Pausar/Retomar** - Pausa ou continua
- **Proxima** - Pula para proxima
- **Volume** - Slider de 0 a 100%

### Adicionar Musica
- Cole URL do YouTube/Spotify
- Ou digite o nome da musica para buscar
- Visualize a fila de reproducao

### Biblioteca
- **Aba Favoritos** - Musicas salvas
- **Aba Historico** - Musicas tocadas recentemente
- Busca no historico
- Toque direto da lista

## Multi-Usuario

Multiplas pessoas podem controlar o bot de maquinas diferentes.

### Maquina Host (roda o bot)

1. Inicie o dashboard normalmente
2. Clique em "Iniciar Bot"
3. O console mostrara o IP:
   ```
   Servidor WebSocket iniciado!
   Local: ws://localhost:8765
   Rede:  ws://192.168.1.100:8765
   ```
4. Compartilhe o IP da rede com outros usuarios

### Outras Maquinas

1. Abra o dashboard
2. No campo **"IP do Servidor"**, digite o IP do Host (ex: `192.168.1.100`)
3. Clique em **"Conectar"**
4. Pronto! Voce vera o mesmo que o Host

### Comportamento
- **Todos podem** adicionar musicas, pausar, pular, etc
- **Host** = primeiro a conectar (indicador visual)
- Se o Host desconectar, o proximo vira Host
- Sincronizacao em tempo real

## Comandos

### Comandos Slash (/)

| Comando | Descricao |
|---------|-----------|
| `/play <url/nome>` | Toca musica ou adiciona a fila |
| `/skip` | Pula para proxima musica |
| `/pause` | Pausa a reproducao |
| `/resume` | Retoma a reproducao |
| `/previous` | Volta para musica anterior |
| `/queue` | Mostra a fila |
| `/volume <0-100>` | Ajusta o volume |
| `/leave` | Desconecta do canal de voz |

### Exemplos

```
/play https://www.youtube.com/watch?v=dQw4w9WgXcQ
/play never gonna give you up
/play https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT
/play https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M
/volume 50
/skip
```

## Estrutura do Projeto

```
MusicaBot/
├── bot.py                    # Bot principal do Discord
├── dashboard.py              # Interface grafica Tkinter
├── database.py               # Banco de dados SQLite
├── requirements.txt          # Dependencias Python
├── .env                      # Configuracoes (nao commitado)
├── .gitignore                # Arquivos ignorados
├── discord_bot_readme.md     # Este arquivo
├── iniciar.bat               # Script para iniciar (Windows)
└── music_bot.db              # Banco de dados (criado automaticamente)
```

## Dependencias

```
discord.py[voice]    # API do Discord com suporte a voz
yt-dlp               # Download de audio do YouTube
PyNaCl               # Criptografia para voz
spotipy              # API do Spotify
python-dotenv        # Variaveis de ambiente
Pillow               # Processamento de imagens
websockets           # Comunicacao em tempo real
```

## Solucao de Problemas

### Bot nao toca musica

- Verifique se o FFmpeg esta instalado: `ffmpeg -version`
- Confirme permissoes "Connect" e "Speak" no servidor
- Verifique os logs no terminal

### Erro "ffmpeg was not found"

- Windows: Baixe o FFmpeg e adicione ao PATH do sistema
- Ou coloque o `ffmpeg.exe` na mesma pasta do bot

### Dashboard nao conecta ao bot

- Verifique se o bot esta rodando
- Confira o IP no campo "IP do Servidor"
- Tente `localhost` se estiver na mesma maquina

### Spotify nao funciona

- Configure SPOTIFY_CLIENT_ID e SPOTIFY_CLIENT_SECRET no `.env`
- Tracks publicas funcionam sem credenciais
- Playlists e albuns precisam das credenciais

### WebSocket nao conecta de outra maquina

- Verifique se estao na mesma rede
- Confira se o firewall permite a porta 8765
- Use o IP correto (ex: 192.168.x.x, nao localhost)

## Seguranca

- **NUNCA** compartilhe seu token do Discord
- O arquivo `.env` esta no `.gitignore`
- Se expor o token, regenere imediatamente no Developer Portal

## Tecnologias

- **discord.py** - API do Discord
- **yt-dlp** - Extracao de audio do YouTube
- **spotipy** - API do Spotify
- **Tkinter** - Interface grafica
- **WebSockets** - Comunicacao em tempo real
- **SQLite** - Banco de dados local
- **Pillow** - Thumbnails

## Licenca

MIT License

---

Desenvolvido por Jhonatan
