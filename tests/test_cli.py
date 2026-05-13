"""Smoke tests for CLI commands."""

from pathlib import Path

import yaml
from click.testing import CliRunner

from fallbackrabbit.cli import cli


class TestInitCommand:
    def test_creates_starter_config(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        assert (tmp_path / "chain.yaml").exists()
        content = yaml.safe_load((tmp_path / "chain.yaml").read_text())
        assert "name" in content
        assert "providers" in content

    def test_does_not_overwrite(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "chain.yaml").write_text("existing", encoding="utf-8")
        runner = CliRunner()
        result = runner.invoke(cli, ["init"])
        assert "already exists" in result.output
        assert (tmp_path / "chain.yaml").read_text() == "existing"

    def test_custom_output_path(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["init", "-o", "my_chain.yaml"])
        assert result.exit_code == 0
        assert (tmp_path / "my_chain.yaml").exists()


class TestValidateCommand:
    def test_valid_chain(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "validate",
                str(Path(__file__).resolve().parent.parent / "schemas" / "example_chain.yaml"),
            ],
        )
        assert result.exit_code == 0
        assert "Valid chain" in result.output

    def test_invalid_path(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", "/nonexistent.yaml"])
        assert result.exit_code != 0


class TestTestCommand:
    def test_runs_simulation(self) -> None:
        chain_path = str(Path(__file__).resolve().parent.parent / "schemas" / "example_chain.yaml")
        runner = CliRunner()
        result = runner.invoke(cli, ["test", chain_path])
        assert result.exit_code == 0
        assert "Success rate" in result.output or "example-chain" in result.output


class TestExportCommand:
    def test_export_custom(self, tmp_path: Path) -> None:
        chain_path = str(Path(__file__).resolve().parent.parent / "schemas" / "example_chain.yaml")
        out_path = str(tmp_path / "custom_export.yaml")
        runner = CliRunner()
        result = runner.invoke(cli, ["export", chain_path, "--format", "custom", "-o", out_path])
        assert result.exit_code == 0
        with open(out_path) as f:
            output = yaml.safe_load(f)
        assert output["chain_name"] == "example-chain"

    def test_export_litellm(self, tmp_path: Path) -> None:
        chain_path = str(Path(__file__).resolve().parent.parent / "schemas" / "example_chain.yaml")
        out_path = str(tmp_path / "litellm_export.yaml")
        runner = CliRunner()
        result = runner.invoke(cli, ["export", chain_path, "--format", "litellm", "-o", out_path])
        assert result.exit_code == 0
        with open(out_path) as f:
            output = yaml.safe_load(f)
        assert "model_list" in output

    def test_export_to_file(self, tmp_path: Path) -> None:
        chain_path = str(Path(__file__).resolve().parent.parent / "schemas" / "example_chain.yaml")
        out_path = str(tmp_path / "export.yaml")
        runner = CliRunner()
        result = runner.invoke(cli, ["export", chain_path, "--format", "custom", "-o", out_path])
        assert result.exit_code == 0
        assert Path(out_path).exists()
