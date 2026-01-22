# Histórico de Desenvolvimento - Bot de Música Discord

## Data: 2025-09-29

---

## Sessão 1: Implementação Inicial

### Pedido Inicial
- Criar bot de música para Discord com comando `/play`
- Usar Python com discord.py e yt-dlp

### Problemas Encontrados e Soluções

#### 1. Erro de Formato do YouTube
**Problema:** `ERROR: [youtube] Requested format is not available`

**Solução:**
```python
ytdl_format_options = {
    'extractor_args': {'youtube': {'player_client': ['android', 'web'], 'skip': ['hls', 'dash']}},
}
```

#### 2. Sistema de Fila e Botões
**Implementação:**
- Botões: ⏮️ (anterior), ⏸️ (pausar), ⏭️ (próximo), 🔀 (shuffle), 📜 (fila)
- Sistema de fila com histórico
- Mensagem com player sempre na última mensagem enviada

---

## Sessão 2: Melhorias de Visual e UX

### Mudanças de Design
1. **Visual Colorido** → Muitas cores, rejeitado
2. **Visual Minimalista** → Muito simples, rejeitado
3. **Visual Clean (Atual)** → Aceito
   - Embed cinza escuro (`0x2f3136`)
   - Formato retangular com informações organizadas
   - Botões em duas linhas

### Estrutura do Embed
```
🎵 Tocando Agora
[Nome da música]

🎵 Próxima Música
[Nome da próxima] ou Nenhuma

📝 Restante na Fila
[Número de músicas]
```

---

## Sessão 3: Sistema de Fila Estilo Spotify

### Problema Identificado
- Ao usar botões anterior/próximo, músicas tocavam fora de ordem
- Botões sumiam ao voltar múltiplas vezes
- Sistema de fila dividido (history + queue) causava confusão

### Solução: Refatoração Completa para Sistema Spotify

#### Estrutura da Classe MusicQueue
```python
class MusicQueue:
    def __init__(self):
        self.all_songs = deque()        # TODAS as músicas
        self.current_index = -1         # Índice da música atual
        self.loop = None                # Canal para enviar mensagens
        self.control_message = None     # Mensagem com botões
        self.manual_control = False     # Flag para navegação manual
```

#### Métodos Principais
```python
def get_current():
    # Retorna música no índice atual

def get_history():
    # Retorna all_songs[:current_index]

def get_queue():
    # Retorna all_songs[current_index + 1:]

def next():
    # Incrementa current_index

def previous():
    # Decrementa current_index
```

---

## Sessão 4: Correção de Bugs de Navegação

### Problema: Botões Sumindo ao Voltar
**Causa:** Condição de corrida entre `previous_button` e callback `play_next()`

**Solução:**
1. Adicionar flag `manual_control` na fila
2. Quando botão anterior é clicado:
   ```python
   queue.manual_control = True
   queue.current_index -= 1
   voice_client.stop()  # Dispara callback
   # ... toca música manualmente
   ```
3. No `play_next()`:
   ```python
   if queue.manual_control:
       queue.manual_control = False
       return  # Ignora execução automática
   ```

### Problema: `/play` Não Adiciona à Fila
**Causa:** Lógica antiga usava `queue.current` ao invés do sistema de índices

**Solução:**
```python
# Primeira música
queue.add(song_data)
queue.current_index = 0

# Músicas subsequentes (quando já está tocando)
if voice_client.is_playing() or voice_client.is_paused():
    queue.add(song_data)  # Adiciona ao final
```

---

## Sessão 5: Sistema de Shuffle

### Implementação Original (Rejeitada)
- Flag `shuffle` que randomizava a cada `next()`
- Comportamento imprevisível

### Implementação Atual (Estilo Spotify)
```python
@discord.ui.button(emoji='🔀')
async def shuffle_button():
    queue_list = queue.get_queue()  # Pega apenas fila

    rand.shuffle(queue_list)  # Embaralha fila

    # Reconstrói: histórico + atual + fila embaralhada
    kept_songs = list(queue.all_songs)[:queue.current_index + 1]
    queue.all_songs = deque(kept_songs + queue_list)
```

**Características:**
- Embaralha apenas músicas não tocadas
- Mantém histórico intacto
- Shuffle acontece uma vez, não a cada música

---

## Sessão 6: Comando /stop

### Problema
Ao usar `/stop`, os botões permaneciam na tela

### Solução
```python
@bot.tree.command(name='stop')
async def stop():
    # 1. Deletar mensagem com botões
    if queue.control_message:
        await queue.control_message.delete()

    # 2. Ativar controle manual
    queue.manual_control = True

    # 3. Limpar fila
    queue.clear()
    queue.control_message = None

    # 4. Parar e desconectar
    voice_client.stop()
    await voice_client.disconnect()
```

---

## Arquitetura Atual do Sistema

### Fluxo de Execução

#### 1. Tocar Primeira Música
```
/play → add(song) → current_index = 0 → play() → criar embed com botões
```

#### 2. Adicionar à Fila
```
/play (durante reprodução) → add(song) → mensagem de confirmação
```

#### 3. Música Termina (Automático)
```
callback after → play_next() → next() → current_index++ → play()
```

#### 4. Botão Próximo
```
⏭️ → stop() → callback → play_next() → next() → play()
```

