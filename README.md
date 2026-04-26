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

# API

To access the API first import the package

```
import photo_orientation as po
```


```
def get_orientation(filepath: str, map: int = 4096) -> tuple[int | None, int | None]:
```
returns a 2-tuple containing the orientation value from the EXIF and XMP blocks respectively.  If
either is missing the corresponding value is `None`. If the values are not `None` but different,
the metadata is inconsistent and some tools like Apple Photos may deem the image to be corrupt.

The function uses [`mmap`](9https://docs.python.org/3/library/mmap.html) to process the file, and by default maps only the first 4k which is where metadata blocks *typically* live.  
If the metadata is not found within the mapped region of the file the function will return `(None, None)` -- that doesn't
mean the metadata is not somewhere else in the file!
Setting `map=0` would map the whole file.  The length needs to be a multiple of the page size.


```
def set_orientation(filepath: str, new_orientation: int, XMP: bool = True, map: int = 4096) -> bool:
```
sets the orientation value in the metadata to `new_orientation`. The value will be set in the EXIF, and
if `XMP=True` and an XMP block exists, that value will be updated as well. If the metadata are not preexisting,
the tool will not create them, for that you
need to use a tool like [`exiftool`](https://exiftool.org).

`set_orientation` is precise and surgical, and changes at most 2 bytes in the metadata blocks.

```
exif_to_degrees: dict[int, int]
```
is a dict that maps an orientation value [1..8] into a rotation in degrees.


```
def rotate_exif(current_exif: int, degrees_cw: int) -> int:
```
The values used to represent orientation are non-sequential, see next section.  This function
returns an orientation value for the orientation `current_exif` rotated by
a CW rotation of `degrees_cw` in degrees. For example `rotate_exif(1, 90) -> 6`.



# Notes

## Image metadata

Image metadata is a complex nightmare, layer upon layer of "standards".  Images can have:

- binary coded [EXIF](https://en.wikipedia.org/wiki/Exif) blocks with tagged values (the basis of the [TIFF](https://en.wikipedia.org/wiki/TIFF) file format). Image orientation is tag 0x112.
- XML encoded metadata following the [XMP](https://en.wikipedia.org/wiki/Extensible_Metadata_Platform) data model, where
orientation can be expressed as either:
  - `tiff:Orientation="6"`
  - `<tiff:Orientation>6</tiff:Orientation>`

### Image Orientation Modes

This project works with EXIF orientation values. The orientation field in the image metadata 
describes a transform *from* the image array stored in the
file as rows and columns (it could be landscape or portrait mode) *to* how it is displayed correctly on the screen.

These are the values most cameras and scanners use for plain rotation:

| EXIF/XMP Value | Meaning | Rotation to display upright |
|---|---|---|
| 1 | Normal | 0 degrees |
| 3 | Rotated 180 | 180 degrees clockwise |
| 6 | Rotated 90 CW | 90 degrees clockwise |
| 8 | Rotated 270 CW | 270 degrees clockwise (or 90 CCW) |


### Full EXIF orientation table

The standard supports additional mirrored transforms but these are uncommon. It can be useful to
consider how the top-left corner of the image, as stored, is transformed in the displayed image.

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

## ML model for automatic orientation estimation

The tool uses the [deep-image-orientation-detection](https://huggingface.co/DuarteBarbosa/deep-image-orientation-detection)
model from Hugging Face.  The model was trained on a huge dataset of 189,018 unique images curated from a number
of publicly available datasets. Each image is augmented by being rotated in four ways (0°, 90°, 180°, 270°), creating a total of 756,072 samples. This augmented dataset was then split into 604,857 samples for training and 151,215 samples for validation.
The model achieves 98.82% accuracy on the validation set.

Full details can be found on the [GitHub repo](https://github.com/duartebarbosadev/deep-image-orientation-detection).

Inference is performed using PyTorch with automatic computational fallbacks: CUDA, MPS (Apple Silicon), CPU.

# Practical guidance

- Use `getorientation --check ...` to detect EXIF/XMP mismatch.
- Use `setorientation --set <value> ...` to apply a fixed orientation value.
- If EXIF and XMP differ, normalize them to the same value to avoid viewer-specific behavior.
