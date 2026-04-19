"""Entry point for weibo CLI."""

from __future__ import annotations

import json
import sys

import typer

from weibo import __version__
from weibo.config import load_config
from weibo.errors import ErrorPayload, WeiboError

app = typer.Typer(
    add_completion=False,
    help=(
        "weibo — 视频重制工具（横转竖 / AI转绘 / 换人重拍 / 爆款复刻）\n\n"
        "分割 → Seedance 2.0 重制 → 合并 → 效果验证\n\n"
        "【初始化】\n"
        '  export WEIBO_ARK_API_KEY="你的火山方舟 API Key"\n\n'
        "【一键运行】\n"
        '  weibo run ./input.mp4 -o ./job --preset h2v --prompt "竖屏构图"\n\n'
        "【分步运行】\n"
        "  weibo split ./input.mp4 -o ./job --preset h2v\n"
        '  weibo remake ./job/manifest.json --prompt "竖屏构图"\n'
        "  weibo merge ./job/manifest.json -o ./final.mp4\n"
        "  weibo verify ./job/manifest.json\n\n"
        "【预设模式】 h2v / style_transfer / character_swap / viral_replica\n"
    ),
)


def _render_error(err: WeiboError, as_json: bool) -> None:
    payload = ErrorPayload(
        code=err.code, message=err.message, request_id=err.request_id
    )
    if as_json:
        typer.echo(json.dumps(payload.__dict__, ensure_ascii=False))
    else:
        rid = f" request_id={err.request_id}" if err.request_id else ""
        typer.echo(f"[{payload.code}] {payload.message}{rid}", err=True)


@app.callback()
def root(
    ctx: typer.Context,
    api_key: str | None = typer.Option(
        None, "--api-key", help="临时指定 API Key。"
    ),
    seedance_endpoint: str | None = typer.Option(
        None, "--seedance-endpoint", help="临时覆盖视频端点。"
    ),
    output_json: bool = typer.Option(False, "--json", help="JSON 输出。"),
) -> None:
    overrides: dict = {}
    if api_key:
        overrides["api_key"] = api_key
    if seedance_endpoint:
        overrides["video_model"] = seedance_endpoint
    ctx.obj = load_config(overrides=overrides)


@app.command()
def version() -> None:
    """显示版本号。"""
    typer.echo(f"weibo {__version__}")


from weibo.commands.split import register_split
from weibo.commands.remake import register_remake
from weibo.commands.merge import register_merge
from weibo.commands.run import register_run
from weibo.commands.query import register_query
from weibo.commands.verify import register_verify
from weibo.commands.asset import register_asset

register_split(app)
register_remake(app)
register_merge(app)
register_run(app)
register_query(app)
register_verify(app)
register_asset(app)


def main() -> None:
    try:
        app()
    except WeiboError as err:
        _render_error(err, as_json="--json" in sys.argv)
        raise SystemExit(err.exit_code) from None


if __name__ == "__main__":
    main()
