# Dashboard interativo — Aula 5

O **mesmo time multi-agente** das aulas anteriores, agora respondendo **sob
demanda** num app web. O usuário digita um pedido em linguagem natural e o
dashboard aciona o time da Aula 3, exibindo cada peça do resultado — a série em
tabela, o gráfico, as variações como métricas, a análise do revisor e as
notícias — em abas, enquanto narra qual agente está trabalhando.

> É o par da Aula 4: lá o time entrega por e-mail, no automático; aqui entrega
> na tela, sob demanda. Mesmo time, duas formas de entrega.

## Rodar

```bash
pip install -r requirements.txt
cp .env.example .env          # e ponha sua GOOGLE_API_KEY
streamlit run dashboard/app.py
```

O navegador abre em `localhost:8501`. Peça, por exemplo: *"Analise o IPCA"*,
*"Variações da Selic"*, *"Como está o câmbio?"*, *"Mostre a PMC"*.

## Como funciona

```
você digita  ─▶  responder()  ─▶  time da Aula 3 (analista→…→revisor)
   (chat)         (ponte)            cada passo vira progresso na tela
                                          │
                                          ▼
                       extrair(State)  ─▶  abas: 📝 análise · 🔢 tabela
                                            📊 gráfico · 📰 notícias
```

- **`dashboard/runtime.py`** — a ponte. Roda o time com `app.stream()` (em vez
  de `rodar()`) para emitir o progresso ao vivo, e `extrair()` separa o State
  final nas peças que a tela exibe.
- **`dashboard/app.py`** — o app Streamlit: campo de chat, narração do progresso
  (qual agente está rodando), abas de resultado e cache por pedido.
- **`time/`** — o time multi-agente, idêntico ao das aulas 3 e 4. Não foi
  tocado: o dashboard só o reusa.

## Decisões de produção

- **Progresso ao vivo** — rodar o time leva segundos; em vez de uma tela
  congelada, o dashboard narra cada agente conforme ele trabalha (`app.stream`).
- **Cache por pedido** — rodar o time gasta tokens; `st.cache_data` faz pedir
  "IPCA" duas vezes devolver o resultado guardado, sem rodar os quatro agentes
  de novo.
- **Estado da conversa** — o Streamlit reexecuta o script a cada interação, então
  o histórico do chat vive em `st.session_state` (sobrevive às reexecuções).

## Estrutura

```
imersao-multi-agentes-05/
├── README.md  requirements.txt  .env.example  .gitignore
├── dashboard/
│   ├── __init__.py
│   ├── runtime.py        # ponte: stream do time + extração do resultado
│   └── app.py            # o app Streamlit (chat + abas)
└── time/                 # o time multi-agente (idêntico às aulas 3 e 4)
    └── equipe.py  state.py  agents/  tools/  prompts/  data/
```
