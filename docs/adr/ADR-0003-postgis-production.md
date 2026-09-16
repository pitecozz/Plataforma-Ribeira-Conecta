# ADR-0003: PostGIS como alvo geoespacial

- Status: accepted
- Data: 2026-09-16

PostGIS é o banco de produção por suportar geometria, CRS e índices espaciais.
SQLite é somente o backend local de testes rápidos e não deve receber consultas
espaciais de produção. A execução desta fase foi verificada em PostgreSQL 16 com
PostGIS 3.4; o caminho de container é reproduzível por `docker-compose.yml`, mas
depende de Docker disponível no ambiente.
