# Áudio do sistema — primeira implementação

A seção System audio, em Overview, permite selecionar um computador pareado e
habilitar o envio por checkbox. No destino, a checkbox Allow audio from paired
computers precisa estar marcada. Instale esta versão e suas dependências nas duas
máquinas. Configurações existentes mantêm ambas as opções desligadas.

## Comportamento

- Destino fixo, independente do teclado e do mouse.
- Captura da saída padrão do sistema e reprodução na saída padrão do destino.
- Som local permanece ativo por padrão; não há captura de microfone.
- No Windows, a opção de mudo local silencia a saída capturada durante o envio.
- Uma transmissão de entrada ou de saída por máquina; habilitar uma desativa a outra.
- Ao trocar a saída padrão do sistema, desative e reative o áudio no Beamer.
- Configurações são locais e persistem após reinício, incluindo a ativação.
- A saída padrão precisa aceitar dois canais. Ausência de monitor de saída resulta
  em erro; o programa nunca tenta substituir a captura por um microfone físico.

## Implementação

Canal TCP separado, porta fixa 24822, apenas aberto quando a recepção está habilitada.
Pareamento existente autentica as máquinas; HKDF separa a chave de áudio da chave
usada no canal de entrada. O enquadramento LinkSession utiliza X25519 e
ChaCha20-Poly1305, autenticação de identidade e proteção contra repetição.
Remover ou desabilitar o pareamento encerra a transmissão ativa.

PCM estéreo de 48 kHz, 16 bits, blocos de 20 ms: aproximadamente 1,54 Mbit/s por
fluxo, além dos cabeçalhos. Não há codec comprimido nem sincronização audiovisual.
TCP pode causar atraso em redes congestionadas; 20 ms é o tamanho do bloco, não
uma promessa de latência total. Captura, rede e reprodução usam uma thread separada.
A conexão tenta novamente após falhas; o estado aparece sob as checkboxes e o erro
mais recente fica no tooltip.

SoundCard 0.4.5 e NumPy implementam WASAPI loopback no Windows e monitor PulseAudio
no Linux (incluindo PipeWire-Pulse). O Flatpak recebe acesso PulseAudio. Os builds
Windows incluem os arquivos CFFI do SoundCard e excluem seu backend CoreAudio.
O instalador Windows inclui uma regra TCP 24822 restrita ao programa/rede privada;
a execução pelo código pode precisar de liberação manual no firewall do destino.

Referências de implementação: https://github.com/bastibe/SoundCard e
https://github.com/flathub/io.qt.PySide.BaseApp.

## Verificação e limites

Testes usam sockets TCP reais, criptografia real e áudio sintético. Cobrem dados
PCM, autenticação, identidade, repetição, limites de frames, revogação, encerramento,
seleção exclusiva do monitor, configuração e controles Qt. Não foi possível
validar WASAPI, PulseAudio, volume, qualidade ou latência em computadores físicos.
Executáveis Windows e Flatpak não foram compilados nesta entrega.

Teste manual sugerido: parear duas máquinas, habilitar a recepção no destino,
selecioná-lo na origem e ativar o envio. Reproduzir música, mover o mouse entre
máquinas, desativar o envio e confirmar que o áudio remoto para. Repetir nos dois
sentidos, um por vez, e verificar reconexão após perda da rede.

## Correção da inicialização Windows

Corrigida a ordem de carregamento do SoundCard e da inicialização COM por thread.
SoundCard 0.4.5 inicializa COM durante o primeiro import e rejeita o retorno
S_FALSE (biblioteca já inicializada), apresentando Error 0x100000001. Agora a
biblioteca é carregada antes da inicialização explícita por worker; a criação
dos dispositivos continua ocorrendo depois desta inicialização. O encerramento
COM é preservado inclusive em erros e reconexões.

Após substituir o código, encerre o Beamer nas duas máquinas e recompile o
executável no Windows. Substituir apenas o código ao lado de um EXE antigo não
altera seu conteúdo. Na raiz do projeto, com dependências instaladas:

```powershell
Set-Location win_app
..\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm build.spec
```

O EXE atualizado fica em win_app/dist/Beamer.exe. Primeiro teste no destino com
recepção habilitada, depois ative o envio na origem. Se houver nova falha, capture
o tooltip da origem, pois a falha anterior pode ter ocultado outros problemas.

Referências: https://learn.microsoft.com/en-us/windows/win32/api/combaseapi/nf-combaseapi-coinitializeex
e soundcard/mediafoundation.py da distribuição SoundCard 0.4.5.

## Compatibilidade NumPy no Windows

O backend WASAPI do SoundCard 0.4.5 ainda usa numpy.fromstring em modo binário,
removido no NumPy 2.3. Os requisitos Windows agora limitam NumPy a >=1.26,<2.3.
O backend Linux não usa essa chamada e mantém a faixa anterior. Para compilar
esta combinação no Windows, use Python 3.12 ou 3.13 (NumPy <2.3 não oferece
suporte a Python 3.14).

Em um ambiente existente, na raiz do projeto:

```powershell
.\.venv\Scripts\python.exe -m pip install "numpy>=1.26,<2.3"
.\.venv\Scripts\python.exe -c "import numpy; print(numpy.__version__)"
Set-Location win_app
..\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm build.spec
```

Encerre o Beamer antigo e abra o EXE recompilado. Faça isso nas duas máquinas.
Não é necessário refazer o pareamento. Referência da remoção:
https://numpy.org/doc/2.3/release/2.3.0-notes.html

## Mudo local opcional no Windows

A checkbox **Mute local output while sending (Windows)** fica disponível na origem
quando o envio está habilitado. Ela começa desligada e é salva localmente. Ao
habilitar ou desabilitar o mudo, o fluxo reinicia para aplicar a preferência.

A API IAudioEndpointVolume atua sobre o ID exato da saída aberta pela captura.
Não há alteração do nível de volume nem das sessões de aplicativos. O estado de
mudo anterior é restaurado ao parar, trocar o destino, perder a conexão ou sair
normalmente do Beamer. Uma saída já silenciada permanece silenciada. Fechamento
forçado, queda de energia, travamento nativo ou remoção do dispositivo podem
impedir a restauração; nesse caso, desative o mudo no controle de som do Windows.

O recurso de mudo está indisponível no Linux; a transmissão Linux continua
funcionando como antes. Nenhuma dependência adicional foi introduzida: as chamadas
Windows usam ctypes, na thread de áudio e dentro da sessão COM já inicializada.

A captura de alguns drivers/hardware acompanha o mudo do endpoint e pode ficar
silenciosa no destino. Desmarque a opção se isso ocorrer. O usuário confirmou a
transmissão Windows antes desta mudança; esta nova opção ainda requer validação
no mesmo hardware. Referências da API:
https://learn.microsoft.com/en-us/windows/win32/api/endpointvolume/nn-endpointvolume-iaudioendpointvolume
e https://learn.microsoft.com/en-us/windows/win32/api/endpointvolume/nf-endpointvolume-iaudioendpointvolume-setmute
