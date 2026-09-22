# Provisionamento interno de identidade

O provisionamento de acesso OIDC é uma operação local, auditável e não é um
endpoint HTTP. A identidade externa é sempre a combinação estável de issuer e
subject; e-mail não é chave de autorização.

## Pré-condições

- A autenticação OIDC do usuário já foi validada e o acesso ao tenant retornou
  `403` por ausência de membership.
- O operador confirmou que se trata do usuário de validação autorizado, e não
  de uma identidade anteriormente exposta durante diagnóstico.
- A migration `018_persist_viewer_role` está aplicada.
- O request fica em arquivo regular, pertencente ao operador, com modo `600`.
- `external_issuer` é exatamente o valor canônico do claim JWT `iss`, inclusive
  esquema HTTPS e barra final quando presentes. O comando não normaliza issuer:
  um hostname isolado e uma URL canônica são identidades distintas e o primeiro
  não autorizará um token emitido pelo segundo.

O arquivo privado contém somente o contrato abaixo e nunca deve ser versionado:

```json
{
  "external_issuer": "<configured issuer>",
  "external_subject": "<provider subject>",
  "tenant_id": "<authorized tenant>",
  "role": "VIEWER",
  "operator_actor": "SYSTEM_OPERATOR"
}
```

O primeiro passo é sempre validar sem escrita:

```bash
PYTHONPATH=src .venv/bin/python -m ribeira_platform.identity_admin provision \
  --request-file ~/.config/ribeira/provisioning-request.json --dry-run
```

Após revisão humana do resultado, execute o mesmo comando sem `--dry-run`.
Ele cria, na mesma transação, a identidade externa quando ausente, uma única
membership `ACTIVE` de `VIEWER` e o evento
`IDENTITY_MEMBERSHIP_PROVISIONED` no `audit_log`.

Repetir uma membership `VIEWER` já ativa é idempotente. Memberships com papel
distinto, desativadas ou revogadas são conflitos explícitos e nunca são
substituídas ou reativadas pelo comando.

Depois do provisionamento, repita o `--dry-run`: o resultado deve indicar
`MEMBERSHIP=EXISTS` e `AUDIT=NOT_WRITTEN`. Se o issuer inicial não corresponder
exatamente ao `iss` validado, revogue essa membership pelo fluxo controlado e
provisione a identidade canônica; não edite nem apague o histórico.

O papel `VIEWER` permite leitura de propriedade/geoespacial e de decisões,
além de envio de feedback autenticado; não concede alteração de propriedade,
aprovação de limites, administração de tenant ou privilégio de plataforma. O
comando não recebe issuer, subject ou tenant como argumentos
de linha de comando e não imprime esses identificadores, tokens ou segredos.

## Revogação controlada

Revogação preserva `identity_user`, a membership e o audit de provisioning. O
arquivo privado, também modo `600`, exige o guardrail `expected_role`:

```json
{
  "external_issuer": "<configured issuer>",
  "external_subject": "<provider subject>",
  "tenant_id": "<authorized tenant>",
  "expected_role": "VIEWER",
  "operator_actor": "SYSTEM_OPERATOR"
}
```

Valide primeiro sem escrita:

```bash
PYTHONPATH=src .venv/bin/python -m ribeira_platform.identity_admin revoke \
  --request-file ~/.config/ribeira/revoke-membership-request.json --dry-run
```

Sem `--dry-run`, somente a membership `ACTIVE` do tenant e papel esperado faz
a transição para `REVOKED`, junto ao evento
`IDENTITY_MEMBERSHIP_REVOKED`. Repetir uma membership já revogada é
idempotente e não cria um segundo audit. A revogação nunca exclui identity,
membership, histórico ou desabilita RLS.
