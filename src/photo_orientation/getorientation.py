import argparse
from pathlib import Path

from ansitable import ANSITable

from photo_orientation.getset import exif_to_degrees, get_orientation


extensions = {".jpg", ".jpeg", ".png", ".tiff"}


def evaluate_file(
    path: Path, display_name: str, check_only: bool, table, mismatch_table
):
    exif_orientation, xmp_orientation = get_orientation(str(path))

    if check_only:
        if exif_orientation is None and xmp_orientation is None:
            print(f"Warning: No orientation found for {display_name}")
        elif exif_orientation is not None and xmp_orientation is not None:
            if exif_orientation != xmp_orientation:
                mismatch_table.row(display_name, exif_orientation, xmp_orientation)
                return True
        return

    degrees = (
        exif_to_degrees.get(exif_orientation) if exif_orientation is not None else None
    )
    table.row(display_name, exif_orientation, xmp_orientation, degrees)
    return False


def process_directory(root: Path, check_only: bool, table, mismatch_table):
    mismatch_count = 0
    for file_path in root.rglob("*"):
        if file_path.suffix.lower() in extensions:
            if evaluate_file(
                file_path,
                str(file_path.relative_to(root)),
                check_only,
                table,
                mismatch_table,
            ):
                mismatch_count += 1
    return mismatch_count


def main():
    parser = argparse.ArgumentParser(
        description="Check EXIF and XMP orientation values for image files."
    )
    parser.add_argument(
        "-c",
        "--check",
        action="store_true",
        help="Enable check mode (default behavior).",
    )
    parser.add_argument("files", nargs="+", help="Files to inspect.")
    args = parser.parse_args()

    # Kept for CLI compatibility with requested flag.
    _ = args.check

    table = None
    mismatch_table = None
    mismatch_count = 0
    if not args.check:
        table = ANSITable("File", "EXIF", "XMP", "Degrees(EXIF)")
    else:
        mismatch_table = ANSITable("File", "EXIF", "XMP")

    for path_str in args.files:
        path = Path(path_str)
        if path.is_file():
            if path.suffix.lower() in extensions:
                if evaluate_file(path, path.name, args.check, table, mismatch_table):
                    mismatch_count += 1
            elif args.check:
                print(f"Skipping non-image file: {path_str}")
            elif table is not None:
                table.row(path_str, "non-image", "-", "-")
        elif path.is_dir():
            mismatch_count += process_directory(path, args.check, table, mismatch_table)
        elif args.check:
            print(f"Skipping missing path: {path_str}")
        elif table is not None:
            table.row(path_str, "missing", "-", "-")

    if not args.check:
        print(table)
    elif mismatch_count > 0:
        print(mismatch_table)


if __name__ == "__main__":
    main()
