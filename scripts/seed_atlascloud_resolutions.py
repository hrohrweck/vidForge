#!/usr/bin/env python3
import os, json, asyncio
from typing import TypedDict
import asyncpg

FAMILY_PATTERNS = [
    ("black-forest-labs/", "ratio", ["1:1", "16:9", "9:16", "4:3", "3:4"]),
    ("google/imagen", "ratio", ["1:1", "16:9", "9:16", "4:3", "3:4"]),
    ("google/nano-banana", "ratio", ["1:1", "16:9", "9:16", "4:3", "3:4"]),
    ("xai/grok-imagine", "ratio", ["1:1", "16:9", "9:16", "4:3", "3:4"]),
    ("qwen/", "pixel_star", ["1536x1536", "2688x1536", "1536x2688", "2048x1536", "1536x2048"]),
    ("alibaba/qwen-image", "pixel_star", ["1536x1536", "2688x1536", "1536x2688", "2048x1536", "1536x2048"]),
    ("atlascloud/qwen-image", "pixel_star", ["1536x1536", "2688x1536", "1536x2688", "2048x1536", "1536x2048"]),
    ("alibaba/wan-", "pixel_star", ["1536x1536", "2688x1536", "1536x2688", "2048x1536", "1536x2048"]),
    ("bytedance/seedream-v4.5", "wh_int", ["1440x1440", "2560x1440", "1440x2560", "2048x1440", "1440x2048"]),
    ("bytedance/seedream-v4", "pixel_star", ["1536x1536", "2688x1536", "1536x2688", "2048x1536", "1536x2048"]),
    ("bytedance/seedream-v5", "pixel_star", ["1536x1536", "2688x1536", "1536x2688", "2048x1536", "1536x2048"]),
    ("openai/gpt-image-1/", "pixel_x", ["1024x1024", "1024x1536", "1536x1024"]),
    ("openai/gpt-image-1.5/", "pixel_x", ["1024x1024", "1024x1536", "1536x1024"]),
    ("openai/gpt-image-1-mini/", "pixel_x", ["1024x1024", "1024x1536", "1536x1024"]),
    ("openai/gpt-image-2/", "pixel_x", ["1536x1536", "2688x1536", "1536x2688", "2048x1536", "1536x2048"]),
    ("z-image/", "wh_int", ["1536x1536", "2688x1536", "1536x2688", "2048x1536", "1536x2048"]),
    ("baidu/", "wh_int", ["1024x1024", "848x1264", "1264x848", "768x1376", "1376x768"]),
]


def get_family_for_model(model_id: str):
    for prefix, family, resolutions in FAMILY_PATTERNS:
        if model_id.startswith(prefix):
            return family, resolutions
    return None


async def main():
    database_url = os.environ.get("DATABASE_URL", "postgresql://vidforge:vidforge@localhost:5432/vidforge")
    parts = database_url.replace("postgresql://", "").split("@")
    user_pass = parts[0]
    host_port_db = parts[1]
    user, password = user_pass.split(":")
    host_port = host_port_db.split("/")[0].split(":")
    host = host_port[0]
    port = int(host_port[1]) if len(host_port) > 1 else 5432
    dbname = host_port_db.split("/")[1]

    conn = await asyncpg.connect(host=host, port=port, user=user, password=password, database=dbname)
    try:
        await conn.fetchval("SELECT 1")
        print(f"Connected to {host}:{port}/{dbname}\n")

        rows = await conn.fetch("""
            SELECT mc.id, mc.model_id, mc.constraints
            FROM model_configs mc
            JOIN providers p ON p.id = mc.provider_id
            WHERE p.provider_type = 'atlascloud' AND mc.modality = 'image'
            ORDER BY mc.model_id
        """)
        print(f"Found {len(rows)} AtlasCloud image model configs.\n")

        if not rows:
            print("No AtlasCloud image models found. Exiting.")
            return

        results = {}
        updates = []

        for row in rows:
            model_id = row["model_id"]
            raw_constraints = row["constraints"]
            if raw_constraints is None:
                current_constraints = {}
            elif isinstance(raw_constraints, str):
                current_constraints = json.loads(raw_constraints)
            else:
                current_constraints = raw_constraints

            match = get_family_for_model(model_id)
            if match is None:
                print(f"  [SKIP] {model_id} - no matching family")
                continue

            family, resolutions = match

            if (current_constraints.get("size_param_family") == family and
                current_constraints.get("resolutions") == resolutions):
                print(f"  [SKIP] {model_id} - already has correct constraints")
                continue

            new_constraints = dict(current_constraints)
            new_constraints["size_param_family"] = family
            new_constraints["resolutions"] = resolutions

            updates.append((str(row["id"]), json.dumps(new_constraints), model_id, family))
            results[family] = results.get(family, 0) + 1

        if updates:
            print(f"Updating {len(updates)} models...")
            update_args = [(uid, constraints) for uid, constraints, _, _ in updates]
            await conn.executemany("""
                UPDATE model_configs SET constraints = $2::jsonb, updated_at = NOW()
                WHERE id = $1::uuid
            """, update_args)

        print("\n" + "=" * 50)
        print("UPDATE SUMMARY")
        print("=" * 50)
        print(f"{'Family':<15} {'Count':>8}")
        print("-" * 25)
        for family, count in sorted(results.items()):
            print(f"{family:<15} {count:>8}")
        print("-" * 25)
        print(f"{'TOTAL':<15} {sum(results.values()):>8}")
        print("=" * 50)

        print("\nVerification:")
        print("-" * 50)
        verify_rows = await conn.fetch("""
            SELECT constraints->>'size_param_family' as family, COUNT(*) as cnt
            FROM model_configs
            WHERE provider_id IN (SELECT id FROM providers WHERE provider_type='atlascloud')
              AND modality='image'
              AND constraints->>'size_param_family' IS NOT NULL
            GROUP BY family ORDER BY family
        """)
        for row in verify_rows:
            print(f"  {row['family']:<15} {row['cnt']:>5}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())