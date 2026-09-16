# Scene selection policy

`SENTINEL2_L2A_LATEST_V1` is a versioned policy, not a universal truth. It
accepts an explicit search interval and max candidate count, orders candidates
by acquisition time, and can apply an explicitly configured cloud-cover limit.

The persisted search includes policy ID/version, candidates, rank, criteria,
rejection reason and selected scene. A missing cloud value is not treated as
zero and is not silently treated as a clear scene; with a cloud limit it is
rejected as `CLOUD_METADATA_UNKNOWN`. If no candidate remains, the result is
`NO_SCENE_FOUND`/`INCONCLUSIVE` and no scene is substituted outside the policy.
