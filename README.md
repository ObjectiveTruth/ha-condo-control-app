# Condo Control for Home Assistant

[![Validate](https://github.com/ObjectiveTruth/ha-condo-control-app/actions/workflows/validate.yml/badge.svg)](https://github.com/ObjectiveTruth/ha-condo-control-app/actions/workflows/validate.yml)

Track packages **still waiting at concierge** with your Condo Control resident account. Pickup status comes directly from Condo Control, including when another household member collects a parcel.

An unofficial community integration. Not affiliated with or endorsed by Condo Control.

## Features

- GUI setup with a property picker, including when your account has only one condo.
- A separate device for each resident account and selected property.
- Add another resident with their own credentials, or add the same account again for another property.
- Set polling during initial GUI setup or change it later, independently per account/property device: 1 to 1440 minutes, default 5 minutes. All entities for an entry share one request per poll.
- Package count, pickup indicator, oldest outstanding arrival time, last successful update, and manual refresh.
- Package references, descriptions, arrival dates, and pickup flags available as sensor attributes.
- Automatic session renewal and Home Assistant reauthentication when credentials stop working.
- Connection failures preserve the last valid reading and its timestamp. A separate diagnostic indicator reports whether the latest update succeeded.

## Install using HACS

Requires Home Assistant **2026.9 or newer** and a Condo Control account with package access.

1. In HACS, open the menu and choose **Custom repositories**.
2. Add `https://github.com/ObjectiveTruth/ha-condo-control-app` with type **Integration**.
3. Download **Condo Control** and restart Home Assistant.
4. Open **Settings → Devices & services → Add integration → Condo Control**.
5. Enter your Condo Control email and password.
6. Select your condo from the account's properties. This confirmation appears even if there is only one.
7. Optionally set a resident display name, choose the polling interval, and confirm the property's time zone.

Add another account using **Add entry** on the Condo Control integration. Each account/property pair becomes its own device. Duplicate pairs are rejected. No YAML is required.

This repository can be installed as a HACS custom repository; it has not been accepted into the HACS default catalog.

For manual installation, copy `custom_components/condo_control` into your Home Assistant `config/custom_components` directory and restart.

## Entities

All six entities are enabled by default. They share the same polling results, so enabling them all adds no scheduled API requests. Individual entities can be disabled in Home Assistant.

| Entity | Meaning |
| --- | --- |
| **Packages waiting** | Number of returned records with `IsPickedUp=false` |
| **Package waiting** | On when the count is greater than zero |
| **Oldest waiting package received** | Arrival timestamp of the oldest outstanding record; unknown when none are waiting |
| **Last successful update** | Most recent successful package poll; retains that timestamp during outages |
| **Last update successful** | Whether the latest API update succeeded; off when showing cached data after an error |
| **Refresh** | Request an immediate refresh using the shared coordinator |

The **Packages waiting** sensor includes these attributes:

```yaml
property: Harbour Example
units: ["101"]
returned_records: 2
picked_up_records: 1
packages:
  - reference: 501
    description: Small box stored at parcel desk
    received_at: "2026-09-25T13:38:00"
    is_picked_up: false
  - reference: 502
    description: Envelope
    received_at: "2026-09-24T12:00:00"
    is_picked_up: true
```

These are illustrative records, not real resident data. Attributes contain all records returned by the endpoint, including collected ones. Descriptions are preserved because courier, recipient, and storage details are not separate structured fields in this endpoint.

Package detail attributes are excluded from Home Assistant Recorder history to reduce storage and avoid retaining descriptions indefinitely. They remain visible in the current entity state. The count and timestamp entities retain normal history. A single latest snapshot, including descriptions, is stored locally in Home Assistant so the last valid reading survives restarts. It is deleted when the integration entry is removed.

Change the interval or time zone using **Configure** on the integration entry. These settings apply only to that account/property device; other devices keep their own settings. Changing options reloads that entry. Authentication tokens are retained in memory and renewed when rejected; the integration does not log passwords, tokens, or response bodies. Credentials are stored in Home Assistant's standard configuration-entry storage, so protect your Home Assistant configuration and backups. Downloadable diagnostics exclude credentials and personal package details.

## On failed updates

Once a valid reading exists, the count, pickup indicator, package details, and oldest-package timestamp keep that reading through network errors, malformed responses, and authentication failures. **Last successful update** does not advance; **Last update successful** turns off. The same snapshot is restored after a restart if the API is still unavailable. There is no automatic stale timeout or forced reset to zero: users can decide what freshness their dashboards and automations require. Before any successful reading, the entities remain unavailable while setup retries. Invalid credentials trigger the usual Home Assistant reauthentication flow.

## What the count means

- It counts **package log records**, which may each describe more than one physical box.
- It reflects what concierge has recorded, with up to the configured polling delay.
- It is scoped to the signed-in resident's permissions. A spouse collecting that resident's parcel changes the existing record. Parcels addressed to a spouse may require their own account unless the building enables household sharing.
- If two accounts can see the same parcel, summing their counts can double-count it. Household aggregation should deduplicate by property and package reference.
- Observed API results cover roughly a month. The endpoint has no documented pagination or date controls, and inclusion of older outstanding parcels has not been established. This integration treats the endpoint's list as the current source of truth and does not infer pickups from disappearing emails.
- API dates can lack a timezone offset. The timestamp sensor interprets them in the configured **property time zone**, initially your Home Assistant time zone. Raw attributes preserve the supplied offset/absence of offset.
- Two-factor challenge handling is not implemented in this release. If the login API requests verification, setup reports this explicitly. Do not disable account security just to use the integration.

The API is documented by Condo Control, but its availability and resident permissions may differ between buildings. This integration has initially been verified against one real resident account, with additional scenarios covered by automated tests.

## Development and testing

Use Python 3.14.2+ and [uv](https://docs.astral.sh/uv/):

```sh
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

Tests use Home Assistant Core and fabricated API responses. They exercise GUI setup, property selection, multiple residents, duplicate prevention, options, reauthentication, device registration, pickup changes, outages, and response validation.

For a read-only live smoke test of the same API client:

```sh
uv run python scripts/check_account.py
```

The script prompts for credentials without echoing the password, lists accessible properties, and prints aggregate package status. It does not save credentials or change Condo Control data.

To test the full GUI without restarting your production home, use a separate Home Assistant instance and copy this integration into its `custom_components` directory. Never commit `.storage`, live credentials, or real API fixtures.

CI runs tests, Ruff, Home Assistant hassfest, and HACS validation. Public-release work should include testing against another resident/property and implementing any additional authentication challenges encountered.

## API references

- [Condo Control API index](https://app.condocontrol.com/api10)
- [Login](https://app.condocontrol.com/api10/Help/Api/POST-api-Users-Login)
- [Property selection](https://app.condocontrol.com/api10/Help/Api/GET-api-Users-Workspace_id_objectType_objectID)
- [Package list](https://app.condocontrol.com/api10/Help/Api/GET-api-Package-PackageList)

## License

MIT. The included package icon is original artwork for this community integration, not an official Condo Control logo.
