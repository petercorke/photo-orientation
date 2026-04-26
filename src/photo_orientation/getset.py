import mmap
import struct
from ansitable import ANSITable


def get_orientation(filepath: str, map: int = 4096) -> tuple[int | None, int | None]:
    """Return EXIF and XMP orientation values from one file read.

    The XMP parser supports both common forms:
    - ``tiff:Orientation="6"``
    - ``<tiff:Orientation>6</tiff:Orientation>``

    Args:
        filepath: Path to image file.
        map: Number of bytes to map in memory. Use ``0`` to map the whole file.

    Returns:
        A tuple ``(exif_orientation, xmp_orientation)`` where either value can be
        ``None`` when not found.
    """
    if map < 0:
        raise ValueError("map must be >= 0")

    with open(filepath, "rb") as f:
        # Memory-map a prefix or the whole file (length=0 maps whole file).
        mm = mmap.mmap(f.fileno(), map, access=mmap.ACCESS_READ)

        try:
            exif_orientation = None
            xmp_orientation = None

            # 1. Locate the Exif header (skip JPEG SOI)
            # Typically 0xFF 0xE1 (APP1), then 2-byte length, then 'Exif\0\0'
            exif_idx = mm.find(b"Exif\0\0")
            if exif_idx != -1:
                try:
                    # 2. Identify Endianness (TIFF Header starts 6 bytes after 'Exif\0\0')
                    tiff_start = exif_idx + 6
                    endian_mark = mm[tiff_start : tiff_start + 2]

                    is_le = endian_mark == b"II"
                    fmt_short = "<H" if is_le else ">H"
                    fmt_long = "<L" if is_le else ">L"

                    # 3. Get offset to 0th IFD (4 bytes at tiff_start + 4)
                    ifd_offset = struct.unpack(
                        fmt_long, mm[tiff_start + 4 : tiff_start + 8]
                    )[0]
                    curr_pos = tiff_start + ifd_offset

                    # 4. Number of directory entries (2 bytes)
                    num_entries = struct.unpack(fmt_short, mm[curr_pos : curr_pos + 2])[
                        0
                    ]
                    curr_pos += 2

                    # 5. Iterate through 12-byte entries
                    for _ in range(num_entries):
                        tag_id = struct.unpack(fmt_short, mm[curr_pos : curr_pos + 2])[
                            0
                        ]

                        if tag_id == 0x0112:  # Orientation Tag
                            # The value is in the last 4 bytes of the 12-byte entry.
                            type_offset = curr_pos + 2
                            type_id = struct.unpack(
                                fmt_short, mm[type_offset : type_offset + 2]
                            )[0]

                            value_offset = curr_pos + 8
                            if type_id == 3:  # SHORT
                                exif_orientation = struct.unpack(
                                    fmt_short, mm[value_offset : value_offset + 2]
                                )[0]
                            elif type_id == 4:  # LONG
                                exif_orientation = struct.unpack(
                                    fmt_long, mm[value_offset : value_offset + 4]
                                )[0]
                            break

                        curr_pos += 12
                except (IndexError, struct.error):
                    exif_orientation = None

            # Parse XMP orientation as attribute: tiff:Orientation="6"
            attr_key = b'tiff:Orientation="'
            attr_idx = mm.find(attr_key)
            if attr_idx != -1:
                val_start = attr_idx + len(attr_key)
                val_end = mm.find(b'"', val_start)
                if val_end != -1:
                    raw_val = mm[val_start:val_end].strip()
                    if raw_val.isdigit():
                        xmp_orientation = int(raw_val)

            # Parse XMP orientation as element if attribute form is absent.
            if xmp_orientation is None:
                element_open = b"<tiff:Orientation>"
                element_close = b"</tiff:Orientation>"
                element_idx = mm.find(element_open)
                if element_idx != -1:
                    val_start = element_idx + len(element_open)
                    val_end = mm.find(element_close, val_start)
                    if val_end != -1:
                        raw_val = mm[val_start:val_end].strip()
                        if raw_val.isdigit():
                            xmp_orientation = int(raw_val)

            return exif_orientation, xmp_orientation

        finally:
            mm.close()
    return None, None


def sync_xmp_orientation(mm, new_value: int) -> bool:
    """Update XMP orientation in-place for attribute and element forms.

    This function replaces a single value byte in the first match of each form:
    - ``tiff:Orientation="N"`` (or unquoted ``tiff:Orientation=N``)
    - ``<tiff:Orientation>N</tiff:Orientation>``

    Returns:
        ``True`` if at least one XMP value was updated.
    """
    if new_value < 0 or new_value > 9:
        return False

    replacement = str(new_value).encode("ascii")
    updated = False

    # Attribute form: tiff:Orientation="N" (or tiff:Orientation=N)
    attr_key = b"tiff:Orientation="
    attr_idx = mm.find(attr_key)
    if attr_idx != -1:
        val_idx = attr_idx + len(attr_key)
        if val_idx < len(mm):
            if mm[val_idx : val_idx + 1] == b'"':
                val_idx += 1
            if val_idx < len(mm):
                mm[val_idx : val_idx + 1] = replacement
                updated = True

    # Element form: <tiff:Orientation>N</tiff:Orientation>
    element_open = b"<tiff:Orientation>"
    element_idx = mm.find(element_open)
    if element_idx != -1:
        val_idx = element_idx + len(element_open)
        if val_idx < len(mm):
            mm[val_idx : val_idx + 1] = replacement
            updated = True

    return updated


