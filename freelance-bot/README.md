# Freelance bot

Busca projetos no Workana, 99Freelas e Freelancer.com a cada 2 horas, avalia cada um com nota de 0 a 100, escreve um rascunho de proposta para os aprovados e avisa por e-mail. O envio da proposta é sempre manual, pelo painel.

## Instalação (uma vez)

1. Instale as dependências:
   ```
   pip install -r requirements.txt
   ```
2. Copie `config/segredos.exemplo.json` para `config/segredos.json` e preencha:
   - `openai_compat_api_key`: chave do FreeLLMAPI (página **Keys** do painel dele, em http://localhost:3001), se `ia.provedor` for `"openai_compat"`
   - `anthropic_api_key`: chave da API do Claude (console.anthropic.com), se `ia.provedor` for `"anthropic"`
   - `gmail_usuario` e `gmail_senha_app`: senha de app do Gmail (Conta Google > Segurança > Verificação em duas etapas > Senhas de app)
   - `email_destino`: para onde vão os avisos
3. Preencha `dados/portfolio.md` com seus dados reais (KYTEC, GitHub, currículo) e apague a linha `MODELO` do topo. A IA usa só o que estiver ali.
4. Ajuste `config/config.json` (buscas, palavras-chave, limites de orçamento).
5. Teste:
   ```
   python orquestrador.py --teste-email     # confere o Gmail
   python orquestrador.py --sem-ia          # só coleta (sem custo de IA)
   python orquestrador.py                   # rodada completa
   python painel/servidor.py                # painel em http://127.0.0.1:5000
   ```
6. Agende:
   ```
   powershell -ExecutionPolicy Bypass -File agendar.ps1
   ```
   Isso cria a tarefa da rodada (a cada 2 h) e a do painel (abre ao fazer logon). Para remover: `agendar.ps1 -Remover`.

## Como a nota funciona

| Parte | Pontos | Como é calculada |
|---|---|---|
| Orçamento | 25 | Valor total em R$: 0 no `minimo_brl`, nota cheia no `ideal_brl`. Por hora: taxa × horas estimadas pela IA |
| Cliente | 25 | Nota média, pagamento verificado e número de avaliações. Sem dados = nota neutra (10) |
| Dificuldade | 25 | Dificuldade real estimada pela IA: 1/10 vale 25, 10/10 vale 0 |
| Remuneração | 25 | Valor ÷ média da plataforma e categoria (0,5× = 0, 1× = 12,5, 1,5× ou mais = 25). Enquanto não houver 5 amostras, compara valor/hora estimado com `valor_hora_referencia_brl` |

**Aprovado** quando: nota ≥ 60, IA não marcou como suspeito, nível real não é avançado, dificuldade ≤ 8.
**Intermediário** (declarado ou estimado) precisa ainda de dificuldade ≤ 6 e orçamento ≥ R$ 400.
Todos esses números estão em `config/config.json`.

## Estados no painel

`novo` → (abriu no painel) `revisado` → `enviado`, ou `descartado` a qualquer momento. `reprovado` fica visível com os motivos; dá para gerar rascunho mesmo assim.

## O que cada plataforma oferece

| Plataforma | Como lê | Limitações |
|---|---|---|
| Workana | JSON embutido na página `/jobs` | Não informa nível nem número de avaliações do cliente sem login |
| 99Freelas | HTML de `/projects` + página do projeto | Orçamento quase sempre "Aberto" (usa o valor mínimo) |
| Freelancer.com | API pública | Não traz dados do cliente sem login |
| Upwork | **Desativado** | Exige login e proíbe raspagem; só pela API oficial (ver `coletores/upwork.py`) |

Se uma plataforma mudar o layout, o log mostra `falha em ...` e as outras continuam.

## Provedor de IA

Escolha em `config.json` → `ia.provedor`:

| Valor | O que usa | Observações |
|---|---|---|
| `"openai_compat"` (padrão) | FreeLLMAPI rodando no seu PC (`ia.openai_compat.base_url`, padrão `http://localhost:3001/v1`) | Grátis. O modelo muda conforme as cotas, então notas podem variar; o painel mostra qual modelo avaliou cada projeto. Se a resposta vier fora do formato, o bot pede de novo (até `tentativas_json` vezes). O FreeLLMAPI precisa estar aberto quando a rodada rodar |
| `"anthropic"` | API do Claude (`ia.modelo`, padrão `claude-opus-5-5`) | Pago. Saída estruturada garantida e qualidade estável. Para gastar menos, use `claude-sonnet-5-5` ou `claude-haiku-5-5` |

`ia.openai_compat.modelo` aceita `"auto"`, `"auto:fast"`, `"auto:smart"`, um perfil do FreeLLMAPI (`"auto:<perfil>"`) ou o id de um modelo específico. Para notas mais consistentes, fixe um modelo.

Em qualquer provedor, cada projeto que passa nas palavras-chave gera uma chamada de avaliação e cada aprovado gera mais uma para o rascunho, com no máximo `ia.max_avaliacoes_por_rodada` (25) por rodada. Se a chave estiver errada, o limite acabar ou o serviço estiver fora, a rodada para de avaliar e os projetos ficam pendentes para a próxima (até 3 tentativas cada).

## Arquivos

- `logs/bot.log`: o que aconteceu em cada rodada
- `dados/projetos.db`: banco SQLite com tudo
- Rodadas recentes: aba "Rodadas" do painel
