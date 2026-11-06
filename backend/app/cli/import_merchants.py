"""
Command-line interface for running the merchant import pipeline and safe batch rollbacks.

Usage Examples:
    # Dry-run validation of Patna curated extract:
    python -m app.cli.import_merchants --provider curated --dry-run

    # Execute actual import of candidate records:
    python -m app.cli.import_merchants --provider curated --max-records 10

    # Query live OpenStreetMap Overpass with category filter in dry-run mode:
    python -m app.cli.import_merchants --provider osm --categories grocery,chemist --dry-run

    # Safely archive an import batch (production-recommended):
    python -m app.cli.import_merchants --rollback-batch <BATCH_UUID> --mode archive

    # Delete an unverified staging import batch:
    python -m app.cli.import_merchants --rollback-batch <BATCH_UUID> --mode delete
"""

import asyncio
import argparse
import json
import logging
import sys
import uuid

from app.db.session import async_session_maker
from app.services.importer.base import AreaConfig
from app.services.importer.curated_provider import CuratedDatasetProvider
from app.services.importer.osm_provider import OSMOverpassProvider
from app.services.importer.pipeline import MerchantImportService, rollback_import_batch

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("import_merchants_cli")

def parse_args():
    parser = argparse.ArgumentParser(description="Dukaanly Candidate Merchant Directory Importer & Batch Manager")
    parser.add_argument(
        "--provider",
        choices=["curated", "osm"],
        default="curated",
        help="Listing provider adapter (default: curated regional extract)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and simulate import without making any database writes"
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=50,
        help="Maximum candidate listings to process (default: 50)"
    )
    parser.add_argument(
        "--categories",
        type=str,
        default="grocery,supermarket,convenience,chemist,bakery,dairy",
        help="Comma-separated retail category allowlist"
    )
    parser.add_argument(
        "--city",
        type=str,
        default="Patna",
        help="Target city (default: Patna)"
    )
    parser.add_argument(
        "--state",
        type=str,
        default="Bihar",
        help="Target state (default: Bihar)"
    )
    parser.add_argument(
        "--min-lat",
        type=float,
        default=25.5500,
        help="Minimum latitude bounding box"
    )
    parser.add_argument(
        "--max-lat",
        type=float,
        default=25.6500,
        help="Maximum latitude bounding box"
    )
    parser.add_argument(
        "--min-lon",
        type=float,
        default=85.0500,
        help="Minimum longitude bounding box"
    )
    parser.add_argument(
        "--max-lon",
        type=float,
        default=85.2500,
        help="Maximum longitude bounding box"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output final report as raw JSON"
    )
    parser.add_argument(
        "--rollback-batch",
        type=str,
        default=None,
        help="UUID of the import batch to roll back or archive"
    )
    parser.add_argument(
        "--mode",
        choices=["archive", "delete"],
        default="archive",
        help="Rollback mode: 'archive' (sets status=archived) or 'delete' (removes unreferenced rows)"
    )
    return parser.parse_args()

async def run_cli():
    args = parse_args()

    # Handle Batch Rollback workflow
    if args.rollback_batch:
        try:
            batch_uuid = uuid.UUID(args.rollback_batch)
        except ValueError:
            print(f"Error: Invalid UUID format for --rollback-batch: {args.rollback_batch}")
            sys.exit(1)

        print("=" * 65)
        print(f" DUKAANLY MERCHANT BATCH ROLLBACK ({args.mode.upper()})")
        print("=" * 65)
        print(f" Batch ID: {batch_uuid}")
        print(f" Mode:     {args.mode} (Strict concurrency & FK verification)")
        print("-" * 65)

        async with async_session_maker() as session:
            try:
                res = await rollback_import_batch(db=session, batch_id=batch_uuid, mode=args.mode)
                if args.json:
                    print(json.dumps(res, indent=2))
                else:
                    print(f" Success: Batch status set to '{res['status']}'.")
                    print(f" Affected Candidate Shops: {res['affected_shops']}")
                    print(f" Timestamp: {res['timestamp']}")
                print("=" * 65)
                return
            except Exception as e:
                print(f" Rollback Aborted / Failed: {e}")
                print("=" * 65)
                sys.exit(1)

    # Standard Import workflow
    area = AreaConfig(
        name=f"{args.city} Pilot Envelope",
        city=args.city,
        state=args.state,
        min_lat=args.min_lat,
        max_lat=args.max_lat,
        min_lon=args.min_lon,
        max_lon=args.max_lon,
    )

    categories = [c.strip().lower() for c in args.categories.split(",") if c.strip()]

    if args.provider == "osm":
        provider = OSMOverpassProvider()
    else:
        provider = CuratedDatasetProvider()

    mode_label = "DRY-RUN (Simulated, 0 DB writes)" if args.dry_run else "LIVE IMPORT"
    print("=" * 65)
    print(f" DUKAANLY MERCHANT DIRECTORY PIPELINE -- {mode_label}")
    print("=" * 65)
    print(f" Provider:   {provider.provider_name} ({provider.attribution})")
    print(f" Envelope:   {area.city}, {area.state} [{area.min_lat}, {area.min_lon}] to [{area.max_lat}, {area.max_lon}]")
    print(f" Categories: {', '.join(categories)}")
    print(f" Max Limit:  {args.max_records}")
    print("-" * 65)

    async with async_session_maker() as session:
        service = MerchantImportService(
            db=session,
            provider=provider,
            area=area,
            allowed_categories=categories,
        )

        summary = await service.run_import(
            dry_run=args.dry_run,
            max_records=args.max_records,
        )

    if args.json:
        print(json.dumps(summary.to_dict(), indent=2))
        return

    print("\n" + "=" * 65)
    print(f" IMPORT SUMMARY ({'DRY-RUN COMPLETE' if args.dry_run else 'PERSISTENCE COMPLETE'})")
    print("=" * 65)
    print(f" Batch Identifier:          {summary.batch_id}")
    print(f" Total Candidates Evaluated: {summary.total_fetched}")
    print(f" Accepted & Validated:       {summary.accepted}")
    print(f" Duplicates (Provider ID):   {summary.duplicates_source}")
    print(f" Duplicates (Spatial <= 25m): {summary.duplicates_spatial}")
    print(f" Rejected (Outside Bounds):  {summary.rejected_bounds}")
    print(f" Rejected (Category):        {summary.rejected_category}")
    if summary.errors:
        print(f" Errors Encountered:         {len(summary.errors)}")
        for err in summary.errors:
            print(f"   ! {err}")
    print("=" * 65)
    print(" Candidate listings are marked 'discovered' and non-orderable.")
    print(" Merchant verification & KYC required before enabling checkout.")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(run_cli())
