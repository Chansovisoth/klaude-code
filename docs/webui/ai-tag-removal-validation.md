# Individual AI tag removal

Details → Edit tags now gives AI chips the same remove control as manual chips.
Removing one changes only the local draft. Cancel restores it; Save tags uses
the existing review dialog and includes the exact AI removals in its summary.
Cancelling that confirmation or rejecting the save retains the draft.

The existing `tags` operation accepts an optional `remove_ai_tags` list of at most
20 exact saved labels. Preparation checks the list and artifact revision. The
worker passes the reviewed list into the existing store transaction, which
rechecks the revision and labels before updating manual tags, removing selected
AI tags and pruning their provenance atomically. Remaining AI tags retain their
original provenance and are never converted into manual tags by removal.
Existing callers that omit the new field retain their previous behavior.

The public `library_ai_tag_edit` capability prevents a refreshed frontend from
silently submitting an incomplete edit to a still-running older host. Such hosts
keep the draft and show restart guidance. No database migration is required.

## Validation

- Artifact, image-tag and reviewed-management unit regressions: 96 passed.
- New cases cover one/all AI removals, unchanged manual tags and retained
  provenance, invalid/unrecognized/oversized lists, stale worker revisions and
  atomic rejection without partial manual-tag changes.
- The isolated inspector browser probe passed individual removal, draft Cancel,
  confirmation Cancel with draft retention, older-host guidance, confirmed save,
  unchanged manual tags and retained AI provenance. It also passed the existing
  review/selection/failure checks and eight light/dark layouts at
  320/390/768/1440px, with zero browser exceptions.
- Focused mypy (three source files), Ruff, JavaScript syntax and diff checks passed.

All checks used temporary stores and local protocol fixtures. The existing
managed host was not restarted; it needs a restart to load the new backend field
and capability before individual AI removals can be saved there.
