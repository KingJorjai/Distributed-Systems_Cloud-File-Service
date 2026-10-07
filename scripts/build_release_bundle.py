"""Build a self-contained PyInstaller bundle for one application component."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = {
    "server": {
        "entrypoint": "serv_fich_multithread.py",
        "executable": "cloud-file-server",
        "readme": "README-server.txt",
        "data_directory": "files",
    },
    "client": {
        "entrypoint": "cli_fich.py",
        "executable": "cloud-file-client",
        "readme": "README-client.txt",
        "data_directory": "client_files",
    },
}


def build_bundle(component: str, output_directory: Path, archive_format: str) -> Path:
    settings = COMPONENTS[component]
    work_directory = output_directory / "build"
    dist_directory = output_directory / "dist"
    staging_directory = output_directory / settings["executable"]
    work_directory.mkdir(parents=True, exist_ok=True)
    dist_directory.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--clean",
            "--noconfirm",
            "--onedir",
            "--name",
            settings["executable"],
            "--paths",
            str(ROOT),
            "--distpath",
            str(dist_directory),
            "--workpath",
            str(work_directory),
            "--specpath",
            str(output_directory),
            str(ROOT / settings["entrypoint"]),
        ],
        check=True,
        cwd=ROOT,
    )

    built_directory = dist_directory / settings["executable"]
    if staging_directory.exists():
        shutil.rmtree(staging_directory)
    shutil.copytree(built_directory, staging_directory)
    shutil.copy2(ROOT / "config.toml.example", staging_directory / "config.toml.example")
    shutil.copy2(
        ROOT / "distribution" / settings["readme"],
        staging_directory / settings["readme"],
    )
    (staging_directory / settings["data_directory"]).mkdir()

    archive_base = output_directory / settings["executable"]
    archive_path = Path(
        shutil.make_archive(
            str(archive_base),
            archive_format,
            root_dir=output_directory,
            base_dir=settings["executable"],
        )
    )
    return archive_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("component", choices=sorted(COMPONENTS))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive-format", choices=("zip", "gztar"), required=True)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    archive = build_bundle(args.component, args.output, args.archive_format)
    print(archive)


if __name__ == "__main__":
    main()
