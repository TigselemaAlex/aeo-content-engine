import typer
from pydantic import ValidationError

from content_engine.config import Settings, get_settings

app = typer.Typer()


@app.callback()
def main() -> None:
    """Content Engine worker"""


def load_settings() -> Settings:
    try:
        return get_settings()
    except ValidationError as error:
        for item in error.errors():
            typer.echo(f"Missing or empty setting: {str(item['loc'][0]).upper()}", err=True)
        raise typer.Exit(code=1) from None


@app.command()
def hello() -> None:
    settings = load_settings()
    print(settings.claude_model_generate)