#### 5. Botão Anterior
```
⏮️ → manual_control = True → current_index-- → stop() →
callback (ignorado) → play() → criar nova mensagem
```

### Estrutura de Dados

```
all_songs = [A, B, C, D, E, F]
current_index = 2

Visualização:
[A, B, C, D, E, F]
       ^
    atual

Histórico: [A, B]
Atual: C
Fila: [D, E, F]
```

---

## Comandos Disponíveis

| Comando | Descrição |
|---------|-----------|
| `/play <url/busca>` | Toca música ou adiciona à fila |
| `/queue` | Mostra fila completa |
| `/skip` | Pula música atual |
| `/stop` | Para tudo e desconecta |
| `/clear` | Limpa mensagens do canal |

## Botões no Player

| Botão | Emoji | Função |
|-------|-------|--------|
| Anterior | ⏮️ | Volta para música anterior |
| Pausar/Retomar | ⏸️/▶️ | Pausa ou retoma reprodução |
| Próximo | ⏭️ | Pula para próxima música |
| Shuffle | 🔀 | Embaralha fila |
| Fila | 📜 | Mostra lista de músicas |

---

## Funcionalidades Especiais

### 1. Auto-Desconectar
```python
@bot.event
async def on_voice_state_update(member, before, after):
    # Se todos os usuários saírem do canal
    members = [m for m in before.channel.members if not m.bot]
    if len(members) == 0:
        await voice_client.disconnect()
        queue.clear()
```

### 2. Limpeza de Mensagens (Bulk Delete)
```python
@bot.tree.command(name='clear')
async def clear_messages():
    # Deleta em lotes de 50 com delay de 1.5s
    # Evita rate limiting do Discord
```

---

## Dependências

```txt
discord.py[voice]
yt-dlp
PyNaCl
```

### Configurações Importantes

#### yt-dlp
```python
ytdl_format_options = {
    'format': 'bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best',
    'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
}
```

#### FFmpeg
```python
ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}
```

---

## Problemas Conhecidos (Resolvidos)

### ✅ Botões somem ao voltar
**Solução:** Flag `manual_control` + nova mensagem

### ✅ Música errada ao navegar
**Solução:** Sistema de índice único

### ✅ /play não adiciona à fila
**Solução:** Lógica corrigida com `current_index`

### ✅ Botões não somem no /stop
**Solução:** Deletar `control_message` antes de limpar

### ✅ Shuffle imprevisível
**Solução:** Shuffle uma vez na fila, não a cada música

---

## Melhorias Futuras (Sugestões)

- [ ] Sistema de loop (repetir música/fila)
- [ ] Comando para remover música específica da fila
- [ ] Seek (pular para timestamp específico)
- [ ] Playlists do YouTube
- [ ] Integração com Spotify
- [ ] Sistema de favoritos por usuário
- [ ] Equalizer de áudio
- [ ] Letra das músicas (integração com API)
- [ ] Sistema de votação para pular
- [ ] Histórico persistente em banco de dados

---

## Notas de Desenvolvimento

### Padrões Usados
- **Async/Await:** Todas operações I/O são assíncronas
- **Deque:** Estrutura de dados eficiente para fila
- **Views:** Discord.py Views para botões persistentes
- **Embeds:** Mensagens formatadas do Discord

### Boas Práticas Aplicadas
- Flag de controle para evitar race conditions
- Tratamento de exceções em operações críticas
- Mensagens efêmeras para feedback temporário
- Limpeza de recursos (mensagens antigas, controle de memória)
- Validações antes de executar ações

### Decisões de Design
1. **Sistema de Índice Único:** Mais simples que dual-deque
2. **Manual Control Flag:** Solução elegante para race conditions
3. **Spotify-like Behavior:** UX familiar para usuários
4. **Embeds Minimalistas:** Melhor legibilidade

---

## Token e Segurança

⚠️ **IMPORTANTE:** O token está hardcoded no arquivo. Para produção:

```python
import os
TOKEN = os.getenv('DISCORD_TOKEN')
```

Adicionar ao `.gitignore`:
```
config.py
.env
```

---

## Estrutura de Arquivos

```
Musica/
├── bot.py                      # Código principal
├── requirements.txt            # Dependências
├── discord_bot_readme.md       # Documentação do usuário
├── HISTORICO_DESENVOLVIMENTO.md # Este arquivo
└── .gitignore                  # (criar)
```

---

## Contato e Contribuições

Este bot foi desenvolvido iterativamente através de debugging colaborativo e refinamento de requisitos. Todas as decisões de design foram baseadas em feedback direto do usuário.

**Versão Atual:** 2.0 (Sistema Spotify-like)
**Última Atualização:** 2025-09-29

---

## Changelog

### v2.0 - Sistema Spotify-like
- Refatoração completa da fila para sistema de índice único
- Implementação de `manual_control` flag
- Shuffle estilo Spotify (embaralha fila, não randomiza)
- Correção de bugs de navegação

### v1.5 - Visual e UX
- Design clean com embed retangular
- Auto-desconectar quando sala vazia
- Comando `/clear` otimizado

### v1.0 - Versão Inicial
- Comando `/play` básico
- Botões de controle
- Sistema de fila básico

---

**Fim do Histórico**