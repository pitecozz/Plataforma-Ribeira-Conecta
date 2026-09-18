-- Keep migration 009 immutable: application access was added after it ran.
-- RLS and its tenant policy remain enforced by migration 009.
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE derived_product_dependency TO ribeira_app;
