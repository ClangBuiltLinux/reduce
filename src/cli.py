import sys

from argparse import ArgumentTypeError
from pathlib import Path
from .types import Command


class Colors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    MAGENTA = "\u001b[35m"


def error(msg: str) -> None:
    print(f"{Colors.FAIL}[ERROR]{Colors.ENDC} {msg}")
    sys.exit(1)


def warn(msg: str, ret_only: bool = False) -> str:
    msg = f"{Colors.WARNING}[WARNING]{Colors.ENDC} {msg}"
    if not ret_only:
        print(msg)
    return msg


def success(msg: str) -> None:
    print(f"{Colors.OKGREEN}[SUCCESS]{Colors.ENDC} {msg}")


def info(msg: str) -> None:
    print(f"{Colors.OKBLUE}[INFO]{Colors.ENDC} {msg}")


def todo(msg: str) -> None:
    print(f"{Colors.MAGENTA + Colors.BOLD}[TODO]{Colors.ENDC} {msg}")


def validate_path_from_cli(
    _path: str, argument: str, allow_mkdir: bool = False
) -> Path:
    """
    Allow argparse to actually validate -p/--path-to-linux argument and
    provide helpful feedback
    """
    posix_path = Path(_path.strip())

    if not posix_path.is_dir():
        if not allow_mkdir:
            raise ArgumentTypeError(
                f"Invalid {argument} argument provided: {_path} is not a "
                "directory or it doesn't exist"
            )
        info(f"Making directory for prepreduce's output files: {posix_path}")
        posix_path.mkdir()

    return posix_path


def validate_target_from_cli(_target: str) -> Path:
    """
    Allow argparse to actually validate the target argument as well as convert
    to PosixPath
    """
    posix_path = Path(_target)
    if posix_path.suffix != ".i" and len(posix_path.suffix):
        error(
            f"target file has {posix_path.suffix} extension instead of `.i`. "
            "Either have no suffix or add `.i` -- quitting now."
        )

    return posix_path.with_suffix(".i")


def validate_build_cmd_from_cli(build_cmd: Command) -> None:
    """
    We need V=1 to find original compiler invocation.
    If V=1 is not found, add it.

    Also, don't allow user to provide target.i file as that is a separate arg
    """
    if "V=1" not in build_cmd:
        info("Adding V=1 to build command")
        build_cmd.append("V=1")

    if any([str(part).endswith(".i") for part in build_cmd]):  # cast is *necessary*
        raise RuntimeError("Don't include the target .i file in your build command")
