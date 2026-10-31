# Beamer — Windows + Linux (fork pessoal)

Adaptação pessoal do Beamer 1.5.18, de Toby George Read Kalkman / Kalkman Code.
Origem: https://github.com/kalkman-code/beamer
Base recebida: arquivo `beamer-main.zip`, commit indicado pelo ZIP
`6bd653d2382005bce9a71484438d27369c28a799`.

Este fork mantém Windows e Linux e remove o aplicativo nativo macOS. Não é uma
versão oficial do autor original. Licença e avisos de autoria foram preservados.

## Funcionalidades mantidas

- Teclado e mouse entre computadores pela rede local.
- Pareamento, criptografia e reconexão.
- Área de transferência de texto e imagens.
- Configuração de telas, bordas, atalhos e efeitos.
- Windows e Linux, incluindo backends X11 e Wayland.

O programa não transmite vídeo nem transfere arquivos. Cada computador usa sua
própria tela. Linux continua experimental e depende das permissões e capacidades
do ambiente gráfico. O funcionamento entre computadores físicos precisa ser
validado no seu ambiente.

## Compartilhar áudio do sistema

Na página **Overview**, encontre **System audio**:

1. No computador que vai reproduzir o som, marque **Allow audio from paired computers**.
2. No computador de origem, escolha o destino em **Audio destination**.
3. Marque **Send this computer's audio**. Desmarque para interromper.

Use esta versão nas duas máquinas e faça o pareamento antes. O destino fica fixo,
mesmo quando o mouse muda de computador. O som local continua ativo por padrão.
No Windows, marque **Mute local output while sending (Windows)** na origem para
silenciar essa saída enquanto envia. Desmarque para voltar a ouvir localmente;
ao parar ou perder a conexão, o estado de mudo anterior é restaurado. Alguns drivers
também silenciam a captura loopback; se o destino ficar sem som, desmarque a opção.
O microfone não é transmitido. Cada máquina envia **ou** recebe por vez; o áudio começa desativado.

A conexão utiliza TCP 24822; permita essa porta no firewall do destino na rede
privada. Linux precisa de PulseAudio ou PipeWire com compatibilidade PulseAudio.
Veja [detalhes e limitações](docs/AUDIO.md).

## Estrutura

- `core/`: protocolo, pareamento, estado compartilhado e testes.
- `win_app/`: interface Qt compartilhada e backends Windows/Linux. O nome histórico
  da pasta foi mantido porque é usado pelos empacotadores e testes.
- `flatpak/`, `uk.co.kalkman.beamer.json`: distribuição Linux.
- `tools/`: extração de traduções, renderização Qt e ferramentas de build.
- `docs/FORK.md`: alterações, compatibilidade e limites desta adaptação.
- `docs/VALIDACAO.md`: resultados de verificação desta entrega.

## Executar no Windows a partir do código

Em um PowerShell, na pasta raiz extraída, com Python instalado:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r win_app\requirements-win.txt
.\.venv\Scripts\python.exe win_app\kvm_bridge_win.py
```

Instale nas duas máquinas ou execute o código em ambas, abra a opção de pareamento
em uma delas e informe o código na outra. Configure as posições das telas.
O firewall precisa permitir a conexão. Os scripts originais de instalação estão
em `win_app/`; o instalador configura as portas 24820/TCP e 24821/TCP+UDP para redes
Privadas. A elevação para controlar janelas administrativas é opcional; prompts
UAC e a área de trabalho segura continuam exigindo interação local.

### Gerar executável Windows

Em Windows, depois de criar o ambiente acima:

```powershell
Set-Location win_app
..\.venv\Scripts\python.exe -m PyInstaller build.spec
```

O resultado esperado é `win_app/dist/Beamer.exe`. Este ZIP contém código-fonte;
não contém um executável compilado ou assinado. O script original
`win_app/build_win_app.ps1` executa a suíte completa antes do build; consulte
`docs/VALIDACAO.md` sobre testes que dependem de plataforma e histórico Git.

## Linux

A rota de empacotamento preservada é Flatpak. Consulte `docs/flatpak-build.md` e:

```bash
bash tools/build_flatpak.sh x86_64
```

Para desenvolvimento em uma sessão gráfica Linux com bibliotecas nativas
necessárias instaladas:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r win_app/requirements-linux.txt
.venv/bin/python win_app/kvm_bridge_win.py
```

Wayland exige o barramento D-Bus da sessão, os portais apropriados, libei e
libxkbcommon. X11 exige uma sessão X e suas bibliotecas. As dependências nativas
estão especificadas no manifesto Flatpak. Uma sessão SSH/WSL sem ambiente gráfico
não substitui um desktop Linux para testar captura de teclado e mouse.

## Compatibilidade

Campos históricos como `mac_host`, `send_to_mac`, nomes de teclas do protocolo e
valores antigos de `modifier_style` foram preservados como compatibilidade de
configurações. Eles também são usados pelos caminhos Windows/Linux; não indicam a
presença do aplicativo macOS. Os testes de protocolo ainda incluem dados de peers
antigos. O protocolo não foi renumerado, e este fork não cria um bloqueio de rede
contra versões antigas do Beamer.

O catálogo de efeitos e os formatos de mensagens compartilhados foram mantidos.
Não houve reescrita do protocolo criptográfico.

## Atualizações e identidade

Nome, identificador Flatpak, diretórios de configuração e consulta de atualizações
ainda são os do upstream. Não trate este fork como instalação paralela isolada:
faça backup das configurações antes de alternar entre versões. A consulta do
upstream não distribui este fork; mantenha-a desativada nas configurações se não
quiser receber avisos de versões oficiais. Não há atualização automática deste ZIP.

## Licença

GPL-3.0; veja `LICENSE`. Autoria original: Toby George Read Kalkman / Kalkman Code.
Alterações deste fork registradas em `docs/FORK.md` em 29/10/2026.
