# Product decisions for review

Status: initial prototype approved for publication to GitHub `main` and user testing through HACS. Production installation is handled by the user. The implementation choices below remain open to feedback from testing.

## Agreed direction

- **Purpose:** show packages still waiting at concierge, based on Condo Control's pickup status. Someone else collecting a parcel must be reflected when concierge records it.
- **Distribution:** an unofficial Home Assistant custom integration installed through HACS, hosted in `ObjectiveTruth/ha-condo-control-app`.
- **Accounts:** each set of credentials gets a separate device with sensors. For multiple condos, each account/property pair gets a separate entry/device so properties remain distinguishable.
- **GUI:** email/password login followed by a property selector that is shown even when there is only one property.
- **Polling:** configurable during initial GUI setup and later through Configure, independently for each account/property device. All entities on that device share its polling interval.
- **Enabled entities:** all six entities are enabled by default. Users can disable individual entities in Home Assistant if desired.
- **Failed updates:** preserve the last valid reading. Do not replace it with zero or unavailable after a successful sample. Keep the last-success timestamp unchanged, letting users decide what freshness they require.

## Implementation choices to review

| Area | Current prototype behavior | Reason / tradeoff |
| --- | --- | --- |
| Display name | **Condo Control**; domain `condo_control` | Matches the service being connected; the repository suffix does not appear in Home Assistant |
| Device name | Resident name + condo name; optional resident name override | Distinguishes people and properties; existing device/entity names can also be renamed in HA |
| Multiple condos | Add another entry using the same credentials and choose another property | Independent configuration and polling per property; no complex nested account editor |
| Multiple units | All packages visible to that account at the selected property | No unsupported unit filtering inferred from descriptions |
| Setup validation | Login, fetch properties, select property, and verify a valid package response | Catches missing package permissions and malformed data before creating an entry |
| Initial interval | **5 minutes** | Reasonable starting balance between freshness and requests; not a vendor-prescribed limit |
| Interval range | **1–1440 minutes**, whole minutes | Prevents accidental second-by-second polling; both setup and options support changes |
| Request sharing | One package request per account/property per poll | All entities read the same snapshot; login/property/unit requests happen when establishing a session |
| Manual refresh | A Refresh button using HA's debounced coordinator | On-demand update without independent polling per entity |
| Count meaning | Outstanding **log records**, not guaranteed physical-box quantity | Some concierge records describe multiple boxes |
| Duplicate records | Deduplicate equal references; reject conflicting copies | Avoids double-counting without silently choosing an uncertain status |
| First-ever failure | No fabricated reading; setup retries, entities remain unavailable until a valid sample exists | There is no last reading to preserve yet |
| Failure after success | Keep all package values/details; freeze last-success timestamp | User-selected behavior |
| Failure indicator | Diagnostic binary sensor **Last update successful** goes off | Optional signal for automations; no automatic dashboard banner or stale timeout |
| Credential expiry | Renew session once; rejected credentials start HA's reauthentication flow | Preserves entity/device identity and existing readings |
| Restart during outage | Restore the last good snapshot from a local cache | Retains useful state even when starting offline |
| Stale-data expiry | **None** | Users decide via the last-success timestamp; retained data may be old |
| Sensor attributes | All API-returned packages: reference, description, received timestamp, pickup flag; property, units, returned count, picked-up count | Gives dashboards useful detail without extra API requests |
| Pickup time/person | Not exposed | The verified endpoint returns only a pickup boolean, not who collected it or when |
| Arrival timezone | Property timezone configurable, initially HA's timezone | API can return naive local timestamps; avoids pretending those are UTC |
| Historical storage | Full package-list attribute excluded from Recorder history; one latest snapshot cached locally | Reduces history bloat, while supporting restart recovery; descriptions still exist in current state/cache/backups |
| Removing an entry | Unload its entities and delete its snapshot cache | Removes that account's integration data; normal HA history follows HA retention |
| Diagnostics | Aggregate counts, interval, update success only | Excludes names, addresses, descriptions, credentials, tokens, references |
| Read/write scope | Login/session selection and read requests only | No package release, notifications, resident-setting changes, bookings, or account edits |
| Two-factor challenge | Explicitly unsupported in this first prototype | Needs verification of the challenge flow; no suggestion to disable security |
| Compatibility | HA **2026.9+** initially; tested with **2026.9.4** | Honest baseline; older releases can be tested before lowering the requirement |
| License | MIT | Proposed permissive community distribution license |
| Publication | HACS custom repository initially; default-catalog submission later | HACS installability and catalog acceptance are separate |

## Entities currently created per device

| Entity | Default behavior |
| --- | --- |
| Sensor: Packages waiting | Outstanding count, plus complete returned package list as attributes |
| Binary sensor: Package waiting | On when the retained count is greater than zero |
| Sensor: Oldest waiting package received | Timestamp; unknown when a valid response has no outstanding packages |
| Diagnostic sensor: Last successful update | Timestamp of the last valid API response |
| Diagnostic binary sensor: Last update successful | Off after a failure or when restored from cache until a fresh poll succeeds |
| Diagnostic button: Refresh | Requests a fresh snapshot |

All six entities are enabled by default. They share one snapshot, so enabling them all adds no scheduled API requests. The Refresh button requests an update only when pressed. Entities can be disabled individually in HA; disabling them does not alter the count's failure policy or the device's polling interval.

## Known source limitations

- The API currently returns recent history, observed at roughly one month. Its treatment of older outstanding packages remains unverified. The prototype assumes its response is the source of truth as requested.
- Household sharing permissions may overlap accounts. A household total is not currently created; adding such a total would require deduplication by property and reference.
- Pickup status only changes when staff records it, then on the next poll.
- One real resident account has been verified. Tests simulate multiple accounts and condos; broader real-world compatibility is not established yet.
- Other service data, such as bookings or service requests, has not been added. It should use separate entities with its own semantics when requested, rather than making package attributes an unstructured account dump.

## Suggested review order

1. Confirm the retained-value failure policy, including no expiry and survival across restarts.
2. Confirm full recent-history attributes versus outstanding packages only.
3. Confirm default/minimum polling and whether timezone belongs in initial setup or advanced options. Initial-setup polling configuration and enabling all six entities are agreed.
4. Confirm the initial scope, compatibility baseline, and publication/test sequence.

All unrequested implementation choices above are adjustable before the first release.
