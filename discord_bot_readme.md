# 🎵 Bot de Música para Discord

Um bot simples e eficiente para tocar músicas do YouTube em servidores Discord, desenvolvido em Python.

## 📋 Índice

- [Características](#características)
- [Pré-requisitos](#pré-requisitos)
- [Instalação](#instalação)
- [Configuração](#configuração)
- [Uso](#uso)
- [Comandos](#comandos)
- [Estrutura do Projeto](#estrutura-do-projeto)
- [Solução de Problemas](#solução-de-problemas)
- [Contribuindo](#contribuindo)
- [Licença](#licença)

## ✨ Características

- ✅ Tocar músicas do YouTube por URL ou termo de busca
- ✅ Controles básicos (play, pause, resume, stop)
- ✅ Ajuste de volume
- ✅ Streaming em tempo real (sem download de arquivos)
- ✅ Comandos simples e intuitivos
- ✅ Código limpo e bem documentado

## 🔧 Pré-requisitos

Antes de começar, certifique-se de ter instalado:

- **Python 3.8+** - [Download](https://www.python.org/downloads/)
- **FFmpeg** - Necessário para processar áudio
  - Windows: [Download](https://ffmpeg.org/download.html)
  - Linux: `sudo apt install ffmpeg`
  - macOS: `brew install ffmpeg`
- **pip** - Gerenciador de pacotes Python (geralmente já vem com Python)

## 📦 Instalação

### 1. Clone o repositório

```bash
git clone https://github.com/seu-usuario/bot-musica-discord.git
cd bot-musica-discord
```

### 2. Crie um ambiente virtual (recomendado)

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/macOS
python3 -m venv venv
source venv/bin/activate
```

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```

## ⚙️ Configuração

### 1. Criar o Bot no Discord

1. Acesse o [Discord Developer Portal](https://discord.com/developers/applications)
2. Clique em **"New Application"**
3. Dê um nome ao seu aplicativo
4. Vá para a aba **"Bot"** no menu lateral
5. Clique em **"Add Bot"**
6. Copie o **Token** (você precisará dele!)
7. Ative as seguintes **Privileged Gateway Intents**:
   - ✅ Message Content Intent
   - ✅ Server Members Intent (opcional)

### 2. Convidar o Bot para seu Servidor

1. Vá para **OAuth2** > **URL Generator**
2. Selecione os scopes:
   - `bot`
   - `applications.commands`
3. Selecione as permissões:
   - Connect
   - Speak
   - Use Voice Activity
   - Send Messages
   - Embed Links
4. Copie a URL gerada e abra no navegador
5. Selecione seu servidor e autorize

### 3. Configurar o Token

Edite o arquivo `config.py` e adicione seu token:

```python
TOKEN = 'SEU_TOKEN_AQUI'
PREFIX = '!'
```

⚠️ **IMPORTANTE:** Nunca compartilhe seu token publicamente!

## 🚀 Uso

### Iniciar o bot

```bash
python bot.py
```

Você verá uma mensagem confirmando que o bot está online:

```
Bot conectado como NomeDoBot
ID: 123456789012345678
------
```

### Usando o bot no Discord

1. Entre em um canal de voz
2. Use os comandos no chat (veja seção de comandos abaixo)

## 📝 Comandos

| Comando | Descrição | Exemplo |
|---------|-----------|---------|
| `!entrar` | Bot entra no seu canal de voz | `!entrar` |
| `!tocar <url/busca>` | Toca uma música do YouTube | `!tocar https://youtube.com/...`<br>`!tocar never gonna give you up` |
| `!pausar` | Pausa a música atual | `!pausar` |
| `!retomar` | Retoma a música pausada | `!retomar` |
| `!parar` | Para a música completamente | `!parar` |
| `!volume <0-100>` | Ajusta o volume | `!volume 50` |
| `!sair` | Bot sai do canal de voz | `!sair` |

### Exemplos de Uso

```
# Entrar no canal de voz
!entrar

# Tocar música por URL
!tocar https://www.youtube.com/watch?v=dQw4w9WgXcQ

# Tocar música por busca
!tocar imagine dragons radioactive

# Ajustar volume para 75%
!volume 75

# Pausar música
!pausar

# Retomar música
!retomar

# Parar música
!parar

# Sair do canal
!sair
```

## 📁 Estrutura do Projeto

```
bot-musica-discord/
│
├── bot.py              # Arquivo principal do bot
├── config.py           # Configurações (TOKEN, PREFIX)
├── requirements.txt    # Dependências do projeto
├── README.md          # Este arquivo
├── .gitignore         # Arquivos ignorados pelo Git
└── venv/              # Ambiente virtual (não commitado)
```

## 🔒 Segurança

- ⚠️ **NUNCA** faça commit do arquivo `config.py` com seu token
- Use variáveis de ambiente em produção:
  ```python
  import os
  TOKEN = os.getenv('DISCORD_TOKEN')
  ```
- Se expor seu token acidentalmente, regenere-o imediatamente no Developer Portal
- Adicione `config.py` ao `.gitignore`

## 🐛 Solução de Problemas

### O bot não toca música

**Problema:** Bot não reproduz áudio após comando `!tocar`

**Soluções:**
- Verifique se o FFmpeg está instalado: `ffmpeg -version`
- Confirme que o bot tem permissões "Connect" e "Speak" no servidor
- Teste com diferentes URLs do YouTube
- Verifique os logs no terminal para erros específicos

### Erro de conexão ao iniciar

**Problema:** Bot não consegue se conectar ao Discord

**Soluções:**
- Verifique se o token em `config.py` está correto
- Confirme que os Intents estão ativados no Developer Portal
- Verifique sua conexão com a internet

### Erro "discord.ext.commands.errors.CommandNotFound"

**Problema:** Bot não reconhece comandos

**Soluções:**
- Verifique se você está usando o prefixo correto (padrão: `!`)
- Confirme que o Message Content Intent está ativado

### Qualidade de áudio ruim

**Problema:** Áudio com cortes ou baixa qualidade

**Soluções:**
- Verifique sua conexão de internet
- Ajuste as opções de formato no código `ytdl_format_options`
- Reduza o volume se houver distorção

### Erro "yt-dlp"

**Problema:** Erros relacionados ao download de vídeos

**Soluções:**
- Atualize o yt-dlp: `pip install --upgrade yt-dlp`
- Alguns vídeos podem ter restrições de região ou idade
- Teste com vídeos diferentes

## 🚧 Melhorias Futuras

Funcionalidades planejadas para próximas versões:

- [ ] Sistema de fila de músicas
- [ ] Comando para pular música
- [ ] Playlists personalizadas
- [ ] Comando de loop/repetir
- [ ] Integração com Spotify
- [ ] Comandos slash (/)
- [ ] Sistema de favoritos
- [ ] Equalizer de áudio

## 🤝 Contribuindo

Contribuições são bem-vindas! Para contribuir:

1. Faça um fork do projeto
2. Crie uma branch para sua feature (`git checkout -b feature/NovaFuncionalidade`)
3. Commit suas mudanças (`git commit -m 'Adiciona nova funcionalidade'`)
4. Push para a branch (`git push origin feature/NovaFuncionalidade`)
5. Abra um Pull Request

## 📄 Licença

Este projeto está sob a licença MIT. Veja o arquivo `LICENSE` para mais detalhes.

## 📚 Recursos Adicionais

- [Documentação discord.py](https://discordpy.readthedocs.io/)
- [Documentação yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [Discord Developer Portal](https://discord.com/developers/docs)
- [Guia de FFmpeg](https://ffmpeg.org/documentation.html)

## 💬 Suporte

Se você encontrar problemas ou tiver dúvidas:

- Abra uma [Issue](https://github.com/seu-usuario/bot-musica-discord/issues)
- Consulte a seção [Solução de Problemas](#solução-de-problemas)
- Entre em contato pelo Discord: seu-usuario#0000

## ⭐ Agradecimentos

- Comunidade discord.py
- Desenvolvedores do yt-dlp
- Todos os contribuidores do projeto

---

**Nota:** Este bot é para fins educacionais. Respeite os termos de serviço do YouTube e do Discord ao usar o bot.

Desenvolvido com ❤️ por [Seu Nome]