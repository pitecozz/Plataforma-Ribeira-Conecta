-- Never remove an in-use or externally extended viewer role during rollback.
DO $$
DECLARE
  viewer_role uuid := '00000000-0000-5000-8000-000000000018';
  property_permission uuid := '00000000-0000-5000-8000-000000000181';
  geospatial_permission uuid := '00000000-0000-5000-8000-000000000182';
BEGIN
  IF EXISTS (SELECT 1 FROM tenant_membership WHERE role_id = viewer_role) THEN
    RAISE EXCEPTION 'cannot rollback 018 while the seeded VIEWER role has memberships';
  END IF;
  IF EXISTS (
    SELECT 1 FROM role_permission
    WHERE role_id = viewer_role
      AND permission_id NOT IN (property_permission, geospatial_permission)
  ) THEN
    RAISE EXCEPTION 'cannot rollback 018 while the seeded VIEWER role has external permissions';
  END IF;
  IF EXISTS (
    SELECT 1 FROM role_permission
    WHERE role_id <> viewer_role
      AND permission_id IN (property_permission, geospatial_permission)
  ) THEN
    RAISE EXCEPTION 'cannot rollback 018 while seeded permissions are assigned to another role';
  END IF;
END
$$;

DELETE FROM role_permission
WHERE role_id = '00000000-0000-5000-8000-000000000018'
  AND permission_id IN (
    '00000000-0000-5000-8000-000000000181',
    '00000000-0000-5000-8000-000000000182'
  );
DELETE FROM iam_role
WHERE id = '00000000-0000-5000-8000-000000000018'
  AND code = 'VIEWER';
DELETE FROM iam_permission
WHERE id IN (
  '00000000-0000-5000-8000-000000000181',
  '00000000-0000-5000-8000-000000000182'
);
