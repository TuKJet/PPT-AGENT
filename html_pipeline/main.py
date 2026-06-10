import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from filename_utils import safe_filename_part
from html_pipeline.pipeline import export_from_existing_html, run_pipeline


def main():
    parser = argparse.ArgumentParser(
        description="PPT Agent (HTML mode) - generate HTML-first decks and export PPTX artifacts"
    )
    parser.add_argument("--topic", "-t", default=None, help="PPT 主题")
    parser.add_argument("--audience", "-a", default=None, help="目标受众")
    parser.add_argument("--pages", "-p", default=None, help="页数要求")
    parser.add_argument(
        "--provider", "-m",
        choices=["openai", "claude", "domestic"],
        default=None,
        help="AI 接口",
    )
    parser.add_argument("--research", "-r", default="", help="补充调研信息")
    parser.add_argument(
        "--polish",
        action="store_true",
        help="启用逐页精修模式，仅对有问题页面做额外修复",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="短链路验证时仅生成前 N 页",
    )
    parser.add_argument(
        "--from-html-dir",
        default=None,
        help="基于已有 html/ 目录重导出 PPT，不重新调用 AI",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="配合 --from-html-dir 使用，指定重导出产物目录",
    )
    parser.add_argument(
        "--editable-only",
        action="store_true",
        help="配合 --from-html-dir 使用，仅导出可编辑版 PPT",
    )
    parser.add_argument(
        "--image-only",
        action="store_true",
        help="配合 --from-html-dir 使用，仅导出图片版 PPT",
    )
    parser.add_argument(
        "--editable-engine",
        default=None,
        help="指定可编辑导出引擎；当前支持 `dom_export` / `legacy`，历史 `pdf_export` 会自动回退到 `dom_export`",
    )
    args = parser.parse_args()

    if args.editable_only and args.image_only:
        print("[错误] --editable-only 与 --image-only 不能同时使用", file=sys.stderr)
        sys.exit(1)

    polish = args.polish or os.getenv("HTML_POLISH_MODE", "false").lower() in {"1", "true", "yes", "on"}

    try:
        if args.from_html_dir:
            export_result = export_from_existing_html(
                html_dir=Path(args.from_html_dir),
                topic=args.topic,
                output_dir=Path(args.output_dir) if args.output_dir else None,
                export_image_ppt=not args.editable_only,
                export_editable_ppt=not args.image_only,
                editable_engine=args.editable_engine,
            )
            print(f"\nHTML 源目录：{Path(args.from_html_dir)}")
            print(f"主题：{export_result['topic']}")
            print(f"页数：{export_result['slide_count']}")
            if export_result["image_pptx_path"]:
                print(f"图片版 PPT：{export_result['image_pptx_path']}")
            if export_result["editable_pptx_path"]:
                print(f"可编辑版 PPT：{export_result['editable_pptx_path']}")
            print(f"链路清单：{export_result['manifest_path']}")
            return

        topic = args.topic or os.getenv("DEFAULT_TOPIC")
        audience = args.audience or os.getenv("DEFAULT_AUDIENCE", "通用受众")
        pages = args.pages or os.getenv("DEFAULT_PAGES", "12-15页")

        if not topic:
            print("[错误] 未提供 PPT 主题。请通过 --topic 传入或在 .env 中设置 DEFAULT_TOPIC。", file=sys.stderr)
            sys.exit(1)

        print(f"主题：{topic}")
        print(f"受众：{audience}")
        print(f"页数：{pages}")
        print(f"模型：{os.getenv('OPENAI_MODEL', 'gpt-4o')}")
        print("模式：HTML（同时导出图片版 + 可编辑版）")
        print(f"精修：{'开启' if polish else '关闭'}")
        if args.max_pages:
            print(f"短链路页数：前 {args.max_pages} 页")
        print("-" * 40)

        out = run_pipeline(
            topic=topic,
            audience=audience,
            page_req=pages,
            provider=args.provider,
            research=args.research,
            polish=polish,
            max_pages=args.max_pages,
            editable_engine=args.editable_engine,
        )
        print(f"\nHTML 文件已保存至：{out}/html/")
        deck_stem = safe_filename_part(topic, max_length=30)
        print(f"图片版 PPT：{out}/{deck_stem}.pptx")
        print(f"可编辑版 PPT：{out}/{deck_stem}_editable.pptx")
        print(f"链路清单：{out}/editable-ppt-chain.json")
    except Exception as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
