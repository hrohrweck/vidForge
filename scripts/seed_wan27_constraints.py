#!/usr/bin/env python3
import os
import json
import asyncio
import asyncpg

WAN27_MODELS = [
    "alibaba/wan-2.7/text-to-video",
    "alibaba/wan-2.7/image-to-video",
    "alibaba/wan-2.7/reference-to-video",
    "alibaba/wan-2.7/video-edit",
]

IMAGE_INPUT_MODELS = {
    "alibaba/wan-2.7/image-to-video",
    "alibaba/wan-2.7/reference-to-video",
}


NEW_CONSTRAINTS = {
    "supported_aspect_ratios": ["16:9"],
    "requires_aspect_ratio": False,
}

NEW_PARAMETER_MAP = {"image_url": "image"}


def parse_database_url(database_url: str):
    stripped = database_url.replace("postgresql://", "")
    user_pass, host_port_db = stripped.split("@", 1)
    user, password = user_pass.split(":", 1)
    host_port = host_port_db.split("/", 1)[0]
    host_parts = host_port.split(":")
    host = host_parts[0]
    port = int(host_parts[1]) if len(host_parts) > 1 else 5432
    dbname = host_port_db.split("/", 1)[1]
    return host, port, user, password, dbname


async def main():
    database_url = os.environ.get(
        "DATABASE_URL", "postgresql://vidforge:vidforge@localhost:5432/vidforge"
    )
    host, port, user, password, dbname = parse_database_url(database_url)

    conn = await asyncpg.connect(
        host=host, port=port, user=user, password=password, database=dbname
    )
    try:
        await conn.fetchval("SELECT 1")
        print(f"Connected to {host}:{port}/{dbname}\n")

        updated = 0
        skipped = 0

        for model_id in WAN27_MODELS:
            row = await conn.fetchrow(
                """
                SELECT id, model_id, parameter_map, constraints
                FROM model_configs
                WHERE model_id = $1
                """,
                model_id,
            )

            if row is None:
                print(f"  [skip] {model_id} - model not found in model_configs")
                skipped += 1
                continue

            target_param_map = (
                NEW_PARAMETER_MAP if model_id in IMAGE_INPUT_MODELS else None
            )

            raw_constraints = row["constraints"]
            if raw_constraints is None:
                current_constraints = {}
            elif isinstance(raw_constraints, str):
                current_constraints = json.loads(raw_constraints)
            else:
                current_constraints = dict(raw_constraints)

            new_constraints = dict(current_constraints)
            new_constraints["supported_aspect_ratios"] = NEW_CONSTRAINTS[
                "supported_aspect_ratios"
            ]
            new_constraints["requires_aspect_ratio"] = NEW_CONSTRAINTS[
                "requires_aspect_ratio"
            ]

            if target_param_map is not None:
                raw_param_map = row["parameter_map"]
                if raw_param_map is None:
                    current_param_map = {}
                elif isinstance(raw_param_map, str):
                    current_param_map = json.loads(raw_param_map)
                else:
                    current_param_map = dict(raw_param_map)

                new_param_map = dict(current_param_map)
                new_param_map["image_url"] = target_param_map["image_url"]
                param_map_json = json.dumps(new_param_map)
            else:
                param_map_json = None

            await conn.execute(
                """
                UPDATE model_configs
                SET constraints = $2::jsonb,
                    parameter_map = COALESCE($3::jsonb, parameter_map),
                    updated_at = NOW()
                WHERE id = $1::uuid
                """,
                row["id"],
                json.dumps(new_constraints),
                param_map_json,
            )

            actions = ["constraints"]
            if target_param_map is not None:
                actions.append("parameter_map")
            print(f"  [ok] {model_id} - updated {', '.join(actions)}")
            updated += 1

        print()
        print("=" * 50)
        print("WAN 2.7 UPDATE SUMMARY")
        print("=" * 50)
        print(f"  Updated: {updated}")
        print(f"  Skipped: {skipped}")
        print(f"  Total:   {len(WAN27_MODELS)}")
        print("=" * 50)

        print("\nVerification:")
        print("-" * 50)
        verify_rows = await conn.fetch(
            """
            SELECT model_id,
                   parameter_map,
                   constraints
            FROM model_configs
            WHERE model_id = ANY($1::text[])
            ORDER BY model_id
            """,
            WAN27_MODELS,
        )
        for vrow in verify_rows:
            param_map = vrow["parameter_map"]
            constraints = vrow["constraints"]
            param_str = (
                json.dumps(param_map) if param_map is not None else "null"
            )
            constraints_str = (
                json.dumps(constraints, sort_keys=True)
                if constraints is not None
                else "null"
            )
            print(f"  {vrow['model_id']}")
            print(f"    parameter_map: {param_str}")
            print(f"    constraints:   {constraints_str}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
