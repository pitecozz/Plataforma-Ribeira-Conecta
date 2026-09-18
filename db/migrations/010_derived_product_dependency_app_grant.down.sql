-- Restore the privilege state established by migration 009 without touching data.
REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE derived_product_dependency FROM ribeira_app;
