# ADR-0011 — CDSE S3 autenticado com download local controlado

## Status

Accepted — Phase 1C.1.

## Contexto

O catálogo STAC oficial do CDSE retorna assets Sentinel-2 L2A como referências
`s3://eodata/...`. A fase anterior catalogava esses assets, mas não podia
processá-los sem acesso autenticado. NDVI precisa apenas das bandas RED e NIR e
não deve baixar o produto Sentinel inteiro.

## Decisão

Usar boto3 com endpoint HTTPS fixo e validado do CDSE, bucket `eodata`, SigV4,
path-style addressing, timeout/retry limitado e credenciais fornecidas por uma
abstração de infraestrutura. O adapter baixa somente os assets semanticamente
resolvidos para RED/NIR, em streaming para arquivo temporário, aplica limites,
calcula SHA-256 local e grava atomicamente no `ObjectStoragePort` tenant-scoped.

Escolhemos download local controlado em vez de configurar GDAL para leitura
remota nesta primeira validação. Isso reduz o número de camadas de rede e torna
bytes, checksum, cleanup e falhas reproduzíveis. Leitura remota por ranges pode
ser avaliada depois sem mudar o contrato de provenance.

## Alternativas

- GDAL/Rasterio via `/vsis3/`: menor download potencial, mas exige configuração
  adicional de credenciais, ranges, cache e observabilidade antes de validar o
  primeiro fluxo real.
- Process API do CDSE: não atende o objetivo desta fase de provar acesso aos
  assets STAC existentes e seria uma mudança de provider/fluxo.
- Cliente S3 próprio: rejeitado por duplicar assinatura, retries e parsing de
  erros de uma biblioteca madura.

## Consequências

O primeiro processamento consome disco e transfere as bandas completas,
respeitando quotas. Credenciais nunca entram no domínio, repositório, logs,
fixtures ou migrations. Falhas de credencial permanecem observáveis e bloqueiam
o cálculo em vez de fabricar um resultado.
