# Validação do fork Windows/Linux

Entrega preparada em 31/10/2026. Ambiente: Linux, Python 3.12, PySide6 6.12.0,
PyNaCl 1.6.2. Interface Qt executada em modo offscreen.

## Resultado da rodada final

- 114 módulos de teste concluídos sem falhas ou erros.
- 2.273 casos contabilizados: 2.252 aprovados e 21 ignorados.
- Os skips correspondem a requisitos de plataforma ou histórico Git ausente no ZIP.
- Resultados por módulo: `validation-results.json`.
- Todos os arquivos Python foram analisados sintaticamente.
- Não foram encontrados imports de mac_app, Foundation, AppKit, Quartz ou objc no
  código Python de produção restante.
- A página de teclado Qt foi renderizada e inspecionada, com as opções Windows/Linux.

A rodada inclui protocolo, pareamento, criptografia, migrações, teclas especiais,
acentuação, captura/injeção simulada X11 e Wayland, inicialização Linux e páginas Qt.

## Limites

Não equivale à execução de toda a suíte upstream. Dois módulos extensos de simulação
(`test_crossing_e2e` e `test_profiles_e2e`) ultrapassaram o limite inicial de 60 segundos
e não estão incluídos na contagem final. Uma execução prolongada do primeiro avançou
sem falhas nos casos concluídos, mas foi interrompida antes de terminar. Um caso
isolado também ultrapassou 20 segundos no código original; não foi demonstrado que
essa duração seja uma regressão do fork. Não há conclusão integral sobre essas suítes.

Os testes nativos Windows não foram integralmente executados neste host Linux.
Uma tentativa adicional de testar `test_no_uac_runtime` apresentou três erros por
APIs ctypes exclusivas do Windows ausentes no host; esse módulo não integra a rodada
portável acima. Não foi produzido nem validado um executável Windows ou Flatpak.

A captura real de teclado/mouse, ABNT2 entre máquinas, clipboard real, suspensão,
reconexão e permissões de portais ainda precisam de teste em computadores físicos.
A redução de tamanho do projeto não constitui medição de redução de RAM ou latência.

## Reproduzir

Instale as dependências da plataforma e PyInstaller (também usado pelos testes de
empacotamento), e execute na raiz:

```bash
python tools/check_fork.py
```

Os logs e o resumo são gravados em `validation/`. Para incluir as simulações longas:

```bash
python tools/check_fork.py --include-long --timeout 1800
```

Os testes de interface utilizam QT_QPA_PLATFORM=offscreen; não substituem testes no
ambiente gráfico real. Para conferir traduções:

```bash
python tools/i18n_extract.py --check --complete
```

## Áudio opcional

Incluídos 16 testes de transporte/dispositivos/configuração de áudio e 3 testes
dos controles Qt. Tráfego TCP criptografado utiliza amostras sintéticas. A seção de
áudio foi renderizada e inspecionada em modo offscreen. As 888 strings do catálogo
passaram na verificação de completude. Captura e reprodução em hardware não foram
testadas, assim como a regra de firewall executada por PowerShell no Windows.

A primeira rodada encontrou ausência de PyInstaller no ambiente e um fixture de
permissões que ainda não simulava o novo módulo da interface. Após instalar a
dependência e atualizar o fixture, os módulos afetados foram reexecutados e passaram.

## Correção após teste em Windows — 30/10/2026 (horário de Brasília)

Relato de Error 0x100000001 ao habilitar envio levou à correção da ordem de
importação SoundCard/inicialização COM por worker. A suíte de áudio foi
reexecutada: 19 testes aprovados, incluindo 3 novos testes com COM simulado
(primeiro carregamento, reconexão/limpeza e isolamento Linux). A suíte completa
acima corresponde à rodada anterior; não foi repetida para esta correção.
A execução com dispositivos físicos Windows continua pendente.

## Compatibilidade SoundCard/NumPy — 30/10/2026

Reproduzida a mensagem "The binary mode of fromstring is removed, use frombuffer
instead" com NumPy 2.3.5. Executada a expressão de conversão original do backend
WASAPI do wheel SoundCard 0.4.5 com buffer CFFI sintético de 960 frames estéreo:
com NumPy 2.2.6 os valores foram preservados e o array resultante é gravável.
Limitado NumPy no requirements-win.txt a >=1.26,<2.3. A mesma suíte de 19 testes
de áudio passou usando NumPy 2.2.6. Não houve validação em dispositivo Windows real
nem repetição da suíte geral nesta atualização de dependência.

## Checkbox de mudo local Windows — 30/10/2026 (Brasília)

149 testes selecionados aprovados: transporte e configurações de áudio, ciclo de
mudo, interface Qt, configurações gerais, migrações e cobertura de tradução.
Foram testados restauração ao parar/desconectar, saída previamente silenciada,
falhas ao silenciar/restaurar, seleção da saída correta, salvamento/rollback da
checkbox e indisponibilidade no Linux. Os dispositivos e o controle de mudo são
simulados. A transmissão dos testes usa TCP/criptografia reais e PCM sintético.
A nova checkbox foi renderizada em modo offscreen e inspecionada visualmente.
Catálogos completos: 890 strings. Estrutura GUID validada com 16 bytes e ordem
little-endian. Não foi feita compilação EXE nem execução do controle COM de mudo
num dispositivo físico Windows; não foi repetida a suíte geral nesta mudança.
