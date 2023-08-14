import argparse
import subprocess
from pathlib import Path

from icecream import ic

from .cli import error, info


def find_dot_i_files() -> list[str]:
    info("Looking for .i files to reduce")
    results = Path.cwd().glob(pattern=r"*.i")

    return [x.name for x in results]


def use_cvise(target: str) -> None:
    i_files = find_dot_i_files()
    if len(i_files) < 1:
        error(
            "Couldn't find any .i files in ./\n\tDid you run:\n\t$ python3 reduce.py prep"
        )
    if len(i_files) > 1:
        error(
            "Couldn't automatically determine the .i file to target for reduction.\n"
            "There may be multiple .i files in this directory.\n"
            "Choose a specific one with the -t flag"
        )

    chosen = i_files[0] if not target else target
    ic(chosen)

    ic(i_files)

    if not Path("./test.sh").exists():
        error("Couldn't find test.sh in ./\n\tDid you run:\n\t$ python3 reduce.py prep")

    cmd = ["cvise", "test.sh", chosen]

    info(f"Reducing {chosen} with C-Vise")

    result = subprocess.run(cmd, stdout=subprocess.PIPE)
    if result.returncode == 1:
        error(
            "C-Vise error...\n\tDid you specifiy a target file with -t which does not exist?"
        )
    ic(result)

    if "cannot run" in result.stdout.decode():
        print(result.stdout.decode())
        error("Please write an interestingness test in ./test.sh")


def main(cli_args: argparse.Namespace) -> None:
    ic.enable() if cli_args.debug else ic.disable()
    ic(cli_args)

    use_cvise(cli_args.target)


def setup_argparser(parser: argparse.ArgumentParser) -> None:
    """
    Parse out arguments from command line interface.
    """
    parser.add_argument(
        "-d",
        "--debug",
        help="Enable Debug logs for $ reduce code",
        action="store_true",
        default=False,
    )

    parser.add_argument(
        "-t",
        "--target",
        help="Which (if multiple) .i file to target for reduction",
        default="",
    )
