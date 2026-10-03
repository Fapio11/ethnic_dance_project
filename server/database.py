from __future__ import annotations

import os

import pymysql
from pymysql.cursors import DictCursor


VALID_REVIEW_STATUSES = {
    "pending",
    "verified",
    "rejected",
}


def get_connection():
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "dance_user"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv(
            "MYSQL_DATABASE",
            "ethnic_dance",
        ),
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
        connect_timeout=5,
        read_timeout=30,
        write_timeout=30,
    )


def get_all_dances() -> list[dict]:
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
    dance_id,
    name,
    ethnic_group,
    region,
    description,
    video_url,
    video_path,
    pose_data_url,
    pose_2d_path,
    pose_3d_path,
    analysis_path,
    review_status,
    narration
FROM dances
ORDER BY dance_id
                """
            )

            return list(cursor.fetchall())
    finally:
        connection.close()


def get_dance(
    dance_id: str,
) -> dict | None:
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM dances
                WHERE dance_id = %s
                LIMIT 1
                """,
                (dance_id,),
            )

            return cursor.fetchone()
    finally:
        connection.close()


def update_pose_results(
    dance_id: str,
    video_url: str | None,
    pose_data_url: str | None,
    pose_2d_path: str | None,
    pose_3d_path: str | None,
    analysis_path: str | None,
) -> None:
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE dances
                SET
                    video_url = %s,
                    pose_data_url = %s,
                    pose_2d_path = %s,
                    pose_3d_path = %s,
                    analysis_path = %s
                WHERE dance_id = %s
                """,
                (
                    video_url,
                    pose_data_url,
                    pose_2d_path,
                    pose_3d_path,
                    analysis_path,
                    dance_id,
                ),
            )

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def update_review_status(
    dance_id: str,
    review_status: str,
) -> None:
    if review_status not in VALID_REVIEW_STATUSES:
        raise ValueError(
            f"不支持的核验状态：{review_status}"
        )

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE dances
                SET review_status = %s
                WHERE dance_id = %s
                """,
                (
                    review_status,
                    dance_id,
                ),
            )

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def save_narration(
    dance_id: str,
    narration: str,
) -> None:
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE dances
                SET narration = %s
                WHERE dance_id = %s
                """,
                (
                    narration,
                    dance_id,
                ),
            )

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
