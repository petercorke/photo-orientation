import argparse
from typing import Any

from pathlib import Path

from photo_orientation.getset import set_orientation


torch: Any | None = None
Image: Any | None = None
device: Any | None = None
model: Any | None = None
preprocess: Any | None = None


def initialize_predictor():
    """Lazily import and initialize model dependencies for prediction mode."""
    global torch, Image, device, model, preprocess

    if model is not None:
        return

    try:
        from PIL import Image as PILImage
        import torch as torch_module
        from torchvision import models, transforms
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise RuntimeError(
            "Prediction mode requires optional dependencies: Pillow, torch, torchvision, and huggingface_hub. "
            "Install them with 'pip install .[auto]' or use -s/--set mode."
        ) from exc

    torch = torch_module
    Image = PILImage

    if torch.cuda.is_available():
        device = torch.device("cuda")
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")
    model = models.efficientnet_v2_s()
    classifier_layer = model.classifier[1]
    in_features = getattr(classifier_layer, "in_features", None)
    if not isinstance(in_features, int):
        raise RuntimeError("Unexpected model classifier shape")
    model.classifier[1] = torch.nn.Linear(in_features, 4)

    weights_path = hf_hub_download(
        repo_id="DuarteBarbosa/deep-image-orientation-detection",
        filename="orientation_model_v2_0.9882.pth",
    )
    model.load_state_dict(torch.load(weights_path, map_location=device))
    model.to(device).eval()

    preprocess = transforms.Compose(
        [
            transforms.Resize(224),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ]
    )


# Define standard image extensions for scans
extensions = {".jpg", ".jpeg", ".png", ".tiff"}

# Mapping model classes to EXIF orientation values
# 0: 1 (Normal), 1: 6 (90 CW), 2: 3 (180), 3: 8 (270 CW)
exif_map = {0: 1, 1: 6, 2: 3, 3: 8}


def process_image(file_path, stats, display_name=None, quiet=False):
    initialize_predictor()

    assert torch is not None
    assert Image is not None
    assert device is not None
    assert model is not None
    assert preprocess is not None

    local_torch = torch
    local_image = Image
    local_device = device
    local_model = model
    local_preprocess = preprocess

    file_path = Path(file_path)
    display = display_name if display_name is not None else file_path
    stats["processed"] += 1

    try:
        if not quiet:
            print(f"  Processing: {display}")
        # Load and predict
        with local_image.open(file_path) as img:
            input_tensor = (
                local_preprocess(img.convert("RGB")).unsqueeze(0).to(local_device)
            )

        with local_torch.no_grad():
            output = local_model(input_tensor)
            pred_class = int(local_torch.argmax(output, dim=1).item())

        # Only update if the model thinks it's not already upright (Class 0)
        if pred_class != 0:
            exif_val = exif_map[pred_class]
            if not quiet:
                print(f"    Correcting: {display} -> Orientation {exif_val}")

            success = set_orientation(str(file_path), exif_val)
            if success:
                stats["changed"] += 1
            elif not quiet:
                print(f"    Failed to update EXIF for {display}")

    except Exception as e:
        print(f"Error processing {file_path}: {e}")


def process_directory(root_path, stats, quiet=False):
    root = Path(root_path)

    if not quiet:
        print(f"Starting program in: {root}")

    for file_path in root.rglob("*"):
        if file_path.suffix.lower() in extensions:
            process_image(file_path, stats, file_path.relative_to(root), quiet)


def set_orientation_for_files(files, exif_value, stats, quiet=False):
    for file_name in files:
        path = Path(file_name)
        if not path.is_file():
            if not quiet:
                print(f"Skipping non-file path: {path}")
            continue

        stats["processed"] += 1
        success = set_orientation(str(path), exif_value)
        if success:
            stats["changed"] += 1
            if not quiet:
                print(f"Updated {path} -> Orientation {exif_value}")
        elif not quiet:
            print(f"Failed to update EXIF for {path}")


def main():
    parser = argparse.ArgumentParser(
        description="Auto-detect image orientation or set a fixed EXIF orientation."
    )
    parser.add_argument(
        "-s",
        "--set",
        dest="set_value",
        type=int,
        help="Set EXIF orientation to this value for the given files.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress per-file output and print a summary at the end.",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Files or directories to process. If omitted, the default directory is used.",
    )
    args = parser.parse_args()
    stats = {"processed": 0, "changed": 0}

    if args.set_value is not None:
        if not args.files:
            parser.error("-s/--set requires at least one file")
        set_orientation_for_files(args.files, args.set_value, stats, args.quiet)
        if args.quiet:
            print(
                f"Summary: processed={stats['processed']}, orientation_changes={stats['changed']}"
            )
        return

    try:
        initialize_predictor()
    except RuntimeError as exc:
        parser.error(str(exc))

    if args.files:
        for path in args.files:
            p = Path(path)
            if p.is_file():
                if p.suffix.lower() in extensions:
                    process_image(p, stats, p.name, args.quiet)
                elif not args.quiet:
                    print(f"Skipping non-image file: {p}")
            elif p.is_dir():
                process_directory(p, stats, args.quiet)
            elif not args.quiet:
                print(f"Skipping missing path: {p}")
        if args.quiet:
            print(
                f"Summary: processed={stats['processed']}, orientation_changes={stats['changed']}"
            )
        return

    # Default: process the configured top-level folder.
    target_dir = "/Volumes/Data/Family scanned photos"
    process_directory(target_dir, stats, args.quiet)
    if args.quiet:
        print(
            f"Summary: processed={stats['processed']}, orientation_changes={stats['changed']}"
        )


if __name__ == "__main__":
    main()
