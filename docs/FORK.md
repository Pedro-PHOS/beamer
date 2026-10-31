# Alterações do fork — 29/10/2026

Escopo: remover o aplicativo macOS e suas dependências nativas, mantendo Windows
e Linux. Base upstream: 1.5.18 / 6bd653d2382005bce9a71484438d27369c28a799.

## Removido

- Pasta `mac_app/`, incluindo testes, builds e requisitos PyObjC/py2app.
- Ícone `.icns`, capturas de tela do Mac e ferramentas exclusivas de auditoria e
  renderização AppKit.
- Integrações Foundation para idioma, região e consulta de releases.
- Decodificação BSD/macOS de sockaddr no caminho POSIX de descoberta.
- Tradução de atalhos Windows → macOS no sender.
- Opções de teclado para Mac e ativação de efeito de notch na interface Qt.
- Testes exclusivos de captura/injeção do macOS e caminhos nativos em testes mistos.

## Preservado e adaptado

- Qt/PySide6, captura/injeção Windows e backends Linux X11/Wayland.
- Criptografia, pareamento, configurações, perfis, clipboard e formato de mensagens.
- Testes Windows/Linux de teclado numérico, acentos, configurações e protocolo.
- Ferramentas Qt e catálogos de tradução, regenerados sem fontes macOS.
- Leitura de campos e enumerações legadas; nenhuma configuração do usuário é apagada.
- Testes dependentes de commits antigos agora informam skip quando o ZIP não contém
  o histórico Git necessário, em vez de falharem com um erro genérico de Git.

## Correção observada durante a validação Linux

A tela de inicialização importava `admin_mode` no Linux, e o planejador de teclado
compartilhado importava `firewall_win` imediatamente. Os imports administrativos
agora são carregados somente no Windows. Isso mantém o planejador reutilizável no
Linux sem carregar esses componentes de administração Windows.

## O que deliberadamente permanece

O protocolo aceita nomes históricos e o módulo `keytable` mantém tabelas de
compatibilidade pequenas: o backend X11 utiliza nomenclatura histórica no seu
caminho de captura. Remover isso indiscriminadamente trocaria Ctrl/Super. Também
permanecem campos `mac_*` em configurações, cenários sintéticos de interoperabilidade
nas verificações do protocolo e geometria compartilhada de efeitos. Eles não
importam frameworks Apple nem exigem `mac_app/`.

O catálogo de efeitos contém rotinas genéricas também usadas por renderizadores
antigos. Não foi feito um corte agressivo dessas rotinas por palavras-chave.
A restrição de sistemas suportados é aplicada ao carregamento de backend local;
ela não é um bloqueio de conexões com peers antigos.

## Próximo teste em hardware

1. Parear Windows ↔ Windows e Windows ↔ Linux.
2. Conferir Ctrl/C/V, Alt+Tab, Windows/Super, AltGr, ç e acentos em teclado ABNT2.
3. Validar clipboard de texto e imagens, bordas, múltiplos monitores e reconexão.
4. Repetir no Linux em X11 e Wayland, concedendo as permissões dos portais.
5. Testar suspensão/retorno e reinício com teclas pressionadas.

A entrega não certifica latência, consumo de RAM nem funcionamento de captura real.

## Áudio opcional — 31/10/2026

Adicionadas checkboxes de envio e recepção, destino fixo, preferências persistentes
e canal TCP autenticado independente. Incluídos SoundCard/NumPy, regra de firewall
e ajustes de empacotamento Windows/Flatpak. Detalhes em `AUDIO.md`.

## Mudo local opcional — 30/10/2026 (Brasília)

Checkbox Windows para silenciar o endpoint capturado apenas durante o envio, com
restauração do estado anterior. Configuração persistente, padrão desligado. O envio
e a recepção Linux permanecem disponíveis; o mudo local é exclusivo do Windows.
