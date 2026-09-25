DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM iam_permission
    WHERE code = 'decision:evaluate'
      AND id <> '00000000-0000-5000-8000-000000000421'
  ) THEN
    RAISE EXCEPTION 'cannot rollback 042 because decision:evaluate has an unexpected identifier';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM role_permission mapping
    WHERE mapping.permission_id = '00000000-0000-5000-8000-000000000421'
      AND mapping.role_id NOT IN (
        SELECT id
        FROM iam_role
        WHERE code IN (
          'TENANT_ADMIN',
          'MANAGER',
          'ANALYST',
          'AGRONOMIST',
          'TECHNICIAN',
          'OPERATOR'
        )
      )
  ) THEN
    RAISE EXCEPTION 'cannot rollback 042 while decision:evaluate is assigned outside the managed roles';
  END IF;
END
$$;

DELETE FROM role_permission
WHERE permission_id = '00000000-0000-5000-8000-000000000421';

DELETE FROM iam_permission
WHERE id = '00000000-0000-5000-8000-000000000421'
  AND code = 'decision:evaluate';
