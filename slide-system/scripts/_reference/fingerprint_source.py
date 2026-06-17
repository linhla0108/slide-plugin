#!/usr/bin/env python3
"""Create deterministic source and region fingerprints for extraction."""

from __future__ import annotations

import argparse
import json

from _common import (
    average_image_hash,
    normalized_bounds,
    now_iso,
    sha256_file,
    sha256_text,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--slide", required=True)
    parser.add_argument("--region", required=True, help="JSON object with x/y/width/height/unit")
    parser.add_argument("--object-id", action="append", default=[])
    parser.add_argument("--semantic-signature", default="")
    parser.add_argument("--region-image")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    region = normalized_bounds(json.loads(args.region))
    source_hash = sha256_file(args.source)
    identity = {
        "source_sha256": source_hash,
        "slide_or_page": str(args.slide),
        "region": region,
        "object_ids": sorted(args.object_id),
    }
    result = {
        "generated_at": now_iso(),
        **identity,
        "region_identity_sha256": sha256_text(json.dumps(identity, sort_keys=True)),
        "semantic_signature_sha256": sha256_text(args.semantic_signature.strip().lower()),
        "perceptual_hash": average_image_hash(args.region_image) if args.region_image else None,
    }
    write_json(args.output, result)
    print(result["region_identity_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

