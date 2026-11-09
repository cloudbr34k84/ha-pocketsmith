# Implementation follow-up — 9 November 2026

The nine gaps identified in the original review below have been implemented.
The complete custom/HACS rule inventory is now in
`custom_components/ha_pocketsmith/quality_scale.yaml` (17 done, 3 exempt).
This is an internal checklist, not an official Home Assistant quality-tier award.

## Implemented

- `action-setup`: registration in async_setup, actions retained on unload,
  loaded-entry validation, reset preconditions and serialized resets; the reset
  button uses the same validated action.
- `appropriate-polling`: fixed hourly polling, removed interval form/number
  platform, documented standard automation-based scheduling.
- `config-flow`: password selectors without prefilling the secret, complete
  reauth field description, preserved unrelated options when saving.
- `config-flow-test-coverage`: all flows, duplicate prevention, every displayed
  error followed by recovery, unique-ID assertions and HTTP validation tests.
- `docs-actions`: actual immediate reset behavior, prerequisites, field-free
  actions and response documented; translations and services updated.
- `docs-installation-instructions`: README and HACS metadata agree on HA 2026.3+.
- `docs-removal-instructions`: key revocation, uninstall files, retained
  progress/statistics and cleanup guidance documented.
- `entity-unique-id`: immutable IDs for account/category/rollup entities and
  idempotent, entry-scoped entity-registry migration. Conflicting records are
  preserved with a warning, never silently deleted.
- `test-before-setup`: 401/403 trigger authentication recovery, temporary errors
  remain retryable, removed duplicate error logging.

## Verification

96 tests passed on Python 3.14.8 / Home Assistant 2026.10.4 using
pytest-homeassistant-custom-component 0.13.318. Config-flow coverage is 100%
for both lines and branches (90 statements, 12 branches). CI uses the pinned
test dependencies and enforces the same coverage gate.

Command:

```sh
python -m pytest tests -q --tb=short --timeout=30 \
  --cov=custom_components.ha_pocketsmith.config_flow --cov-branch \
  --cov-report=term-missing --cov-fail-under=100
```

Python syntax, JSON/YAML parsing, changed translation sections, 20-rule
inventory and git diff whitespace checks passed. Tests use mocks; no live API
credentials or production configuration were used. Tests ran in an isolated
/tmp virtual environment outside the restricted sandbox because HA test cleanup
hung inside it. Hassfest and the HA 2026.3 minimum-version runtime matrix were
not executed locally. Existing hassfest CI remains enabled.

## Compatibility and remaining separate work

The polling number entity is retired; its old registry record may be removed
from the UI after reload. Stored custom intervals are ignored. No integration
reload/restart, release, commit or push was performed.

External recorder statistic IDs were deliberately not renamed by the entity
migration, preserving existing series. Their existing title-based naming can
still split external series after upstream renames; solving that requires a
separate recorder metadata migration. The pre-existing mixed-currency net-worth
calculation is also unchanged. Neither is represented as fixed by this work.

---

# Original review (historical findings before implementation)

# Bronze quality review

Reviewed 9 November 2026 against all 20 files in the supplied local `ha-integration-dev/HA Core and integrations/HA Integration quality scale/1. Bronze` directory, including its custom-integration scope note.

Revision: `670e8d60f1ed0a4d4d171e7746da55accbb609e3` (working tree clean before review). Version: 0.5.7. Scope: custom/HACS integration, not an official Core tier award.

**Result: not fully compliant. 8 source-review passes, 9 requirements with gaps, 3 not applicable.** Pass means supported by source inspection, not a claim of successful runtime testing.

## Complete checklist

Paths below are relative to `custom_components/ha_pocketsmith/` unless stated otherwise.