def set_orientation(
    filepath: str, new_orientation: int, XMP: bool = True, map: int = 4096
) -> bool:
    """Set EXIF orientation and optionally sync XMP orientation.

    :param filepath: Path to image file.
    :type filepath: str
    :param new_orientation: EXIF orientation value (typically 1, 3, 6, 8).
    :type new_orientation: int
    :param XMP: When ``True``, also patch XMP orientation value(s).
    :type XMP: bool
    :param map: Number of bytes to map in memory. Use ``0`` to map the whole file.
    :type map: int
    :return: ``True`` if EXIF or XMP was updated.
    :rtype: bool
    :raises ValueError: If ``map`` is negative.
    """
    if map < 0:
        raise ValueError("map must be >= 0")

    with open(filepath, "r+b") as f:
        # Memory-map a prefix or the whole file (length=0 maps whole file).
        mm = mmap.mmap(f.fileno(), map, access=mmap.ACCESS_WRITE)

        try:
            updated_exif = False
            # 1. Locate the Exif header (skip JPEG SOI)
            # Typically 0xFF 0xE1 (APP1), then 2-byte length, then 'Exif\0\0'
            exif_idx = mm.find(b"Exif\0\0")

            if exif_idx != -1:
                # 2. Identify Endianness (TIFF Header starts 6 bytes after 'Exif\0\0')
                tiff_start = exif_idx + 6
                endian_mark = mm[tiff_start : tiff_start + 2]

                is_le = endian_mark == b"II"
                fmt_short = "<H" if is_le else ">H"
                fmt_long = "<L" if is_le else ">L"

                # 3. Get offset to 0th IFD (4 bytes at tiff_start + 4)
                ifd_offset = struct.unpack(
                    fmt_long, mm[tiff_start + 4 : tiff_start + 8]
                )[0]
                curr_pos = tiff_start + ifd_offset

                # 4. Number of directory entries (2 bytes)
                num_entries = struct.unpack(fmt_short, mm[curr_pos : curr_pos + 2])[0]
                curr_pos += 2

                # 5. Iterate through 12-byte entries
                for _ in range(num_entries):
                    tag_id = struct.unpack(fmt_short, mm[curr_pos : curr_pos + 2])[0]

                    if tag_id == 0x0112:  # Orientation Tag
                        # The value is in the last 4 bytes of the 12-byte entry.
                        # Check the type to determine write size (SHORT or LONG)
                        type_offset = curr_pos + 2
                        type_id = struct.unpack(
                            fmt_short, mm[type_offset : type_offset + 2]
                        )[0]

                        value_offset = curr_pos + 8

                        # Surgical Write: handle both SHORT (type 3) and LONG (type 4)
                        if type_id == 3:  # SHORT
                            new_val_bytes = struct.pack(fmt_short, new_orientation)
                            mm[value_offset : value_offset + 2] = new_val_bytes
                        elif type_id == 4:  # LONG
                            new_val_bytes = struct.pack(fmt_long, new_orientation)
                            mm[value_offset : value_offset + 4] = new_val_bytes

                        updated_exif = True
                        break

                    curr_pos += 12

            updated_xmp = False
            if XMP:
                updated_xmp = sync_xmp_orientation(mm, new_orientation)

            if updated_exif or updated_xmp:
                mm.flush()  # Ensure change is written to disk
                return True

        finally:
            mm.close()
    return False


def rotate_exif(current_exif: int, degrees_cw: int) -> int:
    """Rotate a non-mirrored EXIF orientation by clockwise degrees.

    Unsupported or mirrored source values are treated as normal orientation ``1``.

    :param current_exif: Current EXIF orientation value.
    :type current_exif: int
    :param degrees_cw: Clockwise rotation in degrees, expected in 90-degree steps.
    :type degrees_cw: int
    :return: Rotated EXIF orientation in the non-mirrored cycle ``[1, 6, 3, 8]``.
    :rtype: int
    """
    # Standard non-mirrored EXIF cycle.
    sequence = [1, 6, 3, 8]

    degrees_cw = degrees_cw % 360  # Ensure rotation in range [0, 360)

    if current_exif not in sequence:
        # Default to Normal if the current tag is undefined or mirrored
        current_exif = 1

    current_idx = sequence.index(current_exif)
    steps = degrees_cw // 90

    new_idx = (current_idx + steps) % 4
    return sequence[new_idx]


exif_to_degrees = {
    1: 0,  # Horizontal (Normal)
    2: 0,  # Mirrored horizontal (0° rotation)
    3: 180,  # Rotated 180°
    4: 180,  # Mirrored vertical (180° rotation)
    5: 90,  # Mirrored horizontal & rotated 270° CW
    6: 90,  # Rotated 90° CW
    7: 270,  # Mirrored horizontal & rotated 90° CW
    8: 270,  # Rotated 270° CW (or 90° CCW)
}
