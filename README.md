# photo-orientation

Tools to inspect and update image orientation metadata (EXIF and XMP).

## Features

- Read EXIF and XMP orientation values.
- Check for EXIF/XMP mismatches across files or nested folders.
- Set a fixed orientation value directly.
- Optional [ML-based auto-orientation mode](https://huggingface.co/DuarteBarbosa/deep-image-orientation-detection) with lazy imports.

## Project Layout

```text
photo-orientation/
  src/photo_orientation/
    __init__.py
    getset.py
    getorientation.py
    setorientation.py
  pyproject.toml
  Makefile
  README.md
```

## Installation

Base install (metadata tools):

```bash
pip install -e .
```

Install with optional auto-orientation dependencies:

```bash
pip install -e .[auto]
```

The `auto` extra includes: `Pillow`, `torch`, `torchvision`, `huggingface_hub`.

## CLI Commands

After install, these console scripts are available.

### Check Orientation

```bash
getorientation --check path/to/file.jpg path/to/folder
```

- Accepts files and folders.
- Recurses folders with `rglob`.
- In `--check` mode, prints an EXIF/XMP mismatch table.

### Set Orientation

```bash
setorientation --set 1 path/to/file.jpg path/to/other.jpg
```

- `--set` mode does not require the optional `auto` dependencies.
- Without `--set`, the tool uses the [ML model](https://huggingface.co/DuarteBarbosa/deep-image-orientation-detection) to predict and set orientation.

## Development

The `Makefile` includes common tasks:

```bash
make help
make install
make install-auto
make run-check ARGS="--check photos/"
make run-set ARGS="--set 1 a.jpg b.jpg"
make dist
make upload
```

## Notes

- The metadata functions support both XMP formats:
  - `tiff:Orientation="6"`
  - `<tiff:Orientation>6</tiff:Orientation>`
- `map=4096` is the default mmap window for orientation reads/writes.
- Set `map=0` to map the full file.  

## Tutorial: Orientation Modes

This project works with EXIF orientation values. The orientation field in the image metadata 
describes a transform *from* the image array stored in the
file as rows and columns (it could be landscape or portrait mode) *to* how it is displayed correctly on the screen.

### Common non-mirrored modes

These are the values most cameras and scanners use for plain rotation:

| EXIF/XMP Value | Meaning | Rotation to display upright |
|---|---|---|
| 1 | Normal | 0 degrees |
| 3 | Rotated 180 | 180 degrees clockwise |
| 6 | Rotated 90 CW | 90 degrees clockwise |
| 8 | Rotated 270 CW | 270 degrees clockwise (or 90 CCW) |

Performing arithmetic on these orientation values is rather crazy, the package include a helper function

```
def rotate_exif(current_exif: int, degrees_cw: int) -> int:
```

which returns an orientation value by the specified rotation in degrees, ie. `rotate_exif(1, 90) -> 6`.

### Full EXIF orientation table

The standard supports additional mirrored transforms but these are uncommon. It can be useful to
consider how the top-left of the image, as stored, is transformed in the displayed image.

| Value | Meaning | Top-left (0,0) maps to |
| :--- | :--- | :--- |
| 1 | Horizontal (normal) | Top left |
| 2 | Mirrored about vertical axis | Top right |
| 3 | Rotated 180 | Bottom right |
| 4 | Mirrored about horizontal axis | Bottom left |
| 5 | Mirrored about vertical axis and rotated 270 CW (transpose) | Top left |
| 6 | Rotated 90 CW | Top right |
| 7 | Mirrored about vertical axis and rotated 90 CW | Bottom right |
| 8 | Rotated 270 CW | Bottom left |

### Where this info lives

- EXIF block:
  - Usually in JPEG APP1 metadata with the `Exif\0\0` header.
  - The orientation value is tag `0x0112` in the TIFF IFD entries.
  - This code handles the case of the tag being SHORT (type 3) or LONG (type 4)
  - In this project, EXIF is read/written from that orientation tag.

- XMP block:
  - Stored as XML metadata, often also in APP1 (or equivalent container metadata).
  - Common forms are:
    - `tiff:Orientation="6"`
    - `<tiff:Orientation>6</tiff:Orientation>`
  - This project reads and can update both forms.

### Practical guidance

- Use `getorientation --check ...` to detect EXIF/XMP mismatch.
- Use `setorientation --set <value> ...` to apply a fixed orientation value.
- If EXIF and XMP differ, normalize them to the same value to avoid viewer-specific behavior.
