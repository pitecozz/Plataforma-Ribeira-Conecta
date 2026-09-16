# ADR-0006: Migrations versionadas com checksum

- Status: accepted
- Data: 2026-09-16

O runner aplica arquivos numerados em ordem, registra SHA-256 em
`schema_migrations` e usa advisory lock. Uma migration aplicada cujo checksum
mudou falha explicitamente. Alterações futuras devem criar novo arquivo; cada
migration possui down quando rollback é tecnicamente possível. `clean` só pode
ser executado em desenvolvimento com flag explícita.
