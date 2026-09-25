INSERT INTO iam_permission (id, code, description)
VALUES (
  '00000000-0000-5000-8000-000000000421',
  'decision:evaluate',
  'Evaluate rules and persist decisions, alerts and actions'
)
ON CONFLICT (code) DO NOTHING;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM iam_permission
    WHERE id = '00000000-0000-5000-8000-000000000421'
      AND code = 'decision:evaluate'
  ) THEN
    RAISE EXCEPTION 'decision:evaluate already exists with an unexpected identifier';
  END IF;

END
$$;

INSERT INTO role_permission (role_id, permission_id)
SELECT role.id, '00000000-0000-5000-8000-000000000421'
FROM iam_role AS role
WHERE role.code IN (
  'TENANT_ADMIN',
  'MANAGER',
  'ANALYST',
  'AGRONOMIST',
  'TECHNICIAN',
  'OPERATOR'
)
ON CONFLICT DO NOTHING;
