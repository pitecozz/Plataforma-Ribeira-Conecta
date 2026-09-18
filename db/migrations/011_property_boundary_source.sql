-- Boundary provenance is optional for legacy properties and explicit for new ones.
ALTER TABLE property ADD COLUMN IF NOT EXISTS boundary_source text;
