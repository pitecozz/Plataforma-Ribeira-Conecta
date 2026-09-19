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

O papel `VIEWER` permite apenas `property:read` e `geospatial:read`; não
concede escrita, aprovação de limites, administração de tenant ou privilégio
de plataforma. O comando não recebe issuer, subject ou tenant como argumentos
de linha de comando e não imprime esses identificadores, tokens ou segredos.
