# Patna directory and demo catalog

## Discovery coverage

Dukaanly accepts any valid latitude and longitude. Nearby-shop discovery is a PostGIS query over the persisted `shops.location` geometry, using `ST_DWithin` for the selected 3 km, 5 km, or 10 km search radius and `ST_Distance` for returned distance and ordering. There is no neighbourhood preset constraint or hidden 5 km discovery cap.

The current directory import envelope is the Patna metropolitan bounding box `25.5500–25.6500` latitude and `85.0500–85.2500` longitude. This is an import-validation boundary, not a promise of delivery coverage throughout Patna. A shop is delivery-eligible only when it is an orderable, verified partner and falls inside the configured delivery radius.

## Listing provenance and orderability

Public directory candidates retain source, source ID, attribution, source URL, import batch and import timestamps. They are stored as `discovered`, have no owner, are non-orderable, and never receive demo catalog products. They cannot be used for cart or checkout operations.

Demo shops are explicitly marked `source=demo` and `source_attribution=Dukaanly Demo Catalog`; they are development fixtures rather than claims that a real business participates in Dukaanly.

## Import operations

Directory imports never run as part of application startup or demo catalog seeding. Run them explicitly in an environment with a configured database:

```powershell
cd backend
python -m app.cli.import_merchants --provider curated --dry-run
python -m app.cli.import_merchants --provider osm --dry-run
```

The curated provider carries per-listing attribution and source URLs. The OSM provider uses Overpass and requires attribution to OpenStreetMap contributors under ODbL. Observe provider rate limits and do not treat successful source discovery as merchant consent.

## Demo catalog report

`python -m app.db.seed_demo` is development-only and prints a report for each demo partner: category, active distinct-product count, inventory-record count, and whether both counts meet the 50-product minimum. The optional `--reset-stock` flag remains development-only and only resets known demo catalog records.
