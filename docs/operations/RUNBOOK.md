# Runbook local da fundação

## Subir

Consulte `docs/operations/LOCAL_DEVELOPMENT.md`. O caminho de produção local usa
PostgreSQL/PostGIS, migrations e a role `ribeira_app`; SQLite é somente fallback
para testes rápidos.

## Verificar saúde

```bash
curl http://127.0.0.1:8000/health/live
curl http://127.0.0.1:8000/health/ready
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

## Exposição pública ainda não autorizada

O adapter HTTP possui autenticação JWT/OIDC, autorização, RLS, limites e métricas
de aplicação, mas ainda depende de TLS no edge, WAF, rate limiting distribuído,
egress proxy, secrets manager, backup/DR e SIEM antes de exposição pública.
