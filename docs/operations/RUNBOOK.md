# Runbook local do primeiro slice

## Subir

```bash
PYTHONPATH=src RIBEIRA_DB_PATH=/tmp/ribeira.sqlite3 python3 -m ribeira_platform.api
```

## Verificar saúde

```bash
curl http://127.0.0.1:8080/health
```

## Falha de provider

1. Consultar o `data_quality_event` do tenant/fonte.
2. Confirmar endpoint, versão e disponibilidade do provider.
3. Não inserir valor manual como se fosse observado.
4. Reprocessar somente após a resposta original estar disponível e auditada.

## Falha de regra

Se não houver regra ativa, a API deve devolver `INCONCLUSIVE` com
`missing_data=active_rule:soil_moisture`. Publicar uma nova versão com aprovador;
não alterar a versão histórica.

## Produção ainda não autorizada

Este bootstrap não deve ser exposto à internet pública: não possui autenticação,
TLS próprio, rate limiting, RLS executado ou observabilidade operacional completa.
