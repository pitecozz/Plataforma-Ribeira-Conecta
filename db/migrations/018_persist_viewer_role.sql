-- Persist the least-privileged Farm 360 reader role using deterministic keys.
-- Existing roles or permissions with the same stable codes are never replaced.
INSERT INTO iam_role (id, code, description)
VALUES ('00000000-0000-5000-8000-000000000018', 'VIEWER', 'Read-only Farm 360 viewer')
ON CONFLICT (code) DO NOTHING;

INSERT INTO iam_permission (id, code, description)
VALUES
  ('00000000-0000-5000-8000-000000000181', 'property:read', 'Read tenant properties and portfolio'),
  ('00000000-0000-5000-8000-000000000182', 'geospatial:read', 'Read Farm 360 geospatial products and tiles')
ON CONFLICT (code) DO NOTHING;

INSERT INTO role_permission (role_id, permission_id)
SELECT role.id, permission.id
FROM iam_role AS role
JOIN iam_permission AS permission
  ON permission.code IN ('property:read', 'geospatial:read')
WHERE role.code = 'VIEWER'
ON CONFLICT DO NOTHING;
