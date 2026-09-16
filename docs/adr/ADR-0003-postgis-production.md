# ADR-0003: PostGIS como alvo geoespacial

- Status: accepted
- Data: 2026-09-16

PostGIS é o banco de produção por suportar geometria, CRS e índices espaciais.
SQLite é somente o backend local dependency-free do bootstrap e não deve receber
consultas espaciais de produção.