| Rule | Result | Evidence and required work |
|---|---|---|
| action-setup | Gap | `__init__.py:61` registers actions in `async_setup_entry`; line 68 removes them on unload. Add `async_setup`, register there, retain actions on entry unload. `actions.py:20–62` accesses runtime data without checking entry state and silently succeeds/returns `{}` with no entry. Validate a loaded entry before access or mutations and raise `ServiceValidationError` when unavailable. |
| appropriate-polling | Gap | One-hour default in `const.py` is reasonable for financial summaries, but `config_flow.py:45` exposes the interval as an options field, explicitly disallowed by the supplied rule. Use a developer-selected interval and document HA's standard custom polling automation. Review removal/migration of the number control too. |
| brands | Pass, custom scope | Local `brand/icon.png` and `icon@2x.png` have PNG signatures and dimensions 256×256 and 512×512; logos are present at 128×128 and 256×256. Local branding satisfies the supplied custom distribution scope on HA 2026.3+. No upstream brands PR is required for that scope. Older advertised HA support needs reconciliation; see installation row. Visual rendering was not tested. |
| common-modules | Pass | Coordinator is in `coordinator.py`; no integration-owned base entity class is misplaced. The rule explicitly says an integration without a base entity has nothing to move. Optional cleanup: consolidate duplicated device info into `entity.py`, removing platform imports from `sensor.py`. |
| config-flow | Gap | UI setup is enabled and connection data/options are separated. However `strings.json` lacks `config.step.reauth_confirm.data_description.developer_key`. Key fields use plain `str`, including a prefilled reconfiguration key; use password text selectors. Remove polling from the options form. |
| config-flow-test-coverage | Gap | Only backfill, coordinator and sensor test modules exist. Validation fixtures in `conftest.py` are not flow tests. Add user, duplicate, reauth, reconfigure and options tests, including each error followed by successful recovery and unique-ID assertions. Exercise the actual validation helper, including 401, 403, other HTTP errors, timeout and success. Measure and enforce 100% config-flow coverage. |
| dependency-transparency | N/A | `manifest.json` has an empty requirements list; there is no separately distributed integration-specific Python dependency. Recorder is an HA integration dependency. |
| docs-actions | Gap | README describes all three actions and summary response, but reset is described as deferring work until next startup. `actions.py:29–38` immediately invokes backfill after deleting progress. Align README and service descriptions with implemented behavior, including handling an already-running backfill. |
| docs-conditions | N/A | No integration-specific condition implementation. Standard template/state conditions in examples do not create such a requirement. |
| docs-high-level-description | Pass | README Overview explains PocketSmith, links its website and describes integration functionality. |
| docs-installation-instructions | Gap | Step-by-step HACS/manual/setup and API prerequisites exist, but README requires HA 2025.1 while `hacs.json` declares 2024.11.0. Local branding applies from 2026.3 per supplied scope. Establish and test the supported minimum, align metadata/docs, and document older-version branding behavior if retaining older support. API-key navigation instructions were not independently verified against the current PocketSmith UI. |
| docs-removal-instructions | Gap | README covers deleting the entry only. Explain revoking the dedicated PocketSmith API key when no longer needed and removing HACS/manual files if uninstalling. Explain persistence/cleanup of backfill storage and historical statistics; do not imply entry deletion erases all history. |
| docs-triggers | N/A | No integration-specific trigger implementation; standard state/numeric-state examples do not count. |
| entity-event-setup | Pass | All platform entities use `CoordinatorEntity` lifecycle handling; no custom constructor subscriptions or lifecycle overrides were found. |
| entity-unique-id | Gap | `sensor.py:123`, `:253`, `:345` include account/category title slugs. Rename upstream, then reload: the same API ID gets a different unique ID. Use immutable identifiers, and migrate existing entity-registry IDs so users retain entity IDs/history/customizations. Account statistics IDs must be reviewed alongside this migration. |
| has-entity-name | Pass | All 15 concrete entity classes set `_attr_has_entity_name = True`; entity names describe their role within the PocketSmith device. |
| runtime-data | Pass | `__init__.py:55` stores coordinator/backfill in `entry.runtime_data` with `PocketSmithConfigEntry = ConfigEntry[PocketSmithData]`; platforms read it. No integration runtime dictionary in `hass.data`. Typing improvement: replace `PocketSmithData.coordinator: object` with a forward reference guarded by TYPE_CHECKING and propagate the entry alias. Full strict typing is beyond Bronze. |
| test-before-configure | Pass | `_validate_developer_key` makes a real `/v2/me` request before entry creation; authentication, permissions, connection, timeout and unexpected errors return forms with errors. Recovery still needs tests under the coverage rule. |
| test-before-setup | Gap | First coordinator refresh correctly gates setup and 401 raises `ConfigEntryAuthFailed`. But `api.py:37` maps explicitly missing permissions (403) to retryable `UpdateFailed`; report the permanent/authentication problem appropriately. `coordinator.py:69–81` logs connection/timeout errors before raising, and `api.py:57` logs rate limiting before raising, contrary to the supplied no-log-and-raise requirement. Let HA report these failures. |
| unique-config-entry | Pass | `config_flow.py:75–76` uses a fixed domain unique ID and duplicate abort, enforcing the documented single-entry design. A manifest `single_config_entry` flag would make that design clearer but is not needed to establish duplicate prevention here. |

## Highest-priority corrections

1. Stabilize unique IDs with a registry migration. Existing tests explicitly expect title slugs, so replace those expectations with rename/reload invariance and migration checks.
2. Fix action registration lifetime and loaded-entry validation. Test availability before entry setup, after failed setup and after unload.
3. Add full config-flow tests and coverage enforcement, then fix forms and error classification.
4. Remove configurable polling from flows and reconcile documentation with actual behavior and supported HA versions.
5. Record every rule and justified exemption in `quality_scale.yaml` once evidence exists. Its absence is a tracking gap; do not mark all rules done before fixes and verification.

## Additional defects found during the review

- Polling changes are not applied immediately: `number.py:68–71` updates entry options only; the interval is read at setup, and no update listener reloads the entry or updates the coordinator. README's immediate-effect claim is false.
- Options submission replaces options with the submitted fields. The form omits `active_currency`, so saving options can discard the currency preference written by the select entity. Preserve unrelated options.
- Net worth sums balances in different currencies and changes only the unit label when selecting another currency (`sensor.py:432–448`). It does not convert monetary values. Either convert with a defined exchange-rate source or expose separate per-currency totals. This is outside the Bronze checklist but materially affects correctness.
- The test workflow uses Python 3.12 with unpinned test dependencies and no coverage gate. Pin a compatible HA/test-plugin combination and use the matching Python version; actual CI execution was not inspected.

## Verification and limits

Read all checklist rule summaries and the relevant requirements, the production setup/config flow/API/coordinator/entity/action code, manifest, strings, documentation, test inventory/fixtures and CI configuration. Checked local PNG signatures and dimensions. No live PocketSmith requests, entry reloads or production configuration changes were made.

Attempted `python3 -m pytest .../tests/ -q`: the environment has Python 3.14.8 but reports `No module named pytest`. No runtime test result or numeric coverage result is claimed. The missing config-flow tests and identified source defects already prevent a 100% compliance conclusion. Run the isolated test suite, config-flow coverage gate and hassfest on a supported dependency matrix before signing off.

This review adds only this report; production code remains unchanged.
