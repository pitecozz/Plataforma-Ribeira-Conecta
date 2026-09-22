-- Do not remove an active viewer capability or a permission extended elsewhere.
DO $$
DECLARE
  viewer_role uuid := '00000000-0000-5000-8000-000000000018';
  asset_permission uuid := '00000000-0000-5000-8000-000000000331';
BEGIN
  IF EXISTS (SELECT 1 FROM tenant_membership WHERE role_id = viewer_role) THEN
    RAISE EXCEPTION 'cannot rollback 033 while VIEWER memberships are active';
  END IF;
  IF EXISTS (
    SELECT 1 FROM role_permission
    WHERE permission_id = asset_permission AND role_id <> viewer_role
  ) THEN
    RAISE EXCEPTION 'cannot rollback 033 while asset:read is assigned to another role';
  END IF;
END
$$;

DELETE FROM role_permission
WHERE role_id = '00000000-0000-5000-8000-000000000018'
  AND permission_id = '00000000-0000-5000-8000-000000000331';

DELETE FROM iam_permission
WHERE id = '00000000-0000-5000-8000-000000000331'
  AND code = 'asset:read';
