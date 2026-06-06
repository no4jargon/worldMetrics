from __future__ import annotations

import argparse
from pathlib import Path

from app.connectors.factory import build_real_connectors
from app.live.factory import build_personal_tracker_connectors
from app.live.source_registry import DEFAULT_SOURCE_CONFIGS
from app.pipelines.build_snapshots import build_snapshots


def run(output_dir: Path | None = None) -> None:
    build_snapshots(output_dir=output_dir)


def run_real(
    output_dir: Path | None = None,
    fixture_paths: dict[str, Path | str] | None = None,
    source_urls: dict[str, Path | str] | None = None,
) -> None:
    connectors = build_real_connectors(fixture_paths=fixture_paths, source_urls=source_urls)
    build_snapshots(output_dir=output_dir, connectors=connectors)


def run_personal_tracker(
    output_dir: Path | None = None,
    fixture_paths: dict[str, Path | str] | None = None,
    source_urls: dict[str, Path | str] | None = None,
) -> None:
    trace_messages: list[str] = []
    connectors = build_personal_tracker_connectors(
        fixture_paths=fixture_paths,
        source_urls=source_urls,
        trace_messages=trace_messages,
    )
    build_snapshots(output_dir=output_dir, connectors=connectors)
    for message in trace_messages:
        print(message)


def run_refresh_dev(
    months: int = 60,
    db_path: Path | None = None,
    output_dir: Path | None = None,
    reset: bool = False,
    end_period: str | None = None,
) -> None:
    from app.pipelines.local_refresh import refresh_local_database
    from app.storage.sqlite_store import DEFAULT_DB_PATH

    refresh_local_database(
        months=months,
        db_path=db_path or DEFAULT_DB_PATH,
        output_dir=output_dir,
        reset=reset,
        end_period=end_period,
    )


def _personal_tracker_fixture_paths(fixtures_dir: Path | None) -> dict[str, Path] | None:
    if fixtures_dir is None:
        return None
    fixture_paths: dict[str, Path] = {}
    for config in DEFAULT_SOURCE_CONFIGS:
        fixture_paths[config.dataset_code] = fixtures_dir / f'{config.dataset_code}.json'
    return fixture_paths


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog='world-metrics')
    subparsers = parser.add_subparsers(dest='command')

    personal_tracker_parser = subparsers.add_parser('personal-tracker')
    personal_tracker_parser.add_argument('--output-dir', type=Path, default=None)
    personal_tracker_parser.add_argument('--fixtures-dir', type=Path, default=None)

    extract_parser = subparsers.add_parser('extract')
    extract_parser.add_argument('--targets-file', type=Path, required=True)
    extract_parser.add_argument('--output-dir', type=Path, default=Path('artifacts/extractions'))
    extract_parser.add_argument('--headed', action='store_true')

    refresh_parser = subparsers.add_parser('refresh-dev')
    refresh_parser.add_argument('--months', type=int, default=60)
    refresh_parser.add_argument('--db-path', type=Path, default=None)
    refresh_parser.add_argument('--output-dir', type=Path, default=None)
    refresh_parser.add_argument('--reset-db', action='store_true')
    refresh_parser.add_argument('--end-month', default=None, help='Optional YYYY-MM month used as the end of the requested window')

    args = parser.parse_args(argv)
    if args.command == 'personal-tracker':
        run_personal_tracker(
            output_dir=args.output_dir,
            fixture_paths=_personal_tracker_fixture_paths(args.fixtures_dir),
        )
        return

    if args.command == 'extract':
        from app.extractors.models import load_target_configs
        from app.extractors.playwright_extractor import PlaywrightMetricExtractor, write_runs_json

        targets = load_target_configs(args.targets_file)
        extractor = PlaywrightMetricExtractor(output_dir=args.output_dir, headed=args.headed)
        runs = [extractor.extract_target(target) for target in targets]
        write_runs_json(runs, args.output_dir)
        for run_result in runs:
            print(run_result.model_dump_json())
        return

    if args.command == 'refresh-dev':
        run_refresh_dev(
            months=args.months,
            db_path=args.db_path,
            output_dir=args.output_dir,
            reset=args.reset_db,
            end_period=args.end_month,
        )
        return

    run()


if __name__ == '__main__':
    main()
