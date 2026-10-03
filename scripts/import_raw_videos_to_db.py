from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
RAW_VIDEO_DIR = PROJECT_DIR / "data" / "raw_videos"

if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "把 data/raw_videos 中的视频路径关联到 MySQL dances 表。"
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际写入数据库；不加此参数时只预览。",
    )
    parser.add_argument(
        "--create-missing",
        action="store_true",
        help="为数据库中不存在的 MD-xxx 编号创建占位记录。",
    )
    return parser.parse_args()


def dance_id_for(video_path: Path) -> str:
    suffix = video_path.stem.removeprefix("video_")
    if not suffix.isdigit():
        raise ValueError(f"无法从文件名生成舞蹈编号：{video_path.name}")
    return f"MD-{int(suffix):03d}"


def ensure_password() -> None:
    if os.getenv("MYSQL_PASSWORD") is None:
        mysql_user = os.getenv("MYSQL_USER", "dance_user")
        os.environ["MYSQL_PASSWORD"] = getpass.getpass(
            f"请输入 MySQL 用户 {mysql_user} 的密码："
        )


def main() -> int:
    args = parse_args()
    videos = sorted(RAW_VIDEO_DIR.glob("video_*.*"))
    videos = [
        path
        for path in videos
        if path.suffix.lower() in {".mp4", ".mov", ".webm", ".avi", ".mkv"}
    ]

    if not videos:
        print(f"没有找到视频：{RAW_VIDEO_DIR}")
        return 1

    ensure_password()
    from server.database import get_connection

    connection = get_connection()
    updated = 0
    created = 0
    skipped = 0

    try:
        with connection.cursor() as cursor:
            for video_path in videos:
                dance_id = dance_id_for(video_path)
                relative_path = video_path.relative_to(PROJECT_DIR).as_posix()

                cursor.execute(
                    "SELECT dance_id FROM dances WHERE dance_id = %s LIMIT 1",
                    (dance_id,),
                )
                exists = cursor.fetchone() is not None

                if exists:
                    action = "更新"
                    if args.apply:
                        cursor.execute(
                            """
                            UPDATE dances
                            SET video_path = %s, video_url = NULL
                            WHERE dance_id = %s
                            """,
                            (relative_path, dance_id),
                        )
                        updated += 1
                elif args.create_missing:
                    action = "新建"
                    if args.apply:
                        cursor.execute(
                            """
                            INSERT INTO dances (
                                dance_id,
                                name,
                                video_path,
                                video_url,
                                review_status
                            ) VALUES (%s, %s, %s, NULL, 'pending')
                            """,
                            (
                                dance_id,
                                f"舞蹈样本 {dance_id.removeprefix('MD-')}",
                                relative_path,
                            ),
                        )
                        created += 1
                else:
                    action = "跳过（记录不存在）"
                    skipped += 1

                print(f"{action:12} {dance_id} <- {relative_path}")

        if args.apply:
            connection.commit()
            print(
                f"\n导入完成：更新 {updated} 条，新建 {created} 条，"
                f"跳过 {skipped} 条。"
            )
        else:
            connection.rollback()
            print("\n当前是预览模式，数据库没有发生变化。")
            print("确认映射正确后，加 --apply 再运行一次。")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
