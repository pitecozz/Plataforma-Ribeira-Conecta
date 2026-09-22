-- Farm360 viewers need the confirmed Digital Twin inventory, but no asset mutation.
INSERT INTO iam_permission (id, code, description)
VALUES (
  '00000000-0000-5000-8000-000000000331',
  'asset:read',
  'Read confirmed tenant Digital Twin assets'
)
ON CONFLICT (code) DO NOTHING;

INSERT INTO role_permission (role_id, permission_id)
SELECT role.id, permission.id
FROM iam_role AS role
JOIN iam_permission AS permission ON permission.code = 'asset:read'
WHERE role.code = 'VIEWER'
ON CONFLICT DO NOTHING;
